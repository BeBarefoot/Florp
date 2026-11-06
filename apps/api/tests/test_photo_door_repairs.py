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
