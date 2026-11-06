import cv2
import numpy as np

from app.stair_detection import detect_stairs


def drawing(turn=True, double=False):
    image = np.full((440, 700, 3), 234, np.uint8)

    def line(a, b):
        cv2.line(image, a, b, (58, 58, 58), 2)

    for x in (200, 260):
        line((x, 210), (x, 300))
    for y in range(210, 301, 15):
        line((200, y), (260, y))
    for y in (300, 360):
        line((260, y), (320, y))
    for x in range(260, 321, 15):
        line((x, 300), (x, 360))
    if turn:
        line((200, 300), (200, 360))
        line((200, 360), (260, 360))
        line((260, 300), (200, 360))
    if double:
        for x in (320, 380):
            line((x, 225), (x, 300))
        for y in range(225, 301, 15):
            line((320, y), (380, y))
        line((380, 300), (380, 360))
        line((320, 360), (380, 360))
        line((320, 300), (380, 360))
    return image


def test_turning_stairs_have_connected_flights_and_winders():
    for double, layout, winders in [(False, "l", 2), (True, "u", 4)]:
        stairs = detect_stairs(drawing(double=double))
        assert len(stairs) == 1
        assert stairs[0].layout == layout
        assert sum(len(t) == 3 for t in stairs[0].treads) == winders
        # Every step meets its next neighbor along a complete edge.
        for a, b in zip(stairs[0].treads, stairs[0].treads[1:]):
            assert len({(p.x, p.y) for p in a} & {(p.x, p.y) for p in b}) == 2


def test_regular_lines_without_turn_evidence_are_not_stairs():
    assert detect_stairs(drawing(turn=False)) == []
