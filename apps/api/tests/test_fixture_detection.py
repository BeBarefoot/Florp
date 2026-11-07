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


def test_shadowed_blurred_photo_preserves_toilet_location_and_rejects_blank_paper():
    # Synthetic photo: uneven exposure, faint ink, optical blur and JPEG loss.
    y, x = np.indices((165, 220))
    paper = (35 + 110 * x / 220 + 8 * np.sin(y / 50)).astype(np.float32)
    glyph = cv2.rotate(stencil("toilet", 29, 40), cv2.ROTATE_90_CLOCKWISE)
    photo = paper.copy()
    photo[80:109, 60:100] *= 1 - glyph.astype(np.float32) / 255 * .15
    photo = cv2.GaussianBlur(photo, (0, 0), .6).astype(np.uint8)
    _, encoded = cv2.imencode('.jpg', photo, [cv2.IMWRITE_JPEG_QUALITY, 80])
    photo = cv2.imdecode(encoded, cv2.IMREAD_GRAYSCALE)
    hits = detect_fixtures(photo, 1 / 64)
    assert any(h.kind == 'toilet' and abs(h.x - 80) < 4 and abs(h.y - 95) < 4
               and h.rotation == 90 for h in hits)
    assert not detect_fixtures(paper.astype(np.uint8), 1 / 64)
