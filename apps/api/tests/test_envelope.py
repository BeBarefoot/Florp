import cv2
import numpy as np
from app.envelope import building_envelope, mask_from_polygon
from app.ink_layers import wall_strips
from app.workspace_worker import build

H, W = 480, 800


def building(img, x1=150, y1=80, x2=560, y2=380, t=8):
    cv2.rectangle(img, (x1, y1), (x2, y2), (0, 0, 0), t)
    cv2.line(img, (330, y1), (330, y2), (0, 0, 0), t - 2)


def hatch(img, x1, y1, x2, y2):
    for k in range(x1 - (y2 - y1), x2, 6):
        cv2.line(img, (k, y2), (k + (y2 - y1), y1), (190, 190, 245), 1)
    m = np.full(img.shape[:2], False)
    m[y1:y2, x1:x2] = True
    return m


def scene():
    img = np.full((H, W, 3), 255, np.uint8)
    building(img)
    # site context: pink hatched terrace and a neighbour's wall fragment, dimension lines and text
    region = hatch(img, 600, 100, 780, 300)
    img[
        ~region
        & (img[:, :, 0] != 255)
        & (img[:, :, 2] == 245)
        & (np.arange(W)[None, :] > 590)
    ] = img[0, 0]
    cv2.rectangle(img, (40, 400), (120, 440), (0, 0, 0), 8)
    for x in range(150, 560, 16):
        cv2.line(img, (x, 40), (x + 8, 40), (0, 0, 255), 1)
    cv2.putText(img, "410", (330, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1)
    return img


def test_envelope_contains_only_the_building():
    img = scene()
    strips = wall_strips(img)
    polygon, mask = building_envelope(strips.mask, strips.stats["w_wall"])
    assert polygon is not None
    xs, ys = zip(*polygon)
    assert min(xs) >= 150 - 40 and max(xs) <= 560 + 40
    assert min(ys) >= 80 - 40 and max(ys) <= 380 + 40
    assert mask[230, 250] and mask[80, 300]
    assert not mask[420, 80]  # the neighbour's wall fragment is outside
    assert not mask[200, 700]  # terrace


def test_no_building_without_an_enclosed_room_sized_hole():
    strips = np.zeros((200, 300), np.uint8)
    cv2.line(strips, (20, 100), (260, 100), 255, 8)
    polygon, mask = building_envelope(strips, 8)
    assert polygon is None and mask.all()


def test_mask_from_polygon():
    m = mask_from_polygon([(10, 10), (50, 10), (50, 50), (10, 50)], (100, 100, 3))
    assert m[30, 30] and not m[70, 70]


def test_worker_ignores_marks_outside_the_building_and_reports_them(tmp_path):
    path = tmp_path / "plan.png"
    cv2.imwrite(str(path), scene())
    doc = build(path)
    walls = [o for o in doc.objects if o.kind == "wall"]
    assert doc.envelope
    assert all(
        max(o.start.x, o.end.x) <= 600 for o in walls
    )  # nothing from the terrace
    assert not any(
        o.start.y > 395 for o in walls
    )  # nothing from the neighbour's fragment
    assert any("outside the building" in w for w in doc.warnings)


def test_worker_honours_a_user_outline(tmp_path):
    path = tmp_path / "plan.png"
    cv2.imwrite(str(path), scene())
    doc = build(path, roi=[(20, 380), (200, 380), (200, 460), (20, 460)])
    walls = [o for o in doc.objects if o.kind == "wall"]
    assert walls and all(o.start.y > 370 and o.end.y > 370 for o in walls)


def test_open_envelope_keeps_a_side_wall_beyond_short_window_piers():
    mask = np.zeros((440, 1000), np.uint8)
    # Long roof/floor spans start to the right of the actual left boundary.
    cv2.rectangle(mask, (160, 75), (870, 85), 255, -1)
    cv2.rectangle(mask, (580, 425), (850, 438), 255, -1)
    # The left side has windows; short roof and floor piers still attach it.
    cv2.rectangle(mask, (85, 78), (101, 112), 255, -1)
    cv2.rectangle(mask, (85, 205), (98, 265), 255, -1)
    cv2.rectangle(mask, (85, 398), (98, 438), 255, -1)
    cv2.rectangle(mask, (90, 428), (151, 438), 255, -1)
    cv2.rectangle(mask, (847, 80), (860, 438), 255, -1)
    # Separate site leader does not have a horizontal architectural junction.
    cv2.rectangle(mask, (927, 0), (935, 410), 255, -1)
    polygon, region = building_envelope(mask, 7)
    assert polygon
    assert region[220, 90] and region[432, 90]
    assert not region[220, 930]


def test_band_crop_does_not_follow_disconnected_garden_context():
    mask = np.zeros((400, 1300), np.uint8)
    cv2.rectangle(mask, (250, 55), (1035, 66), 255, -1)
    cv2.rectangle(mask, (250, 390), (1010, 399), 255, -1)
    cv2.rectangle(mask, (250, 55), (262, 140), 255, -1)
    cv2.rectangle(mask, (250, 280), (262, 399), 255, -1)
    cv2.rectangle(mask, (730, 215), (1010, 228), 255, -1)
    cv2.rectangle(mask, (730, 215), (743, 399), 255, -1)
    cv2.rectangle(mask, (1040, 55), (1050, 175), 255, -1)
    cv2.rectangle(mask, (990, 55), (1050, 66), 255, -1)
    cv2.rectangle(mask, (20, 10), (90, 45), 255, 5)
    cv2.rectangle(mask, (1095, 0), (1100, 399), 255, -1)
    polygon, region = building_envelope(mask, 10)
    assert polygon and region[300, 256] and region[100, 1045]
    assert not region[25, 50] and not region[200, 1097]
