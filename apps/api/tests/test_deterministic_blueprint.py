from io import BytesIO
import asyncio
import json
import zipfile
import xml.etree.ElementTree as ET
import cv2
import numpy as np
from PIL import Image
import pytest
from fastapi.testclient import TestClient
from shapely.geometry import Polygon, box, Point
from shapely.ops import unary_union
from app.deterministic_blueprint import BlueprintEngine, Options, CalibrationReference
from app.deterministic_blueprint.schema import ExtractionError
from app.deterministic_blueprint.preprocess import normalize, transform_points, decode
from app.deterministic_blueprint.geometry import (
    contours_to_polygons,
    snap_ring,
    wall_masks,
    polygons,
)
from app.deterministic_blueprint.calibration import choose_scale, dimension_candidates
from app.deterministic_blueprint.export import normalize_metric, png


def plan(width=1600, height=1100):
    img = np.full((height, width, 3), 255, np.uint8)
    red = (100, 100, 200)
    cv2.rectangle(img, (150, 150), (width - 150, height - 150), red, 24)
    cv2.line(img, (width // 2, 150), (width // 2, height - 150), red, 20)
    cv2.line(img, (width // 2, height // 2), (width - 150, height // 2), red, 20)
    cv2.rectangle(img, (400, 130), (510, 170), (255, 255, 255), -1)
    cv2.line(img, (width - 150, 160), (width - 150, height - 160), (140, 75, 30), 24)
    cv2.putText(img, "500", (40, 80), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 0), 2)
    cv2.rectangle(img, (250, 300), (450, 420), (0, 0, 0), 2)
    cv2.circle(img, (70, height // 2), 35, (0, 230, 230), -1)
    return img, cv2.imencode(".png", img)[1].tobytes()


def configured(**kw):
    return Options(ocr=False, default_scale_px_per_cm=1.37, **kw)


def test_full_pipeline_outputs_and_exact_fractional_margin():
    _, data = plan()
    result = BlueprintEngine(configured()).process_bytes(data)
    b = result.report["bounds"]
    assert b["margin_working_px"] == pytest.approx(68.5)
    arch = unary_union(list(result.layers.values())).bounds
    view = result.bounds.bounds
    assert [
        arch[0] - view[0],
        arch[1] - view[1],
        view[2] - arch[2],
        view[3] - arch[3],
    ] == pytest.approx([50] * 4, abs=1e-8)
    with zipfile.ZipFile(BytesIO(result.archive)) as archive:
        assert set(archive.namelist()) == {
            "walls.png",
            "walls.svg",
            "walls.dxf",
            "report.json",
            "geometry.geojson",
        }
        svg = ET.fromstring(archive.read("walls.svg"))
        assert {
            "LAYER_WALLS_EXTERIOR",
            "LAYER_WALLS_INTERIOR",
            "LAYER_MAMAD_CONCRETE",
            "LAYER_50CM_BOUNDS",
        } <= {g.get("id") for g in svg.findall("{*}g")}
        assert Image.open(BytesIO(archive.read("walls.png"))).info[
            "dpi"
        ] == pytest.approx((300, 300), abs=0.01)
        assert b"\n$INSUNITS\n70\n4\n" in archive.read("walls.dxf")
        report = json.loads(archive.read("report.json"))
        assert "zip_encode" in report["timings_seconds"]
        assert report["accuracy_certified"] is False


@pytest.mark.parametrize("scale", [0.73, 1.37, 2.5137])
def test_50cm_all_four_bounds_not_an_interior_guideline(scale):
    layers = {"LAYER_WALLS_EXTERIOR": box(100.25, 200.75, 700.35, 900.65)}
    metric, bounds, meta = normalize_metric(layers, scale)
    x1, y1, x2, y2 = metric["LAYER_WALLS_EXTERIOR"].bounds
    assert (x1, y1) == pytest.approx((50, 50))
    assert bounds.bounds[2] - x2 == pytest.approx(50)
    assert bounds.bounds[3] - y2 == pytest.approx(50)
    original, viewport = (
        meta["architecture_working_bounds_px"],
        meta["viewport_working_bounds_px"],
    )
    assert [
        (original[0] - viewport[0]) / scale,
        (original[1] - viewport[1]) / scale,
        (viewport[2] - original[2]) / scale,
        (viewport[3] - original[3]) / scale,
    ] == pytest.approx([50] * 4)


def test_contour_holes_and_nested_island_not_filled():
    mask = np.zeros((200, 200), np.uint8)
    cv2.rectangle(mask, (10, 10), (190, 190), 255, -1)
    cv2.rectangle(mask, (30, 30), (170, 170), 0, -1)
    cv2.rectangle(mask, (80, 80), (120, 120), 255, -1)
    geometry = contours_to_polygons(mask)
    assert not geometry.contains(Point(50, 50))
    assert geometry.contains(Point(100, 100))
    assert sum(len(p.interiors) for p in polygons(geometry)) == 1


def test_opening_gap_black_and_yellow_furniture_not_wall():
    image, _ = plan()
    red, blue, _ = wall_masks(image, [], 1.37, np.eye(3), configured())
    assert red[150, 450] == 0
    assert not red[300:421, 250:451].any()
    assert not red[500:570, 35:105].any()
    assert blue[400, 1450] > 0


def test_outer_mode_removes_middle_partition():
    _, data = plan()
    all_walls = BlueprintEngine(configured()).process_bytes(data)
    outer = BlueprintEngine(configured(mode="outer_walls")).process_bytes(data)
    assert outer.layers["LAYER_WALLS_INTERIOR"].is_empty
    assert (
        unary_union(list(outer.layers.values())).area
        < unary_union(list(all_walls.layers.values())).area * 0.85
    )
    assert outer.report["classification"]["status"] == "inferred_verify"


def test_open_crop_never_uses_convex_hull_for_outer_shell():
    img = np.full((600, 800, 3), 255, np.uint8)
    cv2.line(img, (100, 100), (600, 100), (100, 100, 200), 20)
    cv2.line(img, (100, 100), (100, 450), (100, 100, 200), 20)
    data = cv2.imencode(".png", img)[1].tobytes()
    with pytest.raises(ExtractionError, match="enclosing perimeter"):
        BlueprintEngine(configured(mode="outer_walls")).process_bytes(data)
    result = BlueprintEngine(configured()).process_bytes(data)
    assert result.report["classification"]["status"] == "unresolved"
    assert "LAYER_WALLS_UNCLASSIFIED" in result.layers


def test_simultaneous_snap_closes_ring_and_preserves_diagonal():
    p = Polygon([(0.0, 0.0), (100.0, 1.0), (101.0, 80.0), (0.0, 80.0)])
    coords = snap_ring(p.exterior.coords, 5, 2)
    assert all(abs(dx) < 1e-8 or abs(dy) < 1e-8 for dx, dy in np.diff(coords, axis=0))
    assert np.array_equal(coords[0], coords[-1])
    triangle = Polygon([(0, 0), (50, 50), (0, 100)])
    assert np.allclose(
        snap_ring(triangle.exterior.coords, 5, 2), triangle.exterior.coords
    )


def test_user_reference_maps_after_resize():
    image = np.full((1000, 2000, 3), 255, np.uint8)
    options = Options(
        ocr=False,
        max_processing_side=1000,
        reference=CalibrationReference(
            start=(200, 400), end=(1200, 400), length_cm=500
        ),
    )
    working, matrix, _ = normalize(image, options)
    scale, report = choose_scale(working, matrix, [], options)
    assert scale == pytest.approx(1)
    assert report["source"] == "reference"


def test_perspective_requires_aspect_and_transforms_reference():
    image = np.full((600, 800, 3), 255, np.uint8)
    corners = [(80, 40), (740, 90), (680, 550), (40, 520)]
    with pytest.raises(ExtractionError, match="page_aspect_ratio"):
        normalize(image, Options(document_corners=corners))
    options = Options(
        document_corners=corners,
        page_aspect_ratio=1.4,
        reference=CalibrationReference(start=(200, 200), end=(600, 200), length_cm=400),
    )
    work, matrix, report = normalize(image, options)
    assert report["method"] == "homography"
    expected = transform_points(
        [options.reference.start, options.reference.end], matrix
    )
    scale, _ = choose_scale(work, matrix, [], options)
    assert scale == pytest.approx(np.linalg.norm(expected[1] - expected[0]) / 400)
    assert np.allclose(
        transform_points(transform_points(corners, matrix), np.linalg.inv(matrix)),
        corners,
    )
    with pytest.raises(ExtractionError, match="default source scale"):
        choose_scale(work, matrix, [], Options(ocr=False, default_scale_px_per_cm=1))


def test_no_scale_is_silently_guessed():
    with pytest.raises(ExtractionError, match="No unambiguous dimension"):
        choose_scale(
            np.full((300, 500, 3), 255, np.uint8), np.eye(3), [], Options(ocr=False)
        )


def test_witness_tick_scale_consensus_and_unpaired_numbers_rejected():
    image = np.full((500, 1000, 3), 255, np.uint8)
    words = []
    for idx, (left, right, value) in enumerate(
        [(100, 700, 600), (100, 500, 400), (100, 900, 800)]
    ):
        y = 100 + idx * 130
        cv2.line(image, (left, y), (right, y), (0, 0, 0), 2)
        for x in (left, right):
            cv2.line(image, (x, y - 12), (x, y + 12), (0, 0, 0), 2)
        center = (left + right) / 2
        words.append(
            {
                "text": str(value),
                "confidence": 95,
                "box": [center - 15, y - 30, center + 15, y - 15],
            }
        )
    assert len(dimension_candidates(image, words)) >= 3
    scale, report = choose_scale(image, np.eye(3), words, Options(ocr=False))
    assert scale == pytest.approx(1, abs=0.01)
    assert report["status"] == "provisional_verify_reference"
    assert dimension_candidates(np.full_like(image, 255), words) == []


def test_repeated_geometric_outputs_are_deterministic():
    _, data = plan()
    engine = BlueprintEngine(configured())
    first, second = engine.process_bytes(data), engine.process_bytes(data)
    for name in first.layers:
        assert first.layers[name].equals_exact(second.layers[name], 0)
    with (
        zipfile.ZipFile(BytesIO(first.archive)) as a,
        zipfile.ZipFile(BytesIO(second.archive)) as b,
    ):
        for name in ("walls.png", "walls.svg", "walls.dxf", "geometry.geojson"):
            assert a.read(name) == b.read(name)


@pytest.mark.parametrize("data", [b"", b"not a PNG", b"GIF89a123"])
def test_invalid_image_errors(data):
    with pytest.raises(ExtractionError):
        decode(data)


def test_white_transparency_not_black_ink():
    stream = BytesIO()
    Image.new("RGBA", (20, 20), (0, 0, 0, 0)).save(stream, format="PNG")
    assert np.all(decode(stream.getvalue()) == 255)


def test_gray_plan_fails_clearly_not_empty_cad():
    image = np.full((200, 300, 3), 255, np.uint8)
    cv2.rectangle(image, (20, 20), (250, 180), (0, 0, 0), 5)
    with pytest.raises(ExtractionError, match="Grayscale/faded"):
        BlueprintEngine(configured()).process_bytes(
            cv2.imencode(".png", image)[1].tobytes()
        )


def test_oversize_print_rejected_before_allocating():
    with pytest.raises(ExtractionError, match="exceeds 16MP"):
        png(
            {"LAYER_WALLS_EXTERIOR": box(50, 50, 50000, 50000)},
            box(0, 0, 50100, 50100),
            10,
        )


def test_roi_excludes_site_color():
    image, _ = plan()
    cv2.rectangle(image, (10, 10), (100, 100), (100, 100, 200), -1)
    red, _, _ = wall_masks(
        image,
        [],
        1.37,
        np.eye(3),
        configured(
            architecture_roi=[(120, 120), (1500, 120), (1500, 1000), (120, 1000)]
        ),
    )
    assert not red[:110, :110].any()


def test_service_health_validation_and_worker_result():
    from app.deterministic_blueprint.service import app

    _, data = plan()
    with TestClient(app) as client:
        assert client.get("/health").json()["downloads"] is False
        bad = client.post(
            "/extract",
            files={"file": ("p.png", data, "image/png")},
            data={"options": '{"default_scale_px_per_cm":0}'},
        )
        assert bad.status_code == 422
        result = client.post(
            "/extract",
            files={"file": ("p.png", data, "image/png")},
            data={"options": configured().model_dump_json()},
        )
        assert result.status_code == 200, (
            result.text[:200] if result.status_code != 200 else ""
        )
        assert float(result.headers["x-processing-seconds"]) < 4.8
        assert "walls.dxf" in zipfile.ZipFile(BytesIO(result.content)).namelist()


def test_service_deadline_kills_subprocess():
    from app.deterministic_blueprint import service

    async def scenario():
        _, data = plan()
        with pytest.raises(Exception) as error:
            await service.extract_with_deadline(data, configured(), 0.001)
        assert error.value.status_code == 504

    asyncio.run(scenario())


def test_service_saturation_returns_429():
    from app.deterministic_blueprint import service

    async def scenario():
        await service.slots.acquire()
        try:
            from starlette.datastructures import UploadFile

            with pytest.raises(Exception) as error:
                await service.extract(
                    UploadFile(file=BytesIO(b"test")), configured().model_dump_json()
                )
            assert error.value.status_code == 429
        finally:
            service.slots.release()

    asyncio.run(scenario())


def test_ocr_timeout_falls_back_to_explicit_scale(monkeypatch):
    from app.deterministic_blueprint import calibration

    monkeypatch.setattr(calibration, "installed_languages", lambda: {"eng"})

    def timeout(*args, **kwargs):
        raise RuntimeError("Tesseract timed out")

    monkeypatch.setattr(calibration.pytesseract, "image_to_data", timeout)
    _, data = plan()
    result = BlueprintEngine(Options(default_scale_px_per_cm=1)).process_bytes(data)
    assert any("ocr_failed_or_timed_out" in w for w in result.report["warnings"])
    assert result.report["calibration"]["source"] == "explicit_default"


def test_faded_hatching_fused_but_opening_not_closed():
    image = np.full((400, 700, 3), 255, np.uint8)
    # Pale red strips with darker red diagonal hatch seeds and boundary.
    for left, right in [(50, 290), (350, 650)]:
        cv2.rectangle(image, (left, 100), (right, 119), (171, 173, 190), -1)
        for x in range(left, right - 20, 8):
            cv2.line(image, (x, 119), (x + 19, 100), (100, 100, 160), 1)
    red, _, _ = wall_masks(image, [], 1.0, np.eye(3), configured())
    assert np.mean(red[105:115, 70:270] > 0) > 0.85
    assert not red[100:120, 300:340].any()


def test_auto_page_detection_avoids_interior_wall_rectangle():
    from app.deterministic_blueprint.preprocess import detect_page

    image, _ = plan()
    assert detect_page(image) is None
    photo = np.full((600, 800, 3), 40, np.uint8)
    corners = np.array([[80, 60], [740, 100], [700, 550], [50, 520]], np.int32)
    cv2.fillPoly(photo, [corners], (245, 245, 245))
    detected = detect_page(photo)
    assert detected is not None
    assert np.max(np.linalg.norm(detected - corners, axis=1)) < 6


def test_roi_invalid_polygon_is_rejected():
    image, _ = plan()
    with pytest.raises(ExtractionError, match="simple polygon"):
        wall_masks(
            image,
            [],
            1.0,
            np.eye(3),
            configured(architecture_roi=[(10, 10), (200, 200), (10, 200), (200, 10)]),
        )


def test_shared_materials_have_no_overlapping_output_area():
    image, data = plan()
    result = BlueprintEngine(configured()).process_bytes(data)
    red = unary_union(
        [g for name, g in result.layers.items() if name != "LAYER_MAMAD_CONCRETE"]
    )
    assert red.intersection(
        result.layers["LAYER_MAMAD_CONCRETE"]
    ).area == pytest.approx(0)
