import cv2
import numpy as np
import pytest
from app.ink_layers import wall_strips
from app.openings import Box, Gap, _photo_end_gaps, _photo_frame_confidence, _photo_mixed_returns, _rails, detect, enumerate_gaps
from app.plan_reconstruct import reconstruct
from app.plan_workspace import Document, Point, Segment

W, H, T = 640, 420, 10


def wall(i, a, b, t=T):
    return Segment(
        id=f"w{i}",
        start=Point(x=a[0], y=a[1]),
        end=Point(x=b[0], y=b[1]),
        thickness_px=t,
    )


def paint(img, walls):
    for w in walls:
        x1, x2 = sorted((w.start.x, w.end.x))
        y1, y2 = sorted((w.start.y, w.end.y))
        h = w.thickness_px / 2
        cv2.rectangle(
            img,
            (int(x1 - (h if x1 == x2 else 0)), int(y1 - (h if y1 == y2 else 0))),
            (int(x2 + (h if x1 == x2 else 0)), int(y2 + (h if y1 == y2 else 0))),
            (0, 0, 0),
            -1,
        )


def scene(walls, draw=lambda img: None):
    img = np.full((H, W, 3), 255, np.uint8)
    paint(img, walls)
    draw(img)
    return img, wall_strips(img)


def model(walls, found):
    passages = [Point(x=x, y=y) for x, y in found.passages]
    return reconstruct(
        Document(width=W, height=H, objects=walls + found.objects, passages=passages),
        "p",
    )


def frame(*extra):
    """A room whose top wall has a gap handled by the caller; other sides solid."""
    return [
        wall(10, (400, 60), (400, 360)),
        wall(11, (80, 360), (400, 360)),
        wall(12, (80, 60), (80, 360)),
        *extra,
    ]


@pytest.mark.parametrize("tone", [60, 222])
def test_drawn_door_gives_gap_span_hinge_swing_and_hosts_on_gap_wall(tone):
    top = [wall(0, (80, 200), (250, 200)), wall(1, (330, 200), (400, 200))]
    walls = top + [
        wall(2, (330, 200), (330, 330)),
        wall(3, (250, 200), (250, 205)),
    ]  # a perpendicular stub
    walls = top + [wall(2, (400, 200), (400, 360))]

    def draw(img):
        cv2.ellipse(
            img, (250, 200), (80, 80), 0, 0, 90, (tone, tone, tone), 1
        )  # arc from the closed to the open leaf
        cv2.line(img, (250, 205), (250, 280), (tone, tone, tone), 1)  # open leaf

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
    assert (
        nodes[host.a].y == nodes[host.b].y
    )  # hosted on the horizontal wall, not the vertical one
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
    walls = [
        wall(0, (80, 200), (130, 200)),
        wall(1, (210, 200), (240, 200)),
        wall(2, (320, 200), (400, 200)),
    ]

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
    assert any(
        f.category == "open_passage" and f.severity == "info" for f in m.findings
    )
    assert len(m.walls) == 2  # the gap is not bridged into wall


def test_yolo_agreement_raises_and_mismatch_lowers_confidence_but_never_changes_the_gap():
    walls = [wall(0, (80, 200), (200, 200)), wall(1, (280, 200), (400, 200))]
    img, strips = scene(walls, lambda im: rails(im, 200, 200, 280))
    base = next(o for o in detect(img, walls, strips).objects if o.kind == "window")
    agree = next(
        o
        for o in detect(
            img, walls, strips, [Box("window", 190, 170, 290, 230, 0.9)]
        ).objects
        if o.kind == "window"
    )
    clash = next(
        o
        for o in detect(
            img, walls, strips, [Box("door", 190, 150, 300, 260, 0.9)]
        ).objects
        if o.kind == "window"
    )
    assert agree.confidence > base.confidence > clash.confidence
    assert (clash.start.x, clash.end.x) == (200, 280)  # span stays the gap, not the box
    m = model(walls, detect(img, walls, strips, [Box("door", 190, 150, 300, 260, 0.9)]))
    assert next(o for o in m.openings if o.kind == "window").status == "proposed"


