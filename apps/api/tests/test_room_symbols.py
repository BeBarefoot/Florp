import cv2
import numpy as np

from app.deterministic_blueprint.preprocess import sharpen_soft_scan
from app.plan_model import ImageTransform, PlanModel, Pt, Room
from app.room_symbols import detect_symbols, tag_rooms


def drawing():
    a = np.full((250, 420, 3), 250, np.uint8)
    ink = (95, 95, 95)
    # Top-down sedan, separate roof glazing and outline.
    body = np.int32(
        [
            (36, 21),
            (59, 18),
            (80, 22),
            (84, 39),
            (84, 124),
            (80, 146),
            (35, 146),
            (30, 126),
            (30, 41),
        ]
    )
    cv2.polylines(a, [body], True, ink, 2)
    for y, dy in [(51, -9), (114, 7)]:
        cv2.polylines(
            a, [np.int32([(35, y), (45, y + dy), (69, y + dy), (79, y)])], False, ink, 2
        )
    for x, dx in [(35, 6), (79, -6)]:
        cv2.polylines(
            a,
            [np.int32([(x, 51), (x + dx, 61), (x + dx, 104), (x, 114)])],
            False,
            ink,
            2,
        )
    # A double bed drawn independently in native pixels.
    cv2.rectangle(a, (165, 59), (245, 167), ink, 2)
    for x in (171, 208):
        cv2.rectangle(a, (x, 65), (x + 29, 83), ink, 2)
    cv2.line(a, (166, 93), (244, 93), ink, 2)
    # Empty parking bay and ruled floor are negative examples.
    cv2.rectangle(a, (300, 40), (360, 180), ink, 2)
    for x in range(15, 120, 12):
        cv2.line(a, (x, 180), (x, 240), ink, 1)
    for y in range(180, 241, 12):
        cv2.line(a, (15, y), (115, y), ink, 1)
    return a


def test_sharpen_only_soft_edges_and_preserve_source():
    clear = drawing()
    assert sharpen_soft_scan(clear) is clear
    soft = cv2.GaussianBlur(clear, (0, 0), 1.8)
    original = soft.copy()
    sharp = sharpen_soft_scan(soft)
    assert np.array_equal(original, soft)
    assert sharp.shape == soft.shape
    assert (
        cv2.Laplacian(sharp, cv2.CV_32F).var() > cv2.Laplacian(soft, cv2.CV_32F).var()
    )
    blank = np.full_like(clear, 255)
    assert sharpen_soft_scan(blank) is blank


def test_symbol_recognition_across_orientation_blur_and_crop():
    image = drawing()
    for source in (
        image,
        cv2.rotate(image, cv2.ROTATE_90_CLOCKWISE),
        cv2.GaussianBlur(image, (0, 0), 1.5),
    ):
        assert sorted(s.kind for s in detect_symbols(sharpen_soft_scan(source))) == [
            "bed",
            "car",
        ]
    crop = [(130, 20), (280, 20), (280, 185), (130, 185)]
    assert [s.kind for s in detect_symbols(image, crop)] == ["bed"]


def test_only_unambiguous_enclosed_rooms_get_a_suggested_type():
    model = PlanModel(id="floor", image_transform=ImageTransform(width=420, height=250))

    def room(key, left, right):
        return Room(
            id=key,
            polygon=[
                Pt(x=x, y=y)
                for x, y in [(left, 5), (right, 5), (right, 176), (left, 176)]
            ],
            area_px2=(right - left) * 171,
        )

    symbols = detect_symbols(drawing())
    model.rooms = [room("sleep", 140, 270)]
    tag_rooms(model, symbols)
    assert (
        model.rooms[0].room_type == "bedroom" and model.rooms[0].needs_semantic_review
    )
    assert len(model.rooms) == 1 and len(model.room_symbols) == 2
    model.rooms = [
        room("enclosed", 10, 120),
        room("mixed", 0, 280),
        room("named", 140, 270),
    ]
    model.rooms[-1].label = "Study"
    tag_rooms(model, symbols)
    assert [r.label for r in model.rooms] == ["Garage", None, "Study"]


def test_blurred_upload_through_plan_extraction(tmp_path):
    from app.workspace_worker import build

    image = drawing()
    for left, right in [(10, 120), (140, 270)]:
        cv2.rectangle(image, (left, 6), (right, 175), (10, 10, 10), 7)
    path = tmp_path / "blurred.png"
    cv2.imwrite(str(path), cv2.GaussianBlur(image, (0, 0), 1.6))
    source = path.read_bytes()
    plan = build(path, plan_id="upload")
    saved = PlanModel.model_validate_json(plan.model_dump_json(by_alias=True))
    assert sorted(r.label for r in saved.rooms) == ["Bedroom", "Garage"]
    assert len(saved.room_symbols) == 2
    assert len(saved.walls) == 8
    assert any("sharpening" in note for note in saved.notes)
    assert path.read_bytes() == source
