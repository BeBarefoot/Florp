import math
from app.plan_workspace import Document, Segment, Point
from app.plan_reconstruct import reconstruct


def seg(i, a, b, t=10, **kw):
    return Segment(
        id=f"s{i}",
        start=Point(x=a[0], y=a[1]),
        end=Point(x=b[0], y=b[1]),
        thickness_px=t,
        **kw,
    )


def build(objects, w=800, h=600):
    return reconstruct(Document(width=w, height=h, objects=objects), "plan")


def degree(model):
    d = {}
    for w in model.walls:
        d[w.a] = d.get(w.a, 0) + 1
        d[w.b] = d.get(w.b, 0) + 1
    return d


def rectangle(extra=()):
    edges = [
        ((100, 100), (700, 100)),
        ((700, 100), (700, 500)),
        ((700, 500), (100, 500)),
        ((100, 500), (100, 100)),
    ]
    return [seg(i, a, b) for i, (a, b) in enumerate(edges)] + list(extra)


def test_overlapping_fragments_merge_but_unclassified_gap_stays_open():
    model = build(
        [
            seg(0, (100, 100), (250, 100)),
            seg(1, (245, 101), (420, 100)),
            seg(2, (428, 99), (600, 100)),
        ]
    )
    assert len(model.walls) == 2
    nodes = {n.id: n for n in model.nodes}
    spans = sorted(
        (min(nodes[w.a].x, nodes[w.b].x), max(nodes[w.a].x, nodes[w.b].x))
        for w in model.walls
    )
    assert spans[0][1] < spans[1][0]
    assert any(f.category == "merged_duplicates" for f in model.findings)


def test_near_straight_run_is_straightened():
    model = build([seg(0, (100, 100), (500, 100 + 400 * math.tan(math.radians(1.5))))])
    nodes = {n.id: n for n in model.nodes}
    w = model.walls[0]
    assert nodes[w.a].y == nodes[w.b].y


def test_photo_reconstruction_removes_orphans_but_keeps_physical_walls():
    objects = rectangle([
        seg(10, (250, 250), (320, 250)),  # detached dimension leader
        seg(11, (360, 220), (380, 220), t=6, boundary_supported=True),  # short glyph
        seg(12, (710, 100), (740, 100), t=6),  # measured continuation across a narrow seam
        seg(13, (350, 50), (435, 50), t=6, boundary_supported=True),  # isolated even with paired ink
        seg(14, (320, 520), (380, 520), t=8, boundary_supported=True).model_copy(
            update={"id": "gap-host-orphan"}
        ),
        seg(15, (320, 520), (380, 520), kind="window", host_id="gap-host-orphan",
            confidence=0.95, boundary_supported=True, height_m=1.2),
        seg(16, (350, 100), (395, 100), kind="door", confidence=0.95, height_m=2.1),
    ])
    doc = Document(width=800, height=600, objects=objects)
    original = reconstruct(doc, "plan")
    fixed = reconstruct(doc.model_copy(update={"photo_wall_evidence": True}), "plan")
    assert len(original.walls) - len(fixed.walls) == 4
    assert {n.y for n in fixed.nodes}.isdisjoint({50, 220, 250, 520})
    assert any(n.x == 740 and n.y == 100 for n in fixed.nodes)
    pier = next(n for n in fixed.nodes if n.x == 740 and n.y == 100)
    wall = next(w for w in fixed.walls if pier.id in (w.a, w.b))
    assert max(degree(fixed)[wall.a], degree(fixed)[wall.b]) >= 2
    assert [o.kind for o in fixed.openings] == ["door"]
    assert len(fixed.rooms) == 1


def test_photo_clutter_cannot_outvote_the_connected_building():
    clutter = [
        seg(i + 10, (140, y), (660, y), t=6, boundary_supported=True)
        for i, y in enumerate((20, 40, 60, 80, 520, 540, 560, 580))
    ]
    doc = Document(width=800, height=600, objects=rectangle(clutter), photo_wall_evidence=True)
    model = reconstruct(doc, "plan")
    assert len(model.walls) == 4
    assert len(model.rooms) == 1


def test_photo_broken_traced_corner_is_joined_instead_of_deleted():
    arms = [
        seg(10, (221, 230), (500, 230), t=12, boundary_supported=True),
        seg(11, (201, 237), (201, 400), t=20, boundary_supported=True),
    ]
    doc = Document(width=800, height=600, objects=rectangle(arms))
    original = reconstruct(doc, "plan")
    assert sum(degree(original)[w.a] == degree(original)[w.b] == 1 for w in original.walls) == 2
    fixed = reconstruct(doc.model_copy(update={"photo_wall_evidence": True}), "plan")
    assert len(fixed.walls) == 6
    corner = next(n for n in fixed.nodes if (n.x, n.y) == (201, 230))
    assert degree(fixed)[corner.id] == 2


