import cv2
import numpy as np
import pytest

from app.compact_plan_cleanup import clean_compact_plan, reconnect_soft_scan_jambs
from app.neutral_swings import filter_soft_scan_swings
from app.plan_derive import derive
from app.plan_model import ImageTransform, Node, Opening, PlanModel, Wall
from app.plan_score import _opening_geom
from app.plan_workspace import Point, Segment
from app.workspace_worker import build


def test_soft_large_sheet_keeps_source_canvas_and_window_span(tmp_path):
    small = np.full((360, 460, 3), 251, np.uint8)
    for start, end in [
        ((50, 70), (165, 82)), ((255, 70), (408, 82)),
        ((50, 70), (62, 300)), ((396, 70), (408, 300)),
        ((50, 288), (408, 300)),
    ]:
        cv2.rectangle(small, start, end, (211,) * 3, -1)
        cv2.rectangle(small, start, end, (145,) * 3, 1)
    for y in (74, 78):
        cv2.line(small, (165, y), (255, y), (149,) * 3, 1)
    large = cv2.resize(small, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
    large = cv2.GaussianBlur(large, (0, 0), 1.8)
    path = tmp_path / "soft.png"
    assert cv2.imwrite(str(path), large)
    model = build(path, plan_id="soft")
    assert (model.image_transform.width, model.image_transform.height) == (1380, 1080)
    assert any("reduced resolution" in note for note in model.notes)
    window, = model.openings
    assert window.kind == "window" and window.host_wall_id
    assert window.width_px == pytest.approx(270, abs=25)
    assert sorted(point.x for point in window.span) == pytest.approx([495, 765], abs=20)
    assert len(model.rooms) == 1
    document = build(path)
    assert (document.width, document.height) == (1380, 1080)
    raw, = [segment for segment in document.objects if segment.kind == "window"]
    assert sorted([raw.start.x, raw.end.x]) == pytest.approx([495, 765], abs=20)


def test_compact_cleanup_keeps_the_wider_door_and_installed_room():
    xy = [(20, 20), (200, 20), (200, 160), (20, 160), (69, 29), (105, 29), (25, 65), (25, 140)]
    plan = derive(PlanModel(
        id="plan", image_transform=ImageTransform(width=220, height=180),
        nodes=[Node(id=f"n{i}", x=x, y=y) for i, (x, y) in enumerate(xy)],
        walls=[
            Wall(id=f"w{i}", a=f"n{i}", b=f"n{(i + 1) % 4}", thickness_px=14)
            for i in range(4)
        ] + [
            Wall(id="ghost-host", a="n4", b="n5", thickness_px=6),
            Wall(id="outline", a="n6", b="n7", thickness_px=3),
        ],
        openings=[
            Opening(id="entry", kind="door", host_wall_id="w0", offset_px=48, width_px=41, confidence=0.78),
            Opening(id="competing-swing", kind="door", host_wall_id="ghost-host", width_px=36, confidence=0.78),
        ],
    ))
    cleaned = clean_compact_plan(plan)
    assert [door.id for door in cleaned.openings] == ["entry"]
    assert {wall.id for wall in cleaned.walls} == {"w0", "w1", "w2", "w3"}
    assert [room.id for room in cleaned.rooms] == [room.id for room in plan.rooms]


def test_soft_scan_swing_needs_masonry_beyond_the_arc():
    image = np.full((150, 200, 3), 251, np.uint8)
    cv2.rectangle(image, (10, 43), (65, 55), (213,) * 3, -1)
    cv2.rectangle(image, (108, 43), (170, 55), (213,) * 3, -1)
    cv2.line(image, (108, 49), (108, 89), (150,) * 3, 2)
    cv2.ellipse(image, (108, 49), (41, 41), 0, 90, 180, (150,) * 3, 2)
    horizontal = Segment(id="masonry", start=Point(x=108, y=49), end=Point(x=68, y=49))
    vertical = Segment(id="leaf", start=Point(x=108, y=49), end=Point(x=108, y=89))
    doors = [
        horizontal.model_copy(update={"id": "door", "kind": "door", "host_id": horizontal.id,
                                      "boundary_supported": True, "leaf": Point(x=0, y=1)}),
        vertical.model_copy(update={"id": "false-door", "kind": "door", "host_id": vertical.id,
                                    "boundary_supported": True, "leaf": Point(x=-1, y=0)}),
    ]
    found = filter_soft_scan_swings(image, [], [horizontal, vertical, *doors])
    assert [item.id for item in found] == ["masonry", "door"]


def test_soft_scan_connects_drawn_jamb_seam_without_moving_openings():
    plan = derive(PlanModel(
        id="plan", image_transform=ImageTransform(width=220, height=160),
        nodes=[Node(id=f"n{i}", x=x, y=y) for i, (x, y) in enumerate(
            [(14, 45), (82, 45), (114, 45), (125, 45), (200, 45), (200, 140), (14, 140)]
        )],
        walls=[Wall(id=f"w{i}", a=f"n{a}", b=f"n{b}", thickness_px=14)
               for i, (a, b) in enumerate([(0, 1), (1, 2), (3, 4), (4, 5), (5, 6), (6, 0)])],
        openings=[
            Opening(id="door", kind="door", host_wall_id="w1", width_px=32),
            Opening(id="window", kind="window", host_wall_id="w2", offset_px=20, width_px=40),
        ],
    ))
    image = np.full((160, 220, 3), 251, np.uint8)
    assert reconnect_soft_scan_jambs(plan, image) is plan
    cv2.rectangle(image, (114, 40), (125, 50), (202,) * 3, -1)
    updated = reconnect_soft_scan_jambs(plan, image)
    assert len(updated.walls) == len(plan.walls) + 1
    assert len(updated.rooms) == 1
    for old, joined in zip(plan.openings, updated.openings):
        assert _opening_geom(plan, old)[1:] == _opening_geom(updated, joined)[1:]


def test_compact_cleanup_removes_shallow_fitting_even_if_inset_room_collapses():
    coords = [(12, 40), (190, 40), (190, 135), (12, 135), (64, 135), (147, 135), (147, 123), (64, 123)]
    plan = derive(PlanModel(
        id="plan", image_transform=ImageTransform(width=220, height=160),
        nodes=[Node(id=f"n{i}", x=x, y=y) for i, (x, y) in enumerate(coords)],
        walls=[
            Wall(id=f"w{i}", a=f"n{a}", b=f"n{b}", thickness_px=width)
            for i, (a, b, width) in enumerate([
                (0, 1, 16), (1, 2, 16), (2, 5, 29), (5, 4, 29), (4, 3, 29), (3, 0, 16),
                (4, 7, 5), (7, 6, 5), (6, 5, 5),
            ])
        ],
        openings=[Opening(id="door", kind="door", host_wall_id="w0", offset_px=54, width_px=35)],
    ))
    cleaned = clean_compact_plan(plan)
    assert {wall.id for wall in cleaned.walls} == {f"w{i}" for i in range(6)}
    assert len(cleaned.rooms) == 1
    assert cleaned.openings == plan.openings
