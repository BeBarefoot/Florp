import cv2
import numpy as np

from app.fixture_detection import detect_fixtures, stencil


def test_symbol_scan_recognizes_a_rotated_toilet_and_blocks_stair_region():
    im = np.full((165, 220), 220, np.uint8)
    # A rotated double bowl near separate dimension strokes.
    glyph = cv2.rotate(stencil("toilet", 29, 40), cv2.ROTATE_90_CLOCKWISE)
    im[80:109, 60:100] -= glyph // 2
    cv2.line(im, (20, 25), (200, 25), 40, 1)
    cv2.line(im, (28, 20), (28, 145), 50, 1)
    hits = detect_fixtures(im, 1 / 64)
    toilet = next(hit for hit in hits if hit.kind == "toilet")
    assert abs(toilet.x - 80) < 4 and abs(toilet.y - 95) < 4
    assert toilet.rotation == 90
    blocked = np.zeros(im.shape, np.uint8)
    blocked[73:116, 53:107] = 1
    assert not any(h.kind == "toilet" and abs(h.x - 80) < 10 and abs(h.y - 95) < 10
                   for h in detect_fixtures(im, 1 / 64, obstacle=blocked))
    assert not detect_fixtures(np.full_like(im, 220), 1 / 64)
