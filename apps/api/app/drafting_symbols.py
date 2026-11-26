"""Scale and rotation search for compound plan symbols on annotated scans."""

import cv2
import numpy as np

from .plan_model import Pt, RoomSymbol


def _stencils():
    def blank(w, h):
        return np.zeros((h, w), np.uint8)

    car = blank(112, 49)

    def path(canvas, points):
        cv2.polylines(canvas, [np.int32(points)], False, 255, 1)

    # Sedan in plan: outer shell, side glazing and two curved windshields.
    path(
        car,
        [
            (0, 24),
            (3, 8),
            (8, 4),
            (28, 1),
            (83, 1),
            (99, 4),
            (108, 12),
            (111, 20),
            (111, 30),
            (105, 40),
            (98, 45),
            (83, 48),
            (25, 48),
            (7, 44),
            (2, 39),
            (0, 24),
        ],
    )
    for points in [
        [(5, 9), (23, 6), (54, 5), (92, 7), (106, 13)],
        [(5, 40), (24, 43), (55, 43), (93, 40), (106, 35)],
        [(22, 6), (19, 15), (19, 32), (22, 42)],
        [(32, 5), (30, 12), (30, 35), (32, 43)],
        [(61, 5), (55, 10), (57, 21), (57, 29), (55, 37), (61, 42)],
        [(63, 5), (68, 14), (70, 26), (68, 35), (63, 42)],
    ]:
        path(car, points)

    dining = blank(60, 57)
    cv2.rectangle(dining, (1, 11), (58, 42), 255, 1)
    for x in (6, 24, 42):
        for y in (3, 42):
            cv2.rectangle(dining, (x, y), (x + 11, y + 9), 255, 1)

    sofa = blank(28, 72)
    cv2.rectangle(sofa, (1, 1), (26, 70), 255, 1)
    cv2.line(sofa, (22, 9), (22, 61), 255, 1)
    for y in (10, 21, 51, 61):
        cv2.polylines(
            sofa,
            [np.int32([(16, y - 6), (22, y), (16, y + 6), (9, y), (16, y - 6)])],
            False,
            255,
            1,
        )

    hob = blank(25, 25)
    cv2.rectangle(hob, (1, 1), (23, 23), 255, 1)
    for x, r in [(7, 2), (17, 3)]:
        for y in (7, 17):
            cv2.circle(hob, (x, y), r, 255, 1)
    cv2.circle(hob, (12, 12), 1, 255, 1)

    stools = blank(70, 19)
    for x in (9, 26, 43, 60):
        cv2.ellipse(stools, (x, 9), (6, 7), 0, 0, 360, 255, 1)
    cv2.line(stools, (1, 10), (68, 10), 255, 1)
    coffee = blank(59, 82)
    cv2.circle(coffee, (29, 29), 28, 255, 1)
    cv2.ellipse(coffee, (29, 52), (24, 24), 0, -25, 205, 255, 1)
    return {
        "coffee_table": coffee,
        "cooktop": hob,
        "dining_table": dining,
        "car": car,
        "sofa": sofa,
        "bar_stools": stools,
    }


def _edges(gray):
    edges = cv2.Canny(gray, 12, 32)
    dx = cv2.Sobel(gray, cv2.CV_32F, 1, 0)
    dy = cv2.Sobel(gray, cv2.CV_32F, 0, 1)
    angle = (np.arctan2(dy, dx) + np.pi / 8) % np.pi
    return [
        np.float32(
            (edges > 0) & (angle >= i * np.pi / 4) & (angle < (i + 1) * np.pi / 4)
        )
        for i in range(4)
    ]


def _tolerant(edge):
    return cv2.GaussianBlur(cv2.dilate(edge, np.ones((3, 3), np.uint8)), (3, 3), 0.6)


def _match_score(ink, channels):
    score = 0
    for i, edges, soft in channels:
        support = cv2.matchTemplate(ink[i], edges, cv2.TM_CCORR) / edges.sum()
        contrast = cv2.matchTemplate(ink[i], soft, cv2.TM_CCOEFF_NORMED)
        score += 0.55 * support + 0.45 * contrast
    return score / len(channels)