def test_wide_gap_on_exterior_wall_gives_a_proposed_garage_opening():
    walls = [
        wall(0, (80, 360), (150, 360)),
        wall(1, (350, 360), (400, 360)),
        wall(2, (80, 360), (80, 100)),
    ]

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
    assert [
        o
        for o in detect(img, walls, strips, exterior=np.zeros((H, W), bool)).objects
        if o.kind == "garage"
    ] == []


def test_gap_enumeration_respects_size_limits():
    walls = [
        wall(0, (80, 200), (90, 200)),
        wall(1, (100, 200), (400, 200)),
    ]  # a gap of 10px = 1 thickness
    assert enumerate_gaps(walls, (H, W)) == []


def test_wide_blank_exterior_gap_is_not_invented_as_a_garage():
    walls = [wall(0, (80, 360), (150, 360)), wall(1, (350, 360), (400, 360))]
    img, strips = scene(walls)
    found = detect(img, walls, strips, exterior=np.ones((H, W), bool))
    assert not found.objects
    assert len(found.passages) == 1


def test_photo_frame_confirmation_requires_two_continuous_rails_and_clear_core():
    ink = np.zeros((100, 170), dtype=bool)
    colour = np.zeros_like(ink)
    gap = Gap(True, 50, 30, 140, 14)
    ink[46, 30:140] = True
    ink[54, 30:89] = True
    assert _photo_frame_confidence(ink, gap, .74, colour) == .74
    ink[54, 89:140] = True
    assert _photo_frame_confidence(ink, gap, .74, colour) > .85
    colour[49:52, 30:140] = True
    assert _photo_frame_confidence(ink, gap, .74, colour) == .74


def test_half_open_diagonal_leaf_is_a_door_with_the_same_physical_gap():
    walls = [wall(0, (80, 200), (250, 200)), wall(1, (330, 200), (400, 200))]

    def draw(im):
        cv2.ellipse(im, (250, 200), (80, 80), 0, 0, 45, (60, 60, 60), 1)
        cv2.line(im, (250, 200), (307, 257), (60, 60, 60), 1)

    image, strips = scene(walls, draw)
    doors = [o for o in detect(image, walls, strips).objects if o.kind == "door"]
    assert len(doors) == 1
    assert (doors[0].start.x, doors[0].end.x) == (250, 330)
    assert doors[0].leaf.y > 0



def test_photo_opening_between_parallel_jamb_ends():
    # The ends line up in X; the clear opening extends along Y between faces.
    jambs = [wall(0, (120, 100), (200, 100), 6), wall(1, (120, 150), (200, 150), 10)]
    assert Gap(False, 200, 103, 145, 10) in _photo_end_gaps(jambs, (H, W))

    # Transpose the plan to exercise the horizontal doorway as well.
    jambs = [wall(0, (100, 120), (100, 200), 6), wall(1, (150, 120), (150, 200), 10)]
    assert Gap(True, 200, 103, 145, 10) in _photo_end_gaps(jambs, (H, W))



def test_mixed_return_door_spans_tip_to_opposing_face():
    walls = [wall(0, (200, 90), (200, 113), 6), wall(1, (120, 160), (200, 160), 10)]
    assert Gap(False, 200, 113, 155, 6, door_only=True) in _photo_mixed_returns(walls, (H, W))


def test_photo_rails_reject_repeated_shelf_crossbars():
    gap = Gap(True, 20, 5, 105, 10)
    ink = np.zeros((40, 120), dtype=bool)
    ink[16, 5:106] = ink[24, 5:106] = True
    assert _rails(ink, gap, reject_rungs=True)[0] == 2
    ink[17:24, 10:105:8] = True
    assert _rails(ink, gap, reject_rungs=True)[0] < 2


def test_photo_swing_can_use_leaf_missing_from_wall_filtered_ink():
    from app.openings import _photo_door

    arc = np.zeros((140, 140), dtype=np.uint8)
    cv2.ellipse(arc, (60, 50), (36, 45), 0, 0, 90, 1, 3)
    unmasked = arc.copy()
    cv2.line(unmasked, (60, 51), (60, 94), 1, 3)
    gap = Gap(True, 50, 60, 96, 8)
    assert _photo_door(arc > 0, gap) is None
    swing = _photo_door(arc > 0, gap, unmasked > 0)
    assert swing is not None and swing[3:] == (True, 1)


