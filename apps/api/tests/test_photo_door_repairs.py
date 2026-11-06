import numpy as np

from app.ink_layers import Strips
from app.photo_door_repairs import repair_photo_doors
from app.plan_model import ImageTransform, Node, Opening, PlanModel, Pt, Scale, Wall


def fixture(*, painted=True, manual_leaf=False, window=False):
    points = {
        "host-a": (50, 70), "host-b": (150, 70),
        "leaf-a": (140, 70), "leaf-b": (140, 110),
        "partition-a": (145, 70), "tee": (145, 120),
        "left": (30, 120), "spur-end": (163, 120),
        "corner": (190, 70), "short-end": (190, 130),
        "bottom-a": (30, 170), "bottom-b": (310, 170),
    }
    edges = {
        "door-host": ("host-a", "host-b"), "leaf": ("leaf-a", "leaf-b"),
        "partition": ("partition-a", "tee"), "bath-wall": ("left", "tee"),
        "spur": ("tee", "spur-end"), "short-return": ("corner", "short-end"),
        "bottom": ("bottom-a", "bottom-b"),
    }
    openings = [
        Opening(id="door", kind="door", host_wall_id="door-host", offset_px=50, width_px=40,
                span=(Pt(x=100, y=70), Pt(x=140, y=70)), swing="left", hinge="end",
                status="confirmed"),
    ]
    if window:
        openings.append(Opening(id="window", kind="window", host_wall_id="bottom",
                                offset_px=150, width_px=20, status="confirmed",
                                span=(Pt(x=180, y=170), Pt(x=200, y=170))))
    model = PlanModel(
        id="plan", image_transform=ImageTransform(width=330, height=200), scale=Scale(),
        nodes=[Node(id=key, x=x, y=y) for key, (x, y) in points.items()],
        walls=[Wall(id=key, a=a, b=b, thickness_px=6,
                    source="user" if key == "leaf" and manual_leaf else "extracted")
               for key, (a, b) in edges.items()],
        openings=openings,
    )
    tint = np.zeros((200, 330), dtype=bool)
    tint[70:120, 143:148] = True
    tint[117:123, 30:148] = True
    if painted:
        tint[68:73, 140:192] = True
        tint[70:171, 188:193] = True
    # The original filled strip mask can still contain the false leaf.
    boundary = tint.copy()
    boundary[70:110, 140] = True
    return model, Strips(boundary, boundary, boundary, boundary, {},
                         boundary_mask=boundary, source_tint=tint)


def test_photo_repair_removes_door_leaf_and_spur_and_connects_painted_return():
    model, strips = fixture()
    repaired = repair_photo_doors(model, strips)
    walls = {w.id: w for w in repaired.walls}
    assert "leaf" not in walls and "spur" not in walls
    assert walls["partition"] == next(w for w in model.walls if w.id == "partition")
    assert repaired.openings == model.openings
    assert PlanModel.model_validate(repaired.dump()) == repaired

    nodes = {n.id: (n.x, n.y) for n in repaired.nodes}
    extensions = {frozenset((nodes[w.a], nodes[w.b])): w
                  for w in walls.values() if w.id.startswith("door-return-")}
    horizontal = extensions[frozenset(((150, 70), (190, 70)))]
    vertical = extensions[frozenset(((190, 130), (190, 170)))]
    assert {horizontal.a, horizontal.b} & {walls["short-return"].a, walls["short-return"].b}
    assert {vertical.a, vertical.b} & {walls["short-return"].a, walls["short-return"].b}
    assert len([w for w in walls.values() if vertical.b in (w.a, w.b)]) == 3
    assert repair_photo_doors(repaired, strips) is repaired


def test_photo_repair_keeps_manual_wall_and_needs_source_paint_for_new_return():
    model, strips = fixture(painted=False, manual_leaf=True)
    repaired = repair_photo_doors(model, strips)
    assert any(w.id == "leaf" for w in repaired.walls)
    assert not any(w.id.startswith("door-return-") for w in repaired.walls)


def test_photo_repair_does_not_extend_across_a_confirmed_window():
    model, strips = fixture(window=True)
    repaired = repair_photo_doors(model, strips)
    assert repaired.openings == model.openings
    assert not any(w.id.startswith("door-return-") for w in repaired.walls)


def missing_return_fixture(*, swing=True):
    import cv2

    # This is the incomplete result: the stair wall and door have no objects.
    # The only hint in the vector model is a short stub drawn on the wrong row.
    xy = [(80, 40), (80, 111), (80, 135), (101, 111), (35, 217), (295, 217)]
    model = PlanModel(
        id="plan", image_transform=ImageTransform(width=330, height=235), scale=Scale(),
        nodes=[Node(id=str(i), x=x, y=y) for i, (x, y) in enumerate(xy)],
        walls=[Wall(id=id_, a=str(a), b=str(b), thickness_px=7)
               for id_, a, b in [("left", 0, 1), ("lower-left", 1, 2), ("stub", 1, 3), ("bottom", 4, 5)]],
    )
    tint = np.zeros((235, 330), dtype=bool)
    tint[40:136, 78:83] = True
    tint[98:103, 80:101] = True
    tint[98:103, 141:196] = True
    tint[100:218, 191:196] = True
    tint[214:220, 35:296] = True
    image = np.full((235, 330, 3), 222, dtype=np.uint8)
    image[tint] = (155, 163, 194)
    if swing:
        cv2.ellipse(image, (141, 100), (40, 40), 0, 90, 180, (153, 153, 153), 1)
        cv2.line(image, (141, 100), (141, 140), (153, 153, 153), 1)
    return model, tint, image


def test_recovers_entire_partition_and_a_door_with_both_wall_connections():
    from app.missing_photo_door import recover_missing_photo_doors

    model, tint, image = missing_return_fixture()
    result = recover_missing_photo_doors(model, tint, image, confirm_at=0.85)
    door, = result.openings
    assert door.kind == "door" and door.status == "confirmed" and door.hinge == "end"
    assert abs(door.width_px - 41) <= 2
    assert all(w.id != "stub" for w in result.walls)
    walls = {w.id: w for w in result.walls}
    host, return_wall = walls[door.host_wall_id], walls[door.host_wall_id + "-return"]
    assert host.b == return_wall.a
    for joint in (host.a, return_wall.b):
        assert sum(joint in (w.a, w.b) for w in result.walls) == 3
    assert PlanModel.model_validate(result.dump()) == result
    assert recover_missing_photo_doors(result, tint, image, confirm_at=0.85) is result


def test_missing_door_fallback_needs_swing_and_respects_a_rejected_door():
    from app.missing_photo_door import recover_missing_photo_doors

    model, tint, image = missing_return_fixture(swing=False)
    assert recover_missing_photo_doors(model, tint, image, confirm_at=0.85) is model

    model, tint, image = missing_return_fixture()
    rejected = Opening(id="rejected", kind="door", status="rejected", width_px=41,
                       span=(Pt(x=100, y=100), Pt(x=141, y=100)))
    model = model.model_copy(update={"openings": [rejected]})
    assert recover_missing_photo_doors(model, tint, image, confirm_at=0.85) is model