def test_l_corners_and_t_junction_share_nodes():
    # Corners are short of each other (gaps of a few px), plus an interior T stem.
    edges = [
        ((104, 100), (700, 100)),
        ((700, 104), (700, 500)),
        ((697, 500), (100, 500)),
        ((100, 497), (100, 103)),
        ((400, 105), (400, 495)),
    ]
    model = build([seg(i, a, b) for i, (a, b) in enumerate(edges)])
    deg = degree(model)
    assert len(model.nodes) == 6
    assert sorted(deg.values()) == [2, 2, 2, 2, 3, 3]
    assert len(model.walls) == 7  # the top and bottom walls are split at the T stem
    assert len(model.rooms) == 2


def test_dangling_stub_is_pruned_and_reported_once():
    model = build(
        rectangle([seg(9, (300, 300), (310, 300)), seg(10, (500, 300), (511, 300))])
    )
    assert len(model.walls) == 4
    pruned = [f for f in model.findings if f.category == "pruned_fragments"]
    assert len(pruned) == 1 and pruned[0].count == 2


def test_door_gap_merges_host_and_span_is_the_gap_not_swing_box():
    walls = [
        seg(0, (100, 100), (300, 100)),
        seg(1, (380, 100), (700, 100)),
        seg(2, (700, 100), (700, 500)),
        seg(3, (700, 500), (100, 500)),
        seg(4, (100, 500), (100, 100)),
    ]
    # The detector box includes the swing arc, so its along-wall extent is wider than the gap.
    door = seg(
        9,
        (292, 100),
        (388, 100),
        kind="door",
        uncertain=True,
        confidence=0.95,
        height_m=2.1,
    )
    model = build(walls + [door])
    assert len(model.walls) == 4
    o = model.openings[0]
    assert o.host_wall_id is not None
    assert o.width_px == __import__("pytest").approx(80, abs=1)
    assert o.status == "confirmed"


def test_uncertain_openings_stay_proposed_for_user_approval():
    window = seg(
        9,
        (200, 100),
        (260, 100),
        kind="window",
        uncertain=True,
        confidence=0.6,
        height_m=1.2,
        sill_m=0.9,
    )
    floating = seg(
        10, (300, 300), (350, 300), kind="door", uncertain=True, confidence=0.99
    )
    model = build(rectangle([window, floating]))
    by_id = {o.id: o for o in model.openings}
    hosted = next(o for o in model.openings if o.kind == "window")
    unhosted = next(o for o in model.openings if o.kind == "door")
    assert hosted.status == "proposed" and hosted.host_wall_id
    assert unhosted.status == "proposed" and unhosted.host_wall_id is None
    approvals = [f for f in model.findings if f.category == "opening_needs_approval"]
    assert sorted(t for f in approvals for t in f.target_ids) == sorted(by_id)


def test_isolated_diagonal_evidence_is_retained(tmp_path):
    import cv2, numpy as np
    from app.workspace_worker import build as worker

    image = np.full((400, 500, 3), 255, np.uint8)
    cv2.line(image, (70, 70), (350, 320), (100, 100, 200), 12)
    file = tmp_path / "diagonal.png"
    cv2.imwrite(str(file), image)
    doc = worker(file)
    assert any(o.id.startswith("diagonal-") for o in doc.objects)
    model = reconstruct(doc, "plan")
    nodes = {n.id: n for n in model.nodes}
    assert any(
        abs(nodes[w.b].x - nodes[w.a].x) > 100
        and abs(nodes[w.b].y - nodes[w.a].y) > 100
        for w in model.walls
    )


def test_cv_window_proposal_uses_supported_rails_and_is_uncertain():
    import cv2, numpy as np
    from app.cv_openings import propose

    image = np.full((200, 400, 3), 255, np.uint8)
    walls = [seg("a", (50, 100), (150, 100)), seg("b", (210, 100), (350, 100))]
    assert not propose(image, walls)
    for y in (97, 103):
        cv2.line(image, (150, y), (210, y), (0, 0, 0), 1)
    result = propose(image, walls)
    assert len(result) == 2
    assert result[1].kind == "window" and result[1].host_id == result[0].id
    assert result[1].confidence < 0.85


def test_classified_gap_bridges_but_plain_passage_does_not():
    walls = [seg(1, (100, 100), (300, 100)), seg(2, (380, 100), (700, 100))]
    plain = build(walls)
    assert len(plain.walls) == 2
    window = seg(3, (300, 100), (380, 100), kind="window", confidence=0.8)
    classified = build(walls + [window])
    assert len(classified.walls) == 1
    assert classified.openings[0].width_px == 80
    assert classified.openings[0].host_wall_id == classified.walls[0].id


