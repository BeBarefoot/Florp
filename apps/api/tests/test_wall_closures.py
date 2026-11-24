import cv2
import numpy as np

from app.plan_model import PlanModel, Node, Wall, ImageTransform
from app.plan_derive import derive
from app.wall_closures import search_closures


def test_faint_fourth_wall_is_a_reviewable_suggestion():
    model = PlanModel(
        id="u",
        image_transform=ImageTransform(width=180, height=180),
        nodes=[
            Node(id=str(i), x=x, y=y)
            for i, (x, y) in enumerate([(30, 130), (30, 25), (145, 25), (145, 130)])
        ],
        walls=[
            Wall(id=f"w{i}", a=str(i), b=str(i + 1), thickness_px=10) for i in range(3)
        ],
    )
    image = np.full((180, 180, 3), 255, np.uint8)
    cv2.rectangle(image, (30, 127), (145, 133), (239, 239, 239), -1)
    draft = derive(search_closures(model, image))
    (suggestion,) = [f for f in draft.findings if f.closure]
    assert (
        len(draft.walls) == 3
        and not draft.rooms
        and suggestion.closure.thickness_px == 7
    )
    draft.walls.append(Wall(id="accepted", a="0", b="3", thickness_px=7))
    closed = derive(draft)
    assert len(closed.rooms) == 1 and not any(f.closure for f in closed.findings)
    image[:, 72:92] = 255
    assert not any(f.closure for f in search_closures(model, image).findings)
    image[:] = 255
    cv2.line(image, (30, 130), (145, 130), (120, 120, 120), 1)
    assert not any(f.closure for f in search_closures(model, image).findings)


def test_unequal_wall_faces_recover_center_and_join():
    from app.workspace_worker import _remeasure
    from app.structural_runs import join_intersections
    from app.plan_workspace import Point, Segment

    mask = np.zeros((180, 200), np.uint8)
    mask[20:48, 18:177] = 255
    mask[20:151, 168:177] = 255
    runs = [
        Segment(
            id="top", start=Point(x=18, y=25), end=Point(x=163, y=25), thickness_px=12
        ),
        Segment(
            id="side", start=Point(x=170, y=46), end=Point(x=170, y=150), thickness_px=6
        ),
    ]
    _remeasure(runs, mask, [6, 14])
    top, side = join_intersections(runs)
    assert [top.thickness_px, side.thickness_px] == [28, 9]
    assert top.end == side.start == Point(x=172, y=33.5)


def test_gray_pier_between_windows_survives_dark_ink_elsewhere():
    from app.ink_layers import wall_strips

    image = np.full((400, 600, 3), 255, np.uint8)
    for a, b in [(45, 200), (253, 315), (363, 550)]:
        cv2.rectangle(image, (a, 80), (b, 90), (205, 205, 205), -1)
    for x in (45, 540):
        cv2.rectangle(image, (x, 80), (x + 10, 220), (205, 205, 205), -1)
    cv2.rectangle(image, (45, 310), (550, 327), (60, 60, 60), -1)
    mask = wall_strips(image).mask
    assert mask[85, 285] and mask[320, 140]
    assert not mask[85, 224] and not mask[85, 339]


def test_fourth_wall_meets_longer_return_without_covering_a_door():
    from app.plan_model import Opening

    coordinates = [(30, 110), (30, 25), (80, 25), (145, 25), (145, 155)]
    model = PlanModel(
        id="t",
        image_transform=ImageTransform(width=180, height=180),
        nodes=[Node(id=str(i), x=x, y=y) for i, (x, y) in enumerate(coordinates)],
        walls=[
            Wall(id=f"w{i}", a=str(i), b=str(i + 1), thickness_px=9) for i in range(4)
        ],
    )
    image = np.full((180, 180, 3), 255, np.uint8)
    image[107:115, 30:146] = 235
    (found,) = [f.closure for f in search_closures(model, image).findings if f.closure]
    assert found.end.x == 145 and found.end.y == 110
    model.openings = [
        Opening(id="door", kind="door", host_wall_id="w3", offset_px=75, width_px=20)
    ]
    assert not any(f.closure for f in search_closures(model, image).findings)


def test_pale_plan_prunes_short_isolated_fixture_stroke_but_preserves_partition():
    from app.plan_reconstruct import Counters, ReconstructConfig, Run, _prune

    points = [(10, 10), (200, 10), (100, 10), (100, 60), (25, 30), (75, 30)]
    edges = [
        [0, 2, Run(points[0], points[2], 24)],
        [2, 1, Run(points[2], points[1], 24)],
        [2, 3, Run(points[2], points[3], 8)],
        [4, 5, Run(points[4], points[5], 8)],
    ]
    counters = Counters()
    kept = _prune(points, edges, 24, ReconstructConfig(), counters, pale=True)
    assert kept == edges[:3]
    assert counters.pruned_fragments == 1


def test_neutral_reconstruction_closes_supported_partition_and_keeps_window_host():
    from types import SimpleNamespace
    from app.plan_reconstruct import reconstruct
    from app.plan_workspace import Document, Point, Segment

    def segment(key, start, end, kind="wall", supported=False):
        return Segment(
            id=key,
            kind=kind,
            start=Point(x=start[0], y=start[1]),
            end=Point(x=end[0], y=end[1]),
            thickness_px=10,
            boundary_supported=supported,
        )

    objects = [
        segment("left", (30, 40), (30, 140)),
        segment("top", (30, 40), (145, 40)),
        segment("right", (145, 40), (145, 140)),
        segment("window", (55, 40), (112, 40), "window", True),
    ]
    doc = Document(width=180, height=180, objects=objects)
    strips = SimpleNamespace(stats={"neutral_wall_bands": True}, boundary_mask=None, source_tint=None)
    image = np.full((180, 180, 3), 255, np.uint8)
    # A fixture outline touches the window and the missing partition.
    cv2.rectangle(image, (82, 40), (89, 140), (220,) * 3, -1)
    cv2.line(image, (30, 140), (145, 140), (165,) * 3, 1)
    unresolved = reconstruct(doc, "plan", strips=strips, image=image)
    assert not unresolved.rooms
    cv2.rectangle(image, (30, 136), (145, 144), (219,) * 3, -1)
    recovered = reconstruct(doc, "plan", strips=strips, image=image)
    assert len(recovered.rooms) == 1
    assert len(recovered.walls) == 4
    window, = recovered.openings
    assert window.host_wall_id
    assert window.width_px == 57