def tree_symbols(image):
    """Separate textured canopy symbols from flat lawn fills and thin garden borders."""
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    dark_leaf = cv2.inRange(hsv, (35, 38, 0), (100, 255, 154))
    filled = cv2.morphologyEx(dark_leaf, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
    count, regions, stats, centers = cv2.connectedComponentsWithStats(filled)
    found = []
    for i in range(1, count):
        x, y, w, h, area = stats[i]
        if not (
            16 <= min(w, h)
            and max(w, h) <= min(image.shape[:2]) * 0.35
            and 0.5 <= w / h <= 2
            and 0.24 <= area / (w * h) <= 0.88
        ):
            continue
        patch = hsv[y : y + h, x : x + w, 2][regions[y : y + h, x : x + w] == i]
        if np.percentile(patch, 90) - np.percentile(patch, 10) < 45:
            continue
        cx, cy = centers[i]
        found.append(
            RoomSymbol(kind="tree", position=Pt(x=cx, y=cy), width_px=w, depth_px=h)
        )
    return found


def compound_symbols(image, roi=None):
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    reduction = min(1.0, 1500 / max(gray.shape))
    gray = cv2.resize(gray, None, fx=reduction, fy=reduction)
    gray = cv2.createCLAHE(2.0, (12, 8)).apply(gray)
    region = np.float32(roi) if roi is not None and len(roi) else None
    thresholds = {
        "coffee_table": 0.58,
        "car": 0.49,
        "sofa": 0.54,
        "bar_stools": 0.54,
        "dining_table": 0.45,
        "cooktop": 0.55,
    }
    patterns = {}
    for kind, pattern in _stencils().items():
        channels = [
            (i, e, _tolerant(e)) for i, e in enumerate(_edges(pattern)) if e.sum() > 3
        ]
        patterns[kind] = pattern.shape, channels
    candidates = []
    for factor in np.geomspace(0.9, 3, 18):
        if min(gray.shape) < factor * 19:
            break
        sample = cv2.resize(
            gray, None, fx=1 / factor, fy=1 / factor, interpolation=cv2.INTER_AREA
        )
        for turns in range(2):
            src = np.rot90(sample, turns).copy()
            ink = [_tolerant(e) for e in _edges(src)]
            for kind, ((h, w), channels) in patterns.items():
                if h > src.shape[0] or w > src.shape[1]:
                    continue
                score = _match_score(ink, channels)
                for _ in range(8):
                    _, peak, _, (x, y) = cv2.minMaxLoc(score)
                    if peak < thresholds[kind] - 0.035:
                        break
                    cx, cy = x + w / 2, y + h / 2
                    if turns:
                        cx, cy = sample.shape[1] - cy, cx
                    center = (cx * factor / reduction, cy * factor / reduction)
                    if (
                        region is None
                        or cv2.pointPolygonTest(region, center, False) >= 0
                    ):
                        candidates.append((peak, kind, center, factor, turns))
                    score[
                        max(0, y - h // 2) : y + h // 2 + 1,
                        max(0, x - w // 2) : x + w // 2 + 1,
                    ] = -1
    found = []
    for peak, kind, center, factor, turns in sorted(candidates, reverse=True):
        if peak < thresholds[kind]:
            continue
        radius = min(patterns[kind][0]) * factor / reduction / 3

        def nearby(point):
            return np.hypot(center[0] - point[0], center[1] - point[1]) < radius

        if any(nearby((s.position.x, s.position.y)) for s in found):
            continue
        if any(
            k == kind and t == turns and f != factor and nearby(p)
            for _, k, p, f, t in candidates
        ):
            height, width = patterns[kind][0]
            rotation = 90 * turns
            if kind in ("sofa", "coffee_table"):
                width, height = height, width
                rotation += 90
            found.append(
                RoomSymbol(
                    kind=kind,
                    position=Pt(x=center[0], y=center[1]),
                    width_px=width * factor / reduction,
                    depth_px=height * factor / reduction,
                    rotation=rotation,
                )
            )
    return found


def counter_basins(image, symbols):
    """Search a cooktop's counter line for the nested rim of an inset sink."""
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    found = []
    for hob in symbols:
        if hob.kind != "cooktop" or not hob.width_px:
            continue
        side = hob.width_px
        center = np.array([hob.position.x, hob.position.y])
        lower = np.maximum(0, np.floor(center - 5 * side)).astype(int)
        upper = np.minimum(gray.shape[::-1], np.ceil(center + 5 * side)).astype(int)
        patch = gray[lower[1] : upper[1], lower[0] : upper[0]]
        edges = cv2.Canny(cv2.createCLAHE(2, (6, 6)).apply(patch), 22, 54)
        near = np.minimum(cv2.distanceTransform(255 - edges, cv2.DIST_L2, 3), 4)
        matches = []
        for factor in (0.72, 0.80, 0.88, 0.96, 1.04):
            w, h = round(side * factor), round(side * factor * 0.88)
            if min(w, h) < 15 or w >= patch.shape[1] or h >= patch.shape[0]:
                continue
            # Sample the nested rims independently on each face. A cabinet
            # corner, parallel dimension lines, or a single box lacks these cues.
            sides = []
            for axis in (0, 1):
                for far in (False, True):
                    stencil = np.zeros((h, w), np.float32)
                    length = (w, h)[axis]
                    for inset in (1, 4):
                        offset = (h, w)[axis] - 1 - inset if far else inset
                        if axis == 0:
                            stencil[offset, 5 : length - 5] = 1
                        else:
                            stencil[5 : length - 5, offset] = 1
                    sides.append(
                        cv2.matchTemplate(near, stencil, cv2.TM_CCORR) / stencil.sum()
                    )
            score = np.mean(sides, axis=0) + 0.5 * np.max(sides, axis=0)
            yy, xx = np.indices(score.shape)
            dx = np.abs(xx + lower[0] + w / 2 - center[0]) / side
            dy = np.abs(yy + lower[1] + h / 2 - center[1]) / side
            eligible = (
                (np.minimum(dx, dy) < 0.22)
                & (np.maximum(dx, dy) > 1.25)
                & (np.maximum(dx, dy) < 4.5)
            )
            score[~eligible] = 10
            val, _, (x, y), _ = cv2.minMaxLoc(score)
            if val < 1.25:
                matches.append((val, x + w / 2 + lower[0], y + h / 2 + lower[1], w, h))
        if matches:
            best, x, y, w, h = min(matches)
            if any(
                abs(xx - x) < 4 and abs(yy - y) < 4 and ww != w
                for _, xx, yy, ww, _ in matches
            ):
                found.append(
                    RoomSymbol(
                        kind="sink", position=Pt(x=x, y=y), width_px=w, depth_px=h
                    )
                )
    return found


def sanitary_symbols(image, model):
    """Look for a paired bowl contour in small enclosed rooms with a door."""
    from .fixture_detection import stencil

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    found = []
    for room in model.rooms:
        if room.room_type not in (None, "bathroom"):
            continue
        polygon = np.float32([(p.x, p.y) for p in room.polygon])
        x, y, w, h = cv2.boundingRect(polygon)
        doors = [
            o
            for o in model.openings
            if o.kind == "door"
            and o.status != "rejected"
            and o.host_wall_id in room.wall_ids
        ]
        if not doors:
            continue
        door = np.median([o.width_px for o in doors])
        if max(w, h) > 3.2 * door or min(w, h) < 0.72 * door:
            continue
        crop = gray[y : y + h, x : x + w]
        ink = [
            _tolerant(edge) for edge in _edges(cv2.createCLAHE(2.0, (4, 4)).apply(crop))
        ]
        matched = []
        for kind, minimum in (("toilet", 0.53), ("sink", 0.55)):
            candidates = []
            for factor in (0.45, 0.5, 0.55, 0.6, 0.65):
                bw = round(factor * door)
                bh = round(1.65 * bw)
                if bw < 12:
                    continue
                if kind == "toilet":
                    pattern = stencil(kind, bw, bh)
                else:
                    pattern = np.zeros((bh, bw), np.uint8)
                    cv2.ellipse(
                        pattern,
                        (bw // 2, round(0.34 * bh)),
                        (round(0.38 * bw), round(0.30 * bh)),
                        0,
                        0,
                        360,
                        255,
                        1,
                    )
                    cv2.rectangle(
                        pattern,
                        (round(0.19 * bw), round(0.69 * bh)),
                        (round(0.83 * bw), round(0.89 * bh)),
                        255,
                        1,
                    )
                for turns in range(4):
                    rotated = np.rot90(pattern, turns)
                    th, tw = rotated.shape
                    if th > crop.shape[0] or tw > crop.shape[1]:
                        continue
                    channels = [
                        (i, e, _tolerant(e))
                        for i, e in enumerate(_edges(rotated))
                        if e.sum() > 3
                    ]
                    score = _match_score(ink, channels)
                    _, peak, _, (cx, cy) = cv2.minMaxLoc(score)
                    px, py = x + cx + tw / 2, y + cy + th / 2
                    if cv2.pointPolygonTest(polygon, (px, py), False) >= 0:
                        candidates.append((peak, px, py, bw, bh, turns))
            if not candidates:
                continue
            peak, px, py, bw, bh, turns = max(candidates)
            if peak < minimum or not any(
                other >= minimum - 0.05
                and otherw != bw
                and t == turns
                and abs(xx - px) + abs(yy - py) < bw / 3
                for other, xx, yy, otherw, _, t in candidates
            ):
                continue
            if kind == "sink" and (
                not matched
                or any(
                    np.hypot(px - v.position.x, py - v.position.y) < 0.8 * door
                    for v in matched
                )
            ):
                continue
            matched.append(
                RoomSymbol(
                    kind=kind,
                    position=Pt(x=px, y=py),
                    width_px=bw,
                    depth_px=bh,
                    rotation=(0, -90, 180, 90)[turns],
                )
            )
        found.extend(matched)
    return found


def patio_sets(image, gardens, symbols):
    """Look for the same six-seat drafting convention at the measured indoor table scale."""
    tables = [s for s in symbols if s.kind == "dining_table" and s.width_px]
    if not tables:
        return []
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    height, width = gray.shape
    template = _stencils()["dining_table"]
    channels = [
        (i, e, _tolerant(e)) for i, e in enumerate(_edges(template)) if e.sum() > 3
    ]
    found = []
    for garden in gardens:
        if garden.surface != "paving":
            continue
        outline = np.rint(np.array(garden.points) * [width, height]).astype(np.int32)
        x, y, w, h = cv2.boundingRect(outline)
        patch = gray[y : y + h, x : x + w]
        if not patch.size:
            continue
        valid = np.zeros(patch.shape, np.uint8)
        cv2.fillPoly(valid, [outline - [x, y]], 1)
        for hole in garden.holes:
            cv2.fillPoly(
                valid,
                [np.rint(np.array(hole) * [width, height]).astype(np.int32) - [x, y]],
                0,
            )
        paper = cv2.createCLAHE(2.0, (4, 6)).apply(patch)
        matches = []
        for table in tables:
            for factor in (
                np.linspace(0.84, 1.08, 6) * table.width_px / template.shape[1]
            ):
                if min(patch.shape) / factor < min(template.shape):
                    continue
                sample = cv2.resize(
                    paper,
                    None,
                    fx=1 / factor,
                    fy=1 / factor,
                    interpolation=cv2.INTER_AREA,
                )
                for turns in (0, 1):
                    src = np.rot90(sample, turns)
                    th, tw = template.shape
                    if src.shape[0] < th or src.shape[1] < tw:
                        continue
                    ink = [_tolerant(e) for e in _edges(src)]
                    score = _match_score(ink, channels)
                    _, peak, _, (xx, yy) = cv2.minMaxLoc(score)
                    cx, cy = (xx + tw / 2) * factor, (yy + th / 2) * factor
                    if turns:
                        cx, cy = patch.shape[1] - cy, cx
                    halfw, halfh = (th, tw) if turns else (tw, th)
                    halfw, halfh = halfw * factor / 2, halfh * factor / 2
                    covered = valid[
                        max(0, round(cy - halfh)) : round(cy + halfh),
                        max(0, round(cx - halfw)) : round(cx + halfw),
                    ]
                    if covered.size and covered.mean() > 0.9:
                        matches.append((peak, cx, cy, factor, turns))
        if matches:
            peak, cx, cy, factor, turns = max(matches)
            agreeing = {
                f
                for s, xx, yy, f, t in matches
                if s > 0.34 and t == turns and abs(xx - cx) + abs(yy - cy) < 6 * factor
            }
            if peak > 0.37 and len(agreeing) >= 3:
                found.append(
                    RoomSymbol(
                        kind="patio_set",
                        position=Pt(x=x + cx, y=y + cy),
                        width_px=template.shape[1] * factor,
                        depth_px=template.shape[0] * factor,
                        rotation=90 * turns,
                    )
                )
    return found


def _counter_edge(gray, lane, radius, first, last):
    """Longest continuous ruled face crossing both anchors, allowing thin annotations."""
    lane = round(lane)
    if lane - radius < 4 or lane + radius + 4 >= len(gray):
        return None
    rows = np.arange(lane - radius, lane + radius + 1)
    contrast = (gray[rows - 3] + gray[rows + 3]) / 2 - gray[rows]
    dark = (contrast.max(axis=0) > 9).astype(np.uint8)[None, :]
    connected = cv2.morphologyEx(dark, cv2.MORPH_CLOSE, np.ones((1, 7), np.uint8))[0]
    marks = np.diff(np.r_[0, connected, 0].astype(int))
    for a, b in zip(np.flatnonzero(marks == 1), np.flatnonzero(marks == -1)):
        if a <= first and last <= b and dark[0, a:b].mean() > 0.78:
            return int(a), int(b)
    return None


def kitchen_cabinets(image, symbols, model):
    """Trace cabinet faces beside paired appliances and a parallel architectural wall."""
    from shapely.geometry import LineString, Point as GeoPoint

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY).astype(np.float32)
    nodes = {n.id: n for n in model.nodes}
    walls = [
        LineString([(nodes[w.a].x, nodes[w.a].y), (nodes[w.b].x, nodes[w.b].y)])
        for w in model.walls
    ]
    found = []
    for sink in (s for s in symbols if s.kind == "sink"):
        for hob in (s for s in symbols if s.kind == "cooktop" and s.width_px):
            p, q = hob.position, sink.position
            vertical = abs(p.y - q.y) > abs(p.x - q.x)
            across = lambda pos: pos.x if vertical else pos.y
            along = lambda pos: pos.y if vertical else pos.x
            lane = (across(p) + across(q)) / 2
            first, last = sorted([along(p), along(q)])
            side = hob.width_px
            if last - first > 4.5 * side or abs(across(p) - across(q)) > 0.24 * side:
                continue
            anchors = []
            for wall in walls:
                (x1, y1), (x2, y2) = wall.coords
                delta = abs(x1 - x2) if vertical else abs(y1 - y2)
                if delta > 1 or wall.distance(GeoPoint(p.x, p.y)) > 0.95 * side:
                    continue
                back = (x1 + x2) / 2 if vertical else (y1 + y2) / 2
                projected = (
                    GeoPoint(back, along(q)) if vertical else GeoPoint(along(q), back)
                )
                if 0.3 * side < abs(lane - back) < 0.9 * side and any(
                    w.distance(projected) < 2 for w in walls
                ):
                    anchors.append(back)
            if not anchors:
                continue
            back = min(anchors, key=lambda v: abs(v - lane))
            sign = 1 if lane > back else -1
            raster = gray.T if vertical else gray
            edge = None
            for ratio in (0.44, 0.50, 0.38, 0.56):
                front = round(lane + sign * side * ratio)
                edge = _counter_edge(raster, front, 2, first, last)
                if edge:
                    break
            if not edge or not 2 * side < edge[1] - edge[0] < 12 * side:
                continue
            # Use the appliance footprint to estimate the rear face inside the wall.
            rear = lane - sign * side * 0.46

            def cabinet(start, end, near, far, rotated):
                a = (start + end) / 2
                b = (near + far) / 2
                return RoomSymbol(
                    kind="cabinets",
                    position=Pt(x=b if rotated else a, y=a if rotated else b),
                    width_px=end - start,
                    depth_px=abs(far - near),
                    rotation=90 if rotated else 0,
                )

            run = LineString(
                [(lane, edge[0]), (lane, edge[1])]
                if vertical
                else [(edge[0], lane), (edge[1], lane)]
            )
            crossings = [run.intersection(w) for w in walls if run.intersects(w)]
            stops = [
                (crossing.y if vertical else crossing.x)
                for crossing in crossings
                if crossing.geom_type == "Point"
            ]
            edge = (
                max([edge[0], *(k for k in stops if k < first)]),
                min([edge[1], *(k for k in stops if k > last)]),
            )
            ends = list(edge)
            for index, direction in enumerate((-1, 1)):
                end = ends[index]
                at = front + sign * side * 0.45
                # Find a perpendicular room wall close to the measured end.
                # The join can extend through the end unit on a blurred scan.
                outer_faces = []
                for wall in walls:
                    (x1, y1), (x2, y2) = wall.coords
                    outer = (y1 + y2) / 2 if vertical else (x1 + x2) / 2
                    delta = abs(y1 - y2) if vertical else abs(x1 - x2)
                    probe = GeoPoint(at, outer) if vertical else GeoPoint(outer, at)
                    if (
                        delta < 1
                        and wall.distance(probe) < 2
                        and -0.12 * side < (outer - end) * direction < 1.6 * side
                    ):
                        outer_faces.append(outer)
                if not outer_faces:
                    continue
                outer = min(outer_faces, key=lambda k: abs(k - end))
                for depth in np.linspace(0.82, 1.22, 12) * side:
                    inner = outer - direction * depth
                    arm = _counter_edge(raster.T, inner, 1, at, at)
                    if not arm:
                        continue
                    tip = arm[1] if sign > 0 else arm[0]
                    if 1.75 * side < (tip - front) * sign < 7 * side:
                        ends[index] = inner
                        found.append(
                            cabinet(*sorted([rear, tip]), inner, outer, not vertical)
                        )
                        break
            found.append(cabinet(*ends, rear, front, vertical))
            break
    return found


def media_consoles(image, symbols, model):
    """Find a wall-backed cabinet with a shorter parallel screen facing a sofa."""
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY).astype(np.float32)
    nodes = {n.id: n for n in model.nodes}
    found = []
    for sofa in (s for s in symbols if s.kind == "sofa"):
        if not sofa.depth_px or not sofa.width_px:
            continue
        facing_x = abs(sofa.rotation) == 90
        raster = gray.T if facing_x else gray
        sign = {0: 1, 90: -1, 180: -1, -90: 1}[sofa.rotation]
        along, across = (
            (sofa.position.y, sofa.position.x)
            if facing_x
            else (sofa.position.x, sofa.position.y)
        )
        walls = []
        for w in model.walls:
            a, b = nodes[w.a], nodes[w.b]
            p, q = (a.y, b.y) if facing_x else (a.x, b.x)
            u, v = (a.x, b.x) if facing_x else (a.y, b.y)
            if abs(u - v) > 1 or not min(p, q) < along < max(p, q):
                continue
            face = (u + v) / 2 - sign * w.thickness_px / 2
            if 0.6 * sofa.width_px < (face - across) * sign < 4 * sofa.width_px:
                walls.append((abs(face - across), face))
        if not walls:
            continue
        _, face = min(walls)
        best = None
        for depth in range(round(0.26 * sofa.depth_px), round(0.85 * sofa.depth_px)):
            front = round(face - sign * depth)
            span = _counter_edge(raster, front, 1, along - 8, along + 8)
            if (
                not span
                or not 0.68 * sofa.width_px < span[1] - span[0] < 1.65 * sofa.width_px
            ):
                continue
            lo, hi = span
            lanes = sorted((round(face - sign * 4), front))
            if (
                lanes[0] < 3
                or lanes[1] + 3 >= len(raster)
                or hi + 3 >= raster.shape[1]
                or lo < 3
            ):
                continue
            # A shorter screen is drawn inside the cabinet, parallel to the facade.
            inner = raster[lanes[0] + 3 : lanes[1] - 2, lo:hi]
            if inner.shape[0] < 3:
                continue
            stroke = (inner[:-2] + inner[2:]) / 2 - inner[1:-1]
            mid = stroke[:, round(0.33 * (hi - lo)) : round(0.67 * (hi - lo))]
            flank = np.concatenate(
                (
                    stroke[:, : round(0.19 * (hi - lo))],
                    stroke[:, round(0.81 * (hi - lo)) :],
                ),
                axis=1,
            )
            screen = ((mid > 8).mean(axis=1) - (flank > 8).mean(axis=1)).max()
            if screen < 0.52:
                continue
            if best is None or screen > best[0]:
                best = (screen, front, lo, hi)
        if best:
            _, front, lo, hi = best
            a, b = (lo + hi) / 2, (front + face) / 2
            found.append(
                RoomSymbol(
                    kind="tv_console",
                    position=Pt(x=b if facing_x else a, y=a if facing_x else b),
                    width_px=hi - lo,
                    depth_px=abs(face - front),
                    rotation=sofa.rotation % 360 - 180,
                )
            )
    return found


def bar_counters(image, symbols):
    """Validate the four edges of the counter alongside a row of stools."""
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    ink = cv2.subtract(
        cv2.morphologyEx(gray, cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8)), gray
    )
    ink = cv2.dilate(ink, np.ones((3, 3), np.uint8)) > 11
    found = []
    for stools in (s for s in symbols if s.kind == "bar_stools"):
        if not stools.width_px or not stools.depth_px:
            continue
        vertical = stools.rotation in (90, -90)
        raster = ink.T if vertical else ink
        cx, cy = (
            (stools.position.y, stools.position.x)
            if vertical
            else (stools.position.x, stools.position.y)
        )
        matches = []
        for scale in (0.92, 0.96, 1.0, 1.04):
            lo, hi = (
                round(cx - scale * stools.width_px / 2),
                round(cx + scale * stools.width_px / 2),
            )
            if lo < 0 or hi >= raster.shape[1]:
                continue
            for near in range(
                round(cy - 0.2 * stools.depth_px), round(cy + 0.2 * stools.depth_px) + 1
            ):
                for sign in (-1, 1):
                    for ratio in (0.85, 0.92, 1.0, 1.08, 1.16):
                        far = near + sign * round(ratio * stools.depth_px)
                        a, b = sorted((near, far))
                        if a < 0 or b >= len(raster):
                            continue
                        faces = [
                            raster[a, lo:hi],
                            raster[b, lo:hi],
                            raster[a:b, lo],
                            raster[a:b, hi],
                        ]
                        support = [v.mean() for v in faces]
                        if min(support) > 0.70:
                            matches.append((sum(support), lo, hi, a, b))
        if matches:
            _, lo, hi, a, b = max(matches)
            along, cross = (lo + hi) / 2, (a + b) / 2
            found.append(
                RoomSymbol(
                    kind="bar_counter",
                    position=Pt(
                        x=cross if vertical else along, y=along if vertical else cross
                    ),
                    width_px=hi - lo,
                    depth_px=b - a,
                    rotation=stools.rotation,
                )
            )
    return found


def site_symbols(image, model, roi=None):
    matches = compound_symbols(image, roi)
    sanitary = sanitary_symbols(image, model)
    bars = bar_counters(image, matches)
    trees = tree_symbols(image)
    h, w = image.shape[:2]
    factor = 1280 / max(w, h)
    if 0.5 <= factor <= 1.5 and abs(factor - 1) > 0.14:
        from .extraction_resize import ExtractionResize

        small = cv2.resize(
            image,
            None,
            fx=factor,
            fy=factor,
            interpolation=cv2.INTER_CUBIC if factor > 1 else cv2.INTER_AREA,
        )
        # Only geometry is needed for bathroom context. Create separate source
        # points before scaling, including where neighbouring rooms share corners.
        working = model.model_copy(update={"stairs": [], "room_symbols": []})
        working = type(model).model_validate(working.dump())
        working = ExtractionResize(small.shape[1], small.shape[0], 1 / factor).model(
            working
        )
        secondary = compound_symbols(small, np.array(roi) * factor if roi else None)

        def original_positions(items):
            for item in items:
                item.position.x = (item.position.x + 0.5) / factor - 0.5
                item.position.y = (item.position.y + 0.5) / factor - 0.5
                item.width_px /= factor
                item.depth_px /= factor
            return items

        def supplement(primary, secondary):
            for item in original_positions(secondary):
                if not any(
                    s.kind == item.kind
                    and np.hypot(
                        s.position.x - item.position.x, s.position.y - item.position.y
                    )
                    < 0.6 * max(item.width_px, item.depth_px)
                    for s in primary
                ):
                    primary.append(item)

        supplement(bars, bar_counters(small, secondary))
        supplement(sanitary, sanitary_symbols(small, working))
        supplement(matches, secondary)
        # Canopy identification relies on local tonal texture. Thin planting
        # borders that turn into blobs at just one sampling size are unstable.
        confirmed = original_positions(tree_symbols(small))
        trees = [
            t
            for t in trees
            if any(
                np.hypot(t.position.x - c.position.x, t.position.y - c.position.y)
                < 0.45 * t.width_px
                for c in confirmed
            )
        ]
    matches.extend(counter_basins(image, matches))
    matches.extend(kitchen_cabinets(image, matches, model))
    matches.extend(patio_sets(image, model.gardens, matches))
    matches.extend(media_consoles(image, matches, model))
    return [*matches, *bars, *sanitary, *trees]


def kitchen_fridges(image, cabinets):
    """Identify a terminal appliance bay using the double cabinet-side outline."""
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY).astype(np.float32)
    fridges = []
    for cabinet in cabinets:
        if cabinet.kind != "cabinets":
            continue
        depth = cabinet.depth_px
        if not 10 <= depth or not 1.7 * depth <= cabinet.width_px <= 6 * depth:
            continue
        vertical = cabinet.rotation in (-90, 90)
        raster = gray if vertical else gray.T
        pos = cabinet.position.y if vertical else cabinet.position.x
        lane = cabinet.position.x if vertical else cabinet.position.y
        if not 5 < lane - depth * 0.85 or lane + depth * 0.85 >= raster.shape[1] - 5:
            continue
        for sign in (-1, 1):
            tip = pos + sign * cabinet.width_px / 2
            starts = range(round(tip - 0.22 * depth), round(tip + 0.22 * depth) + 1)
            fronts = range(round(lane - 0.75 * depth), round(lane + 0.75 * depth) + 1)
            for start in starts:
                if not 3 <= start < len(raster) - 3:
                    continue
                for length in np.arange(0.96, 1.5, 0.08) * depth:
                    end = round(start + sign * length)
                    if not 3 <= end < len(raster) - 3:
                        continue
                    lo, hi = sorted((start, end))
                    columns = np.array(list(fronts))
                    contrast = (
                        raster[lo:hi, columns - 2] + raster[lo:hi, columns + 2]
                    ) / 2 - raster[lo:hi, columns]
                    rails = columns[(contrast > 4).mean(axis=0) > 0.8]
                    for front in rails:
                        for rear in rails:
                            if not 0.94 * depth < rear - front < 1.45 * depth:
                                continue
                            if not any(
                                2 <= inner - front <= 0.26 * depth for inner in rails
                            ):
                                continue
                            caps = [
                                (raster[y - 2, front:rear] + raster[y + 2, front:rear])
                                / 2
                                - raster[y, front:rear]
                                for y in (start, end)
                            ]
                            if min((cap > 4).mean() for cap in caps) > 0.72:
                                x, y = (front + rear) / 2, (start + end) / 2
                                fridges.append(
                                    RoomSymbol(
                                        kind="fridge",
                                        position=Pt(
                                            x=x if vertical else y,
                                            y=y if vertical else x,
                                        ),
                                        width_px=abs(end - start),
                                        depth_px=rear - front,
                                        rotation=cabinet.rotation,
                                    )
                                )
                                break
                        else:
                            continue
                        break
                    else:
                        continue
                    break
                else:
                    continue
                break
            else:
                continue
            break
    return fridges


def recover_kitchen_at_second_resolution(image, model):
    """Recheck the inset sink and countertop on a less enlarged raster."""
    from .extraction_resize import ExtractionResize

    h, w = image.shape[:2]
    factor = 1.18
    resized = cv2.resize(
        image, None, fx=factor, fy=factor, interpolation=cv2.INTER_CUBIC
    )
    working = model.model_copy(deep=True)
    working.stairs = []
    working = ExtractionResize(resized.shape[1], resized.shape[0], 1 / factor).model(
        working
    )
    sinks = counter_basins(resized, working.room_symbols)
    cabinets = kitchen_cabinets(resized, [*working.room_symbols, *sinks], working)
    for item in [*sinks, *cabinets]:
        ExtractionResize(w, h, factor).point(item.position)
        item.width_px /= factor
        item.depth_px /= factor
    return [*sinks, *cabinets, *kitchen_fridges(image, cabinets)]