def test_duplicate_partial_openings_cannot_add_up_to_fake_gap_coverage():
    walls = [seg(1, (100, 100), (300, 100)), seg(2, (400, 100), (700, 100))]
    partial = [
        seg(i, (300, 100), (330, 100), kind="window", confidence=0.8) for i in (3, 4, 5)
    ]
    model = build(walls + partial)
    assert len(model.walls) == 2


def test_thickness_outlier_cannot_dominate_a_long_merged_run():
    model = build(
        [
            seg(1, (100, 100), (220, 100), t=10),
            seg(2, (215, 100), (340, 100), t=11),
            seg(3, (335, 100), (700, 100), t=60),
        ]
    )
    assert len(model.walls) == 1
    assert model.walls[0].thickness_px == 11


def test_short_pier_between_openings_survives_but_tiny_stub_is_pruned():
    model = build(
        [
            seg(1, (100, 100), (260, 100)),
            seg(2, (320, 100), (340, 100)),
            seg(3, (400, 100), (600, 100)),
            seg(4, (200, 300), (210, 300)),
        ]
    )
    assert len(model.walls) == 3
    nodes = {n.id: n for n in model.nodes}
    assert any(
        math.hypot(nodes[w.b].x - nodes[w.a].x, nodes[w.b].y - nodes[w.a].y) == 20
        for w in model.walls
    )


def test_dangling_extension_follows_ink_and_rejects_blank_path():
    import numpy as np
    from app.plan_reconstruct import extend_dangling

    ink = np.zeros((250, 400), bool)
    # A boundary line just off the centre axis is legitimate support.
    ink[96, 180:222] = True
    walls = [seg(1, (60, 100), (180, 100)), seg(2, (220, 40), (220, 200))]
    assert extend_dangling(walls, ink) == 1
    assert walls[0].end.x == 215
    blank = [seg(1, (60, 100), (180, 100)), seg(2, (220, 40), (220, 200))]
    assert extend_dangling(blank, np.zeros_like(ink)) == 0
    assert blank[0].end.x == 180


def test_extension_does_not_smear_endpoint_ink_across_a_blank_gap():
    import numpy as np
    from app.plan_reconstruct import extend_dangling

    ink = np.zeros((250, 400), bool)
    ink[100, 175:181] = True
    ink[100, 190:196] = True
    walls = [seg(1, (60, 100), (180, 100)), seg(2, (200, 40), (200, 200))]
    assert extend_dangling(walls, ink) == 0


def test_width_outlier_does_not_absorb_a_nearby_parallel_wall():
    model = build(
        [
            seg(1, (100, 100), (220, 100), t=10),
            seg(2, (215, 100), (340, 100), t=11),
            seg(3, (335, 100), (700, 100), t=60),
            seg(4, (100, 125), (700, 125), t=10),
        ]
    )
    assert len(model.walls) == 2
    nodes = {n.id: n for n in model.nodes}
    assert sorted(round(nodes[w.a].y) for w in model.walls) == [100, 125]


def test_narrow_width_outlier_does_not_thin_a_merged_wall():
    model = build(
        [
            seg(1, (100, 100), (220, 100), t=10),
            seg(2, (215, 100), (340, 100), t=11),
            seg(3, (335, 100), (700, 100), t=2),
        ]
    )
    assert len(model.walls) == 1
    assert model.walls[0].thickness_px == 10


def test_vertical_extension_uses_cross_wall_ink_support():
    import numpy as np
    from app.plan_reconstruct import extend_dangling

    ink = np.zeros((300, 300), bool)
    ink[180:222, 96] = True
    walls = [seg(1, (100, 50), (100, 180)), seg(2, (40, 220), (240, 220))]
    assert extend_dangling(walls, ink) == 1
    assert walls[0].end.y == 215


def test_door_flank_extension_preserves_the_opening_span():
    import numpy as np
    from app.plan_reconstruct import extend_dangling

    host = seg(1, (70, 100), (110, 100))
    jamb_wall = seg(2, (160, 70), (160, 200))
    door = host.model_copy(deep=True, update={"id": "opening", "kind": "door", "host_id": host.id})
    objects = [host, jamb_wall, door]
    ink = np.zeros((250, 400), bool)
    ink[98:103, 110:160] = True
    limits = {host.id: 50}
    assert extend_dangling(objects, np.zeros_like(ink), cover=0.9, reach_by_wall=limits) == 0
    assert extend_dangling(objects, ink, cover=0.9, reach_by_wall=limits) == 1
    assert host.end.x == 155
    assert (door.start.x, door.end.x) == (70, 110)
