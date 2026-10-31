import cv2
import numpy as np
from app.ink_layers import wall_strips
from app.openings import Box, detect, enumerate_gaps
from app.plan_reconstruct import reconstruct
from app.plan_workspace import Document, Point, Segment

W, H, T = 640, 420, 10


def wall(i, a, b, t=T):
    return Segment(id=f"w{i}", start=Point(x=a[0], y=a[1]), end=Point(x=b[0], y=b[1]), thickness_px=t)


def paint(img, walls):
    for w in walls:
        x1, x2 = sorted((w.start.x, w.end.x))
        y1, y2 = sorted((w.start.y, w.end.y))
        h = w.thickness_px / 2
        cv2.rectangle(img, (int(x1 - (h if x1 == x2 else 0)), int(y1 - (h if y1 == y2 else 0))),
                      (int(x2 + (h if x1 == x2 else 0)), int(y2 + (h if y1 == y2 else 0))), (0, 0, 0), -1)


def scene(walls, draw=lambda img: None):
    img = np.full((H, W, 3), 255, np.uint8)
    paint(img, walls)
    draw(img)
    return img, wall_strips(img)


def model(walls, found):
    passages = [Point(x=x, y=y) for x, y in found.passages]
    return reconstruct(Document(width=W, height=H, objects=walls + found.objects, passages=passages), "p")


def frame(*extra):
    """A room whose top wall has a gap handled by the caller; other sides solid."""
    return [wall(10, (400, 60), (400, 360)), wall(11, (80, 360), (400, 360)), wall(12, (80, 60), (80, 360)), *extra]


def test_drawn_door_gives_gap_span_hinge_swing_and_hosts_on_gap_wall():
    top = [wall(0, (80, 200), (250, 200)), wall(1, (330, 200), (400, 200))]
    walls = top + [wall(2, (330, 200), (330, 330)), wall(3, (250, 200), (250, 205))]  # a perpendicular stub
    walls = top + [wall(2, (400, 200), (400, 360))]

    def draw(img):
        cv2.ellipse(img, (250, 200), (80, 80), 0, 0, 90, (60, 60, 60), 1)  # arc from the closed to the open leaf
        cv2.line(img, (250, 205), (250, 280), (60, 60, 60), 1)  # open leaf

    img, strips = scene(walls, draw)
    found = detect(img, [w for w in walls], strips)
    doors = [o for o in found.objects if o.kind == "door"]
    assert len(doors) == 1
    d = doors[0]
    assert (d.start.x, d.end.x) == (250, 330)  # span is the gap, hinge at the start
    assert d.leaf.y > 0 and d.leaf.x == 0  # opens toward +y
    m = model(walls, found)
    o = next(o for o in m.openings if o.kind == "door")
    host = next(w for w in m.walls if w.id == o.host_wall_id)
    nodes = {n.id: n for n in m.nodes}
    assert nodes[host.a].y == nodes[host.b].y  # hosted on the horizontal wall, not the vertical one
    assert o.width_px == __import__("pytest").approx(80, abs=2)
    assert o.hinge == "start" and o.swing in ("left", "right")


def test_door_with_hinge_on_the_far_end():
    walls = [wall(0, (80, 200), (250, 200)), wall(1, (330, 200), (400, 200))]

    def draw(img):
        cv2.ellipse(img, (330, 200), (80, 80), 0, 90, 180, (60, 60, 60), 1)
        cv2.line(img, (330, 205), (330, 280), (60, 60, 60), 1)

    img, strips = scene(walls, draw)
    door = next(o for o in detect(img, walls, strips).objects if o.kind == "door")
    assert (door.start.x, door.end.x) == (330, 250)  # hinge first


def rails(img, y0, x1, x2):
    for y in (y0 - 3, y0, y0 + 3):
        cv2.line(img, (x1, y), (x2, y), (70, 70, 70), 1)