def test_photo_window_rejects_masonry_core_offset_from_centreline():
    from app.openings import _photo_window_clear

    material = np.zeros((80, 100), dtype=bool)
    gap = Gap(False, 30, 15, 65, 12)
    material[15:66, 25:27] = True
    assert not _photo_window_clear(material, gap)
    material[15:66, 25:27] = False
    material[15:20, 25:27] = True
    assert _photo_window_clear(material, gap)


def test_long_glazing_separated_by_an_opaque_mark():
    from app.openings import _long_glazing

    image = np.full((150, 600, 3), 230, np.uint8)
    colour = np.zeros((150, 600), bool)
    for a, b in [(20, 50), (280, 305)]:
        colour[52:63, a : b + 1] = True
    for y in (55, 62):
        cv2.line(image, (50, y), (280, y + 1), (50, 50, 50), 1)
    image[49:65, 145:172] = (55, 180, 190)
    gaps = _long_glazing(image, [(True, 58, [(20, 50, 10), (280, 305, 10)])], colour)
    assert len(gaps) == 2
    assert gaps[0].lo == 50 and gaps[0].hi <= 146
    assert gaps[1].lo >= 170 and gaps[1].hi == 280

def test_coarse_photo_gap_does_not_hide_two_supported_windows():
    image = np.full((150, 600, 3), 230, np.uint8)
    colour = np.zeros(image.shape[:2], dtype=bool)
    colour[53:64, 20:51] = True
    colour[53:64, 210:236] = True
    for y in (55, 62):
        cv2.line(image, (50, y), (210, y), (50, 50, 50), 1)
    image[49:65, 117:143] = (55, 180, 190)
    strips = wall_strips(image)
    strips.stats["coloured_walls"] = True
    strips.structural_colour = colour
    walls = [wall(0, (20, 58), (50, 58)), wall(1, (210, 58), (235, 58))]
    windows = sorted(
        (opening for opening in detect(image, walls, strips).objects if opening.kind == "window"),
        key=lambda opening: opening.start.x,
    )
    assert len(windows) == 2
    assert windows[0].end.x <= 117
    assert windows[1].start.x >= 143


def test_photo_crop_does_not_treat_hatched_edge_as_glazing():
    from app.openings import _cropped_material_band

    image = np.full((100, 160, 3), 220, np.uint8)
    gap = Gap(True, 97, 20, 110, 12)
    image[94:100, 15:115] = (120, 123, 151)
    image[:, ::5] = 100
    assert _cropped_material_band(image, gap)
    image[94:100, 15:115] = 210
    assert not _cropped_material_band(image,gap)


def test_pale_door_swing_on_wall_face_retains_jamb_span():
    walls = frame(wall(0, (80, 60), (250, 60), 20), wall(1, (330, 60), (400, 60), 20))
    image = np.full((H, W, 3), 251, np.uint8)
    for segment in walls:
        a, b = segment.start, segment.end
        if a.y == b.y:
            points = ((round(a.x), round(a.y-10)), (round(b.x), round(b.y+10)))
        else:
            points = ((round(a.x-5), round(a.y)), (round(b.x+5), round(b.y)))
        cv2.rectangle(image, *points, (195, 195, 195), -1)
    cv2.ellipse(image, (250, 70), (80, 80), 0, 0, 90, (220, 220, 220), 2)
    cv2.line(image, (250, 70), (250, 150), (220, 220, 220), 2)
    image = cv2.GaussianBlur(image, (0, 0), 1)
    strips = wall_strips(image)
    assert strips.stats.get("neutral_wall_bands")
    found = detect(image, walls, strips)
    door, = [o for o in found.objects if o.kind == "door"]
    assert (door.start.x, door.end.x, door.start.y) == (250, 330, 60)


