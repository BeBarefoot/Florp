import cv2
import numpy as np
import pytest

from app.compact_plan_cleanup import clean_compact_plan
from app.plan_derive import derive
from app.plan_model import ImageTransform, Node, Opening, PlanModel, Wall
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
