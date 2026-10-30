"""Regression tests for lost L/T walls, duplicated fragments and opening spans."""

import cv2
import numpy as np
import pytest
from shapely.geometry import LineString
from shapely.ops import unary_union
from app.structural_runs import structural_runs, join_intersections
from app.semantic_workspace import from_labels, _refine_thickness, _prune
from app.plan_workspace import Segment, Point


def line(a, b, name="wall", thickness=8):
    return Segment(
        id=name,
        start=Point(x=a[0], y=a[1]),
        end=Point(x=b[0], y=b[1]),
        thickness_px=thickness,
    )


def test_connected_l_t_network_keeps_each_branch_and_thickness():
    mask = np.zeros((240, 320), np.uint8)
    # A broad concrete L and a thin partition joining its middle.
    cv2.rectangle(mask, (40, 40), (270, 55), 255, -1)
    cv2.rectangle(mask, (255, 40), (270, 200), 255, -1)
    cv2.rectangle(mask, (145, 50), (151, 180), 255, -1)
    runs = join_intersections(structural_runs(mask, 24))
    network = unary_union(
        [LineString([(o.start.x, o.start.y), (o.end.x, o.end.y)]) for o in runs]
    )
    for point in [(60, 47.5), (240, 47.5), (262.5, 150), (148, 150)]:
        from shapely.geometry import Point as ShapePoint

        assert network.distance(ShapePoint(point)) < 2
    vertical = [o for o in runs if o.end.y - o.start.y > 100]
    assert len(vertical) == 2
    assert sorted(o.thickness_px for o in vertical) == [7, 16]
    assert max(o.thickness_px for o in runs) <= 16


def test_distant_collinear_wall_gap_is_not_filled():
    mask = np.zeros((120, 300), np.uint8)
    mask[40:48, 20:100] = 255
    mask[40:48, 170:280] = 255
    runs = join_intersections(structural_runs(mask, 22))
    assert len(runs) == 2
    assert all(not (o.start.x < 130 < o.end.x) for o in runs)


def test_crossing_endpoints_do_not_chain_average_parallel_axes():
    runs = [
        line((20, 50), (100, 50), "h"),
        line((99, 49), (99, 110), "v"),
        line((20, 54), (100, 54), "duplicate"),
    ]
    original = [o.model_copy(deep=True) for o in runs]
    joined = join_intersections(runs)
    assert joined[0].start.y == joined[0].end.y == 50
    assert joined[2].start.y == joined[2].end.y == 54
    assert original[1].start.x == joined[1].end.x == 99


def test_source_thickness_uses_many_sections_not_crossing_midpoint():
    mask = np.zeros((200, 300), bool)
    mask[46:54, 20:280] = True
    mask[10:170, 140:160] = True
    result = _refine_thickness([line((20, 50), (280, 50), thickness=30)], mask)
    assert result[0].thickness_px == 8


def test_redundant_raster_fragments_are_removed_but_new_partition_remains():
    runs = [
        line((20, 50), (280, 50), "long", 20),
        line((60, 48), (90, 48), "fragment", 3),
        line((140, 50), (140, 160), "partition", 8),
    ]
    assert {o.id for o in _prune(runs)} == {"long", "partition"}


def fixture():
    image = np.full((200, 320, 3), 245, np.uint8)
    rooms = np.zeros((200, 320), np.uint8)
    icons = np.zeros_like(rooms)
    rooms[40:52, 20:300] = 2
    cv2.rectangle(image, (20, 40), (299, 51), (100, 100, 180), -1)
    # Exact physical window gap is wider than the initial semantic proposal.
    image[40:52, 120:180] = 245
    icons[40:52, 126:150] = 1
    icons[40:52, 150:172] = 2  # mixed semantic labels should be one window
    return image, rooms, icons


def test_semantic_opening_uses_source_gap_and_valid_host():
    d = from_labels(*fixture())
    windows = [o for o in d.objects if o.kind == "window"]
    assert len(windows) == 1
    window = windows[0]
    assert window.start.x == pytest.approx(120, abs=2)
    assert window.end.x == pytest.approx(179, abs=2)
    assert window.host_id in {o.id for o in d.objects if o.kind == "wall"}
    assert window.uncertain and not window.reviewed
    assert d.reference is None


def test_monochrome_semantic_hypothesis_survives_color_corroboration():
    image, rooms, icons = fixture()
    image[:] = 240
    d = from_labels(image, rooms, icons)
    assert any(o.kind == "wall" for o in d.objects)


def test_cropped_edge_does_not_produce_fake_opening():
    image, rooms, icons = fixture()
    rooms[-10:, 20:300] = 2
    icons[-5:, 160:180] = 1
    d = from_labels(image, rooms, icons)
    assert not any(o.kind != "wall" and o.start.y > 190 for o in d.objects)


def test_bad_label_dimensions_fail_before_vectorization():
    image, rooms, icons = fixture()
    with pytest.raises(ValueError, match="source dimensions"):
        from_labels(image, rooms[:-1], icons)


def test_configured_evaluator_requires_local_files_without_downloading(
    tmp_path, monkeypatch
):
    from app.config import settings
    from app.semantic_workspace import predict

    monkeypatch.setattr(settings, "workspace_semantic_source", str(tmp_path))
    monkeypatch.setattr(
        settings, "workspace_semantic_weights", str(tmp_path / "missing.pkl")
    )
    with pytest.raises(ValueError, match="trusted CubiCasa source"):
        predict(np.full((100, 200, 3), 255, np.uint8))


def test_evaluation_renderer_handles_fully_cut_host_wall():
    from scripts.evaluate_workspace import render
    from app.plan_workspace import Document

    wall = line((20, 50), (100, 50), "host", 10)
    opening = wall.model_copy(deep=True)
    opening.id = "opening"
    opening.kind = "door"
    opening.host_id = wall.id
    opening.height_m = 2.1
    document = Document(width=160, height=100, objects=[wall, opening])
    clean, _, svg = render(document, np.full((100, 160, 3), 255, np.uint8))
    assert np.all(clean == 255)
    assert "<svg" in svg
