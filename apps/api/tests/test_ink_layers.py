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
    cv2.putText(
        img, "BEDROOM 4", (330, 180), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 2
    )
    s = wall_strips(img)
    assert covered(s.mask, 120, 80, 530, 88) > 0.95
    assert covered(s.mask, 301, 100, 304, 310) > 0.9
    assert (s.mask[195:206, 115:285] > 0).sum() == 0
    assert (s.mask[150:200, 320:520] > 0).sum() == 0
    assert len(s.stats["classes"]) >= 1


def test_photographed_faded_hatch_preserves_width_and_window_gap():
    img = canvas((175, 174, 177))
    hatch_band(img, 80, 140, 290, 154, step=7, color=(155, 151, 170))
    hatch_band(img, 355, 140, 570, 154, step=7, color=(155, 151, 170))
    # Soft photographic focus and a gradual illumination gradient.
    img = cv2.GaussianBlur(img, (3, 3), 0.6)
    gradient = np.linspace(0.85, 1.05, W)[None, :, None]
    img = np.clip(img * gradient, 0, 255).astype(np.uint8)
    s = wall_strips(img)
    assert covered(s.mask, 105, 143, 265, 151) > 0.75
    assert covered(s.mask, 380, 143, 545, 151) > 0.75
    assert covered(s.mask, 305, 140, 340, 154) < 0.1
    assert covered(s.mask, 105, 120, 265, 134) < 0.02
    assert covered(s.mask, 105, 162, 265, 175) < 0.02


def test_near_black_antialiasing_on_yellow_does_not_become_blue_ink():
    img = canvas((170, 235, 250))
    cv2.rectangle(img, (100, 80), (540, 90), (1, 0, 0), -1)
    cv2.rectangle(img, (300, 90), (305, 320), (0, 0, 1), -1)
    s = wall_strips(img)
    assert covered(s.dark, 120, 80, 530, 90) > 0.9
    assert covered(s.dark, 301, 110, 304, 310) > 0.9
    assert not s.blue.any()


def test_dark_navy_concrete_retains_its_material():
    img = canvas((180, 180, 180))
    cv2.rectangle(img, (100, 100), (520, 114), (100, 40, 20), -1)
    cv2.rectangle(img, (100, 100), (114, 320), (100, 40, 20), -1)
    s = wall_strips(img)
    assert covered(s.blue, 125, 102, 505, 112) > 0.8


def test_thin_partition_survives_beside_thick_walls():
    img = canvas()
    cv2.rectangle(img, (80, 70), (550, 84), (0, 0, 0), -1)
    cv2.rectangle(img, (80, 70), (94, 330), (0, 0, 0), -1)
    cv2.rectangle(img, (300, 84), (304, 330), (0, 0, 0), -1)
    cv2.line(img, (150, 220), (260, 220), (0, 0, 0), 1)
    s = wall_strips(img)
    assert covered(s.mask, 301, 110, 304, 310) > 0.8
    assert covered(s.mask, 160, 217, 250, 224) < 0.1
