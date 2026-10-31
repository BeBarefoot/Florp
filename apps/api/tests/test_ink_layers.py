import cv2
import numpy as np
from app.ink_layers import wall_strips

W, H = 640, 400


def canvas(color=(255, 255, 255)):
    return np.full((H, W, 3), color, np.uint8)


def hatch_band(img, x1, y1, x2, y2, step=6, color=(190, 190, 245), outline=True):
    """Pale diagonal hatch between two dark outlines (a drawn wall)."""
    band = np.zeros(img.shape[:2], np.uint8)
    for k in range(-H, W + H, step):
        cv2.line(band, (k, 0), (k - H, H), 255, 1)
    m = np.zeros_like(band)
    m[y1:y2, x1:x2] = 255
    img[(band > 0) & (m > 0)] = color
    if outline:
        cv2.rectangle(img, (x1, y1), (x2 - 1, y2 - 1), (40, 40, 40), 1)


def covered(mask, x1, y1, x2, y2):
    return (mask[y1:y2, x1:x2] > 0).mean()


def test_hatched_wall_between_outlines_is_a_strip_and_dimension_marks_are_not():
    img = canvas()
    hatch_band(img, 100, 100, 500, 112)
    hatch_band(img, 100, 100, 112, 300)
    # red dashed dimension line + red digits
    for x in range(100, 520, 14):
        cv2.line(img, (x, 60), (x + 7, 60), (0, 0, 255), 1)
    cv2.putText(img, "500", (260, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1)
    cv2.line(img, (100, 52), (100, 68), (0, 0, 255), 1)
    cv2.line(img, (500, 52), (500, 68), (0, 0, 255), 1)
    s = wall_strips(img)
    mask = s.mask
    assert covered(mask, 120, 101, 490, 111) > 0.9
    assert covered(mask, 101, 120, 111, 290) > 0.9
    assert (mask[30:75, :] > 0).sum() == 0


def test_pale_hatch_without_saturated_seed_is_accepted():
    img = canvas()
    hatch_band(img, 80, 150, 560, 164, color=(225, 215, 250))
    s = wall_strips(img)
    assert covered(s.mask, 100, 152, 540, 162) > 0.85


def test_hatched_terrain_without_outline_is_rejected():
    img = canvas()
    hatch_band(img, 100, 100, 500, 112)
    hatch_band(img, 100, 100, 112, 300)
    hatch_band(img, 300, 200, 560, 340, outline=False)  # terrace / garden hatching
    s = wall_strips(img)
    assert (s.mask[210:330, 320:550] > 0).sum() == 0
    assert covered(s.mask, 120, 101, 490, 111) > 0.9


def test_black_walls_of_two_thicknesses_on_room_fill_and_single_stroke_beam_rejected():
    img = canvas((170, 235, 250))  # yellow room fill is paper, not ink
    cv2.rectangle(img, (100, 80), (540, 88), (0, 0, 0), -1)  # exterior, 9px
    cv2.rectangle(img, (100, 80), (108, 320), (0, 0, 0), -1)
    cv2.rectangle(img, (300, 88), (305, 320), (0, 0, 0), -1)  # interior partition, 6px
    cv2.line(img, (120, 200), (280, 200), (0, 0, 0), 1)  # decorative beam, one stroke
    cv2.putText(img, "BEDROOM 4", (330, 180), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 2)
    s = wall_strips(img)
    assert covered(s.mask, 120, 80, 530, 88) > 0.95
    assert covered(s.mask, 301, 100, 304, 310) > 0.9
    assert (s.mask[195:206, 115:285] > 0).sum() == 0
    assert (s.mask[150:200, 320:520] > 0).sum() == 0
    assert len(s.stats["classes"]) >= 1
