import numpy as np
from app.ink_layers import Strips
from app.plan_model import PlanModel
from app.source_joints import close_source_joints


def scene(monkeypatch, bridge=True, opening=False):
    points = [(10, 10), (90, 10), (90, 90), (10, 90), (50, 35), (50, 65)]
    m = PlanModel.model_validate({
        "id": "joints", "imageTransform": {"width": 400, "height": 400},
        "nodes": [{"id": str(i), "x": x, "y": y} for i, (x, y) in enumerate(points)],
        "walls": [{"id": str(i), "a": str(a), "b": str(b), "thicknessPx": 8}
                  for i, (a, b) in enumerate([(0, 1), (1, 2), (2, 3), (3, 0), (4, 5)])],
        "openings": ([{
            "id": "opening", "kind": "window", "status": "proposed",
            "span": [{"x": 50, "y": 20}, {"x": 50, "y": 30}],
        }] if opening else []),
    })
    empty = np.zeros((400, 400), bool)
    material = empty.copy()
    material[10 if bridge else 35:91 if bridge else 66, 47:54] = True
    strips = Strips(empty, empty, empty, empty, {}, structural_colour=material, boundary_mask=empty)
    monkeypatch.setattr("app.ink_layers.wall_strips", lambda _: strips)
    return m, np.zeros((400, 400, 3), np.uint8)


def test_source_joint_repairs_both_ends_and_is_idempotent(monkeypatch):
    model, image = scene(monkeypatch)
    fixed = close_source_joints(model, image)
    fixed = PlanModel.model_validate(fixed.dump())
    wall = next(w for w in fixed.walls if w.id == "4")
    nodes = {n.id: n for n in fixed.nodes}
    assert nodes[wall.a].y == 10 and nodes[wall.b].y == 90
    for end in (wall.a, wall.b):
        assert any(w.id != wall.id and end in (w.a, w.b) for w in fixed.walls)
    assert close_source_joints(fixed, image).dump() == fixed.dump()


def test_blank_gap_is_not_authorized_by_nearby_wall_pixels(monkeypatch):
    model, image = scene(monkeypatch, bridge=False)
    fixed = close_source_joints(model, image)
    assert fixed.nodes == model.nodes


def test_proposed_window_vetoes_a_source_backed_repair(monkeypatch):
    model, image = scene(monkeypatch, opening=True)
    fixed = close_source_joints(model, image)
    nodes = {n.id: n for n in fixed.nodes}
    assert nodes["4"].y == 35
    assert fixed.openings == model.openings


def test_manual_wall_is_not_extended(monkeypatch):
    model, image = scene(monkeypatch)
    model.walls[-1].source = "user"
    assert close_source_joints(model, image).nodes == model.nodes


def test_thin_dimension_stroke_cannot_authorize_extension(monkeypatch):
    model, image = scene(monkeypatch)
    empty = np.zeros(image.shape[:2], bool)
    material = empty.copy()
    material[10:91, 50] = True
    strips = Strips(empty, empty, empty, empty, {}, structural_colour=material, boundary_mask=empty)
    monkeypatch.setattr("app.ink_layers.wall_strips", lambda _: strips)
    assert close_source_joints(model, image).nodes == model.nodes


def test_hosted_opening_stays_in_place_when_host_start_extends(monkeypatch):
    model, image = scene(monkeypatch)
    data = model.dump()
    data["openings"] = [{"id": "window", "kind": "window", "hostWallId": "4",
                         "offsetPx": 10, "widthPx": 10, "status": "confirmed"}]
    model = PlanModel.model_validate(data)
    fixed = close_source_joints(model, image)
    opening = fixed.openings[0]
    assert opening.offset_px == 35
    assert opening.width_px == 10 and opening.status == "confirmed"
    wall = next(w for w in fixed.walls if w.id == "4")
    nodes = {n.id: n for n in fixed.nodes}
    start = nodes[wall.a].y + opening.offset_px
    assert (start, start + opening.width_px) == (45, 55)
    for key in (wall.a, wall.b):
        assert any(w.id != wall.id and key in (w.a, w.b) for w in fixed.walls)


def test_source_backed_collinear_seam_is_welded(monkeypatch):
    model, image = scene(monkeypatch)
    data = model.dump()
    data["walls"] = [{"id": "a", "a": "0", "b": "4", "thicknessPx": 8},
                     {"id": "b", "a": "5", "b": "1", "thicknessPx": 8}]
    data["nodes"] = [{"id": i, "x": x, "y": 50}
                     for i, x in [("0", 10), ("4", 40), ("5", 60), ("1", 90)]]
    model = PlanModel.model_validate(data)
    empty = np.zeros(image.shape[:2], bool)
    material = empty.copy()
    material[47:54, 10:91] = True
    strips = Strips(empty, empty, empty, empty, {}, structural_colour=material, boundary_mask=empty)
    monkeypatch.setattr("app.ink_layers.wall_strips", lambda _: strips)
    fixed = close_source_joints(model, image)
    assert fixed.walls[0].b == fixed.walls[1].a
    assert close_source_joints(fixed, image).dump() == fixed.dump()


def test_small_jamb_seam_aligns_without_changing_opening_width():
    from app.wall_alignment import align_walls

    model = PlanModel.model_validate({
        "id": "jamb", "imageTransform": {"width": 400, "height": 400},
        "nodes": [{"id": i, "x": x, "y": y}
                  for i, x, y in [("a", 10, 50), ("b", 40, 50), ("c", 49, 50.7), ("d", 90, 50.7)]],
        "walls": [{"id": "a", "a": "a", "b": "b", "thicknessPx": 13.4},
                  {"id": "b", "a": "c", "b": "d", "thicknessPx": 13.4}],
        "openings": [{"id": "window", "kind": "window", "hostWallId": "b",
                      "offsetPx": 0, "widthPx": 41, "status": "confirmed"}],
    })
    fixed = align_walls(model)
    assert fixed.walls[0].b == fixed.walls[1].a
    assert fixed.openings[0].width_px == 41
    assert fixed.openings[0].span[0].x == 49
    assert fixed.openings[0].span[1].x == 90
    assert len({n.y for n in fixed.nodes}) == 1
