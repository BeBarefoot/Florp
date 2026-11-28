import cv2
import numpy as np
import pytest

from app.balconies import recover_balconies
from app.plan_derive import derive
from app.plan_model import ImageTransform, Node, Opening, PlanModel, Wall
from app.plan_score import _opening_geom


@pytest.mark.parametrize("rotation", [0, 1, 2, 3])
@pytest.mark.parametrize("partial_rails", [False, True])
def test_paired_balcony_rails_follow_an_exterior_door(rotation, partial_rails):
    def point(x, y):
        for _ in range(rotation):
            x, y = y, 209 - x
        return x, y

    nodes = [
        Node(id=str(i), x=x, y=y)
        for i, (x, y) in enumerate(point(x, y) for x, y in [(24, 96), (180, 96), (180, 180), (24, 180)])
    ]
    model = derive(PlanModel(
        id="plan", image_transform=ImageTransform(width=210, height=210),
        nodes=nodes,
        walls=[Wall(id=f"w{i}", a=str(i), b=str((i + 1) % 4), thickness_px=10) for i in range(4)],
        openings=[
            Opening(id="door", host_wall_id="w0", kind="door", offset_px=44, width_px=27),
            Opening(id="window", host_wall_id="w0", kind="window", offset_px=115, width_px=25),
        ],
    ))
    if partial_rails:
        extra = [
            ("left", point(24, 54)), ("right", point(132, 60)), ("right-base", point(132, 96)),
        ]
        model = derive(model.model_copy(update={
            "nodes": model.nodes + [Node(id=key, x=x, y=y) for key, (x, y) in extra],
            "walls": model.walls + [
                Wall(id="left-stub", a="0", b="left", thickness_px=9),
                Wall(id="right-stub", a="right", b="right-base", thickness_px=8),
            ],
        }))
    image = np.full((210, 210, 3), 251, np.uint8)

    def draw_rail(points):
        for a, b in zip(points, points[1:]):
            cv2.line(image, point(*a), point(*b), (154,) * 3, 1)

    # A single U-shaped site line is insufficient.
    draw_rail([(24, 93), (24, 35), (132, 35), (132, 93)])
    assert recover_balconies(model, image) is model
    draw_rail([(28, 93), (28, 39), (128, 39), (128, 93)])
    recovered = recover_balconies(model, image)
    balcony, = [room for room in recovered.rooms if room.room_type == "balcony"]
    assert balcony.label == "Balcony"
    assert balcony.area_px2 == 102 * 52
    assert len(recovered.rooms) == 2
    assert all(not w.id.endswith("-stub") for w in recovered.walls)
    assert sum(w.exterior and w.height_m == 1.05 for w in recovered.walls if w.exterior) == 3
    for old, new in zip(model.openings, recovered.openings):
        assert new.width_px == old.width_px
        assert _opening_geom(recovered, new)[1:] == _opening_geom(model, old)[1:]
    assert recover_balconies(recovered, image) is recovered