@pytest.mark.parametrize("angle,wall_width", [(0, 54), (45, 15)])
def test_pale_doors_between_facing_jambs_preserve_span(angle, wall_width):
    from app.openings import Result, _pale_doors

    start = np.array([210., 150.])
    radians = np.deg2rad(angle)
    direction = np.array([np.cos(radians), np.sin(radians)])
    normal = np.array([-direction[1], direction[0]])
    width = 70
    end = start + width * direction
    walls = [
        wall(0, start - 90 * direction, start, wall_width),
        wall(1, end, end + 90 * direction, wall_width),
    ]
    material = np.zeros((350, 440), np.uint8)
    for segment in walls:
        a, b = segment.start, segment.end
        # Butt caps retain the actual wall tips, unlike cv2.line's round cap.
        p, q = np.array([a.x, a.y]), np.array([b.x, b.y])
        d = normal * wall_width / 2
        cv2.fillConvexPoly(material, np.int32([p-d,q-d,q+d,p+d]), 1)
    ink = np.zeros_like(material)
    sweep = np.linspace(0, np.pi/2, 75)
    arc = start + width * (np.cos(sweep)[:,None]*direction + np.sin(sweep)[:,None]*normal)
    cv2.polylines(ink, [np.rint(arc).astype(np.int32)], False, 1, 2)
    cv2.line(ink, tuple(start.astype(int)), tuple(np.rint(start + width*normal).astype(int)), 1, 2)
    host, door = _pale_doors(walls, material, ink, [], 0)
    assert door.host_id == host.id and door.uncertain
    assert (door.start.x, door.start.y) == pytest.approx(start)
    assert (door.end.x, door.end.y) == pytest.approx(end)
    rebuilt = model(walls, Result(objects=[host, door]))
    opening, = rebuilt.openings
    assert opening.host_wall_id is not None
    assert opening.width_px == pytest.approx(width)
    assert opening.status == "proposed"
    assert _pale_doors(walls, material, ink, [door], 0) == []
    assert _pale_doors(walls, material, np.zeros_like(ink), [], 0) == []
    cv2.line(material, tuple(start.astype(int)), tuple(np.rint(end).astype(int)), 1, wall_width)
    assert _pale_doors(walls, material, ink, [], 0) == []


def test_soft_neutral_facade_separates_window_frame_from_balcony_door():
    image = np.full((360, 440, 3), 252, np.uint8)
    for start, end in [
        ((45, 69), (104, 81)),
        ((158, 69), (199, 81)),
        ((236, 69), (391, 81)),
        ((45, 69), (56, 310)),
        ((380, 69), (391, 310)),
        ((45, 299), (391, 310)),
    ]:
        cv2.rectangle(image, start, end, (215,) * 3, -1)
        cv2.rectangle(image, start, end, (158,) * 3, 1)
    # Drafted faces run across the door, but only the window has internal rails.
    for y in (69, 81):
        cv2.line(image, (104, y), (236, y), (165,) * 3, 1)
    for y in (74, 76):
        cv2.line(image, (104, y), (158, y), (95,) * 3, 1)
    cv2.ellipse(image, (235, 75), (35, 35), 0, 90, 180, (140,) * 3, 1, cv2.LINE_AA)
    cv2.line(image, (235, 75), (235, 110), (140,) * 3, 1, cv2.LINE_AA)
    image = cv2.GaussianBlur(image, (0, 0), 0.55)

    # The initial wall scan merged the narrow window into the upper wall.
    walls = [
        wall(0, (50, 75), (199, 75), 12),
        wall(1, (236, 75), (385, 75), 12),
        wall(2, (50, 75), (50, 304), 11),
        wall(3, (385, 75), (385, 304), 11),
        wall(4, (50, 304), (385, 304), 11),
    ]
    strips = wall_strips(image)
    assert strips.stats["neutral_wall_bands"]
    detected = detect(image, walls, strips)
    door, = [item for item in detected.objects if item.kind == "door"]
    window, = [item for item in detected.objects if item.kind == "window"]
    assert sorted((door.start.x, door.end.x)) == pytest.approx([200, 235], abs=3)
    assert sorted((window.start.x, window.end.x)) == pytest.approx([104, 158], abs=3)


def test_double_swing_uses_inside_leaf_without_changing_the_measured_span():
    from shapely.geometry import box
    from app.openings import _interior_leaf

    outward = (1.75, np.array([30, 80]), np.array([55, 80]), np.array([0, 1]))
    inward = (1.73, np.array([30, 81]), np.array([55, 81]), np.array([0, -1]))
    footprint = box(0, 0, 100, 82)
    assert np.array_equal(_interior_leaf(outward, [outward], footprint), outward[-1])
    assert np.array_equal(_interior_leaf(outward, [outward, inward], footprint), inward[-1])