def test_window_rails_in_a_gap_give_a_window():
    walls = [wall(0, (80, 200), (200, 200)), wall(1, (280, 200), (400, 200))]
    img, strips = scene(walls, lambda im: rails(im, 200, 200, 280))
    found = detect(img, walls, strips)
    assert [o.kind for o in found.objects if o.kind != "wall"] == ["window"]
    assert not found.passages


def test_row_of_windows_with_piers_gives_separate_windows_and_keeps_piers():
    walls = [wall(0, (80, 200), (130, 200)), wall(1, (210, 200), (240, 200)), wall(2, (320, 200), (400, 200))]

    def draw(img):
        rails(img, 200, 130, 210)
        rails(img, 200, 240, 320)

    img, strips = scene(walls, draw)
    found = detect(img, walls, strips)
    windows = [o for o in found.objects if o.kind == "window"]
    assert len(windows) == 2
    m = model(walls, found)
    assert sum(o.kind == "window" for o in m.openings) == 2
    assert len(m.walls) == 1  # piers merge back into one wall carrying both windows


def test_yolo_door_box_in_mid_room_without_a_gap_places_nothing():
    walls = frame(wall(0, (80, 60), (400, 60)))
    img, strips = scene(walls)
    found = detect(img, walls, strips, [Box("door", 200, 150, 280, 240, 0.99)])
    assert found.objects == []


def test_plain_gap_is_an_open_passage_not_a_door():
    walls = [wall(0, (80, 200), (200, 200)), wall(1, (280, 200), (400, 200))]
    img, strips = scene(walls)
    found = detect(img, walls, strips)
    assert found.objects == [] and len(found.passages) == 1
    m = model(walls, found)
    assert any(f.category == "open_passage" and f.severity == "info" for f in m.findings)
    assert len(m.walls) == 2  # the gap is not bridged into wall


def test_yolo_agreement_raises_and_mismatch_lowers_confidence_but_never_changes_the_gap():
    walls = [wall(0, (80, 200), (200, 200)), wall(1, (280, 200), (400, 200))]
    img, strips = scene(walls, lambda im: rails(im, 200, 200, 280))
    base = next(o for o in detect(img, walls, strips).objects if o.kind == "window")
    agree = next(o for o in detect(img, walls, strips, [Box("window", 190, 170, 290, 230, 0.9)]).objects if o.kind == "window")
    clash = next(o for o in detect(img, walls, strips, [Box("door", 190, 150, 300, 260, 0.9)]).objects if o.kind == "window")
    assert agree.confidence > base.confidence > clash.confidence
    assert (clash.start.x, clash.end.x) == (200, 280)  # span stays the gap, not the box
    m = model(walls, detect(img, walls, strips, [Box("door", 190, 150, 300, 260, 0.9)]))
    assert next(o for o in m.openings if o.kind == "window").status == "proposed"


def test_wide_gap_on_exterior_wall_gives_a_proposed_garage_opening():
    walls = [wall(0, (80, 360), (150, 360)), wall(1, (350, 360), (400, 360)), wall(2, (80, 360), (80, 100))]

    def draw(img):
        for x in range(150, 350, 20):
            cv2.line(img, (x, 360), (x + 10, 360), (90, 90, 90), 1)

    img, strips = scene(walls, draw)
    exterior = np.ones((H, W), bool)
    found = detect(img, walls, strips, exterior=exterior)
    garage = [o for o in found.objects if o.kind == "garage"]
    assert len(garage) == 1
    m = model(walls, found)
    assert next(o for o in m.openings if o.kind == "garage").status == "proposed"
    # not on an exterior wall: plain passage
    assert [o for o in detect(img, walls, strips, exterior=np.zeros((H, W), bool)).objects if o.kind == "garage"] == []


def test_gap_enumeration_respects_size_limits():
    walls = [wall(0, (80, 200), (90, 200)), wall(1, (100, 200), (400, 200))]  # a gap of 10px = 1 thickness
    assert enumerate_gaps(walls, (H, W)) == []
