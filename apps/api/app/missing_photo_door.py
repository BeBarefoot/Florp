"""Recover a missing doorway and its missing L-shaped partition together."""
from collections import defaultdict
from hashlib import sha256
import math

import cv2
import numpy as np
from shapely.geometry import LineString, Polygon

from .ink_layers import _local_paper
from .openings import Gap, _photo_door
from .plan_model import Node, Opening, Pt, Wall
from .wall_alignment import _join_tees


def _axis(a, b):
    if a.y == b.y and a.x != b.x:
        return 0
    if a.x == b.x and a.y != b.y:
        return 1
    return None


def recover_missing_photo_doors(model, tint, image, *, confirm_at):
    """Require a surviving T/return, two painted jambs, a swing, and a far wall."""
    if tint is None or len(model.walls) >= 9997 or len(model.nodes) >= 19997 or len(model.openings) >= 5000:
        return model
    nodes = {n.id: n for n in model.nodes}
    incident = defaultdict(list)
    runs = [[], []]
    for wall in model.walls:
        a, b = nodes[wall.a], nodes[wall.b]
        incident[a.id].append(wall.id)
        incident[b.id].append(wall.id)
        axis = _axis(a, b)
        if axis is not None:
            p, q = (a.x, a.y), (b.x, b.y)
            runs[axis].append((wall, p[1-axis], *sorted((p[axis], q[axis]))))

    # Rejected openings also reserve their source span; do not revive them.
    by_id = {w.id: w for w in model.walls}
    apertures = []
    for opening in model.openings:
        host = by_id.get(opening.host_wall_id)
        if host is not None:
            a, b = nodes[host.a], nodes[host.b]
            length = math.hypot(b.x-a.x, b.y-a.y)
            if length > 0:
                apertures.append(LineString([
                    (a.x + d*(b.x-a.x)/length, a.y + d*(b.y-a.y)/length)
                    for d in (opening.offset_px, opening.offset_px+opening.width_px)
                ]))
        elif opening.span:
            apertures.append(LineString([(p.x, p.y) for p in opening.span]))
    hosted = {o.host_wall_id for o in model.openings}
    envelope = Polygon([(p.x, p.y) for p in model.envelope]) if model.envelope else None
    recovered_ids, replaced_stubs = set(), set()
    additions, openings = [], []
    swing_ink = None

    for axis, lanes in enumerate(runs):
        other = 1 - axis
        ink = tint if axis == 0 else tint.T
        height, width = ink.shape
        for stub, lane, start, end in lanes:
            if stub.id in hosted or stub.source == "user" or not 1.1 * stub.thickness_px <= end-start <= 36:
                continue
            for root, tip in ((stub.a, stub.b), (stub.b, stub.a)):
                if len(incident[tip]) != 1 or len(incident[root]) < 2:
                    continue
                u = (nodes[root].x, nodes[root].y)[axis]
                v = (nodes[tip].x, nodes[tip].y)[axis]
                sign = 1 if v > u else -1
                shift = round(min(20, max(15, 2.4 * stub.thickness_px)))
                anchors = [(lo, hi) for w, cross, lo, hi in runs[other]
                           if w.id in incident[root] and cross == u]
                if not anchors:
                    continue
                stub_paint = ink[max(0, round(lane)-1):round(lane)+2,
                                 round(start+0.25*(end-start)):round(end-0.12*(end-start))]
                painted_stub = stub_paint.size and (stub_paint.any(axis=0).mean() >= 0.25)
                candidates = []
                for c in range(max(2, round(lane)-shift), min(height-2, round(lane)+shift+1)):
                    if painted_stub and abs(c-lane) > max(3, 0.65*stub.thickness_px):
                        continue
                    if not any(lo-1e-5 <= c <= hi+1e-5 for lo, hi in anchors):
                        continue
                    profile = ink[c-2:c+3].sum(axis=0)
                    # Walk from the structural junction through the first
                    # jamb, the blank opening, and the second painted flank.
                    x = round(u) + sign*np.arange(180)
                    x = x[(x >= 0) & (x < width)]
                    if x.size < 38:
                        continue
                    band = profile[x] >= 2
                    band = cv2.morphologyEx(band[None].astype(np.uint8), cv2.MORPH_CLOSE,
                                            np.ones((1, 3), np.uint8))[0] > 0
                    edges = np.flatnonzero(np.diff(np.r_[False, band, False].astype(int))).reshape(-1, 2)
                    if len(edges) < 2:
                        continue
                    (a, b), (d, e) = edges[:2]
                    gap_width = d-b+1
                    if (a > 4 or b-a < 9 or abs(x[b-1]-v) > shift or not 19 <= gap_width <= 68
                            or not 0.55*gap_width <= e-d <= 1.75*gap_width
                            or e >= len(x) or np.mean(profile[x[d:e]] >= 2) < 0.92):
                        continue
                    lo, hi = sorted((float(x[b-1]), float(x[d])))
                    radius = max(2, min(5, round(gap_width*0.11)))
                    point = lambda t, s: (t, s) if axis == 0 else (s, t)
                    for _, far, left, right in lanes:
                        if not 1.5*gap_width <= abs(far-c) <= 3.5*gap_width:
                            continue
                        rows = np.arange(round(min(c, far))+3, round(max(c, far))-2)
                        for corner in range(int(x[e-1])-radius, int(x[e-1])+radius+1):
                            if not left <= corner <= right or not radius <= corner < width-radius:
                                continue
                            if (corner-x[d])*sign < 0.5*gap_width:
                                continue
                            band_v = ink[rows, corner-radius:corner+radius+1]
                            if (band_v.sum(axis=1) >= 3).mean() < 0.95:
                                continue
                            # Do not run a new return next to a surviving one.
                            if any(abs(k-corner) <= radius+2 and
                                   min(q, max(c, far))-max(p, min(c, far)) > 0.3*gap_width
                                   for _, k, p, q in runs[other]):
                                continue
                            if any(abs(k-c) <= radius+2 and
                                   min(q, max(u, corner))-max(p, min(u, corner)) > 0.3*gap_width
                                   for w, k, p, q in lanes if w.id != stub.id):
                                continue
                            path = LineString([point(u, c), point(corner, c), point(corner, far)])
                            if ((envelope is not None and not envelope.covers(path))
                                    or any(path.distance(aperture) <= radius+1 for aperture in apertures)):
                                continue
                            vertical_t = float(np.median(band_v.sum(axis=1)))
                            horizontal_t = float(np.median(profile[x[d:e]]))
                            rank = horizontal_t + vertical_t + 2*ink[rows, corner].mean()
                            candidates.append((rank, c, lo, hi, corner, far, horizontal_t, vertical_t))
                if not candidates:
                    continue
                if swing_ink is None:
                    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY).astype(np.float32)
                    paper = _local_paper(gray.astype(np.uint8)).astype(np.float32)
                    local = cv2.GaussianBlur(gray, (0, 0), 2)
                    kernel = np.ones((3, 3), np.uint8)
                    strong = ((gray < 0.94*paper) & (gray < local-0.015*paper)) & ~tint
                    faint = ((gray < 0.98*paper) & (gray < local-0.008*paper)) & ~tint
                    swing_ink = [cv2.dilate(mask.astype(np.uint8), kernel) > 0 for mask in (strong, faint)]
                # The source-fit coordinates are bounded by the two real
                # jambs. Neither a blank gap nor the painted L alone is enough.
                tried = set()
                best = None
                for rank, c, lo, hi, corner, far, ht, vt in sorted(candidates, reverse=True):
                    key = c, lo, hi
                    if key in tried:
                        continue
                    if len(tried) == 10:
                        break
                    tried.add(key)
                    swing = _photo_door(swing_ink[0], Gap(axis == 0, c, lo, hi, ht), swing_ink[1])
                    if swing and (best is None or rank+3*swing[0] > best[0]):
                        best = rank+3*swing[0], c, lo, hi, corner, far, ht, vt, swing
                if best is None or stub.id in replaced_stubs:
                    continue
                _, c, lo, hi, corner, far, ht, vt, swing = best
                p, q, r = point(u, c), point(corner, c), point(corner, far)
                key = "photo-door-" + sha256(str((p, q, r)).encode()).hexdigest()[:16]
                if (key in recovered_ids or len(model.walls)+len(additions) >= 9997
                        or len(nodes) >= 19997 or len(model.openings)+len(openings) >= 5000):
                    continue
                recovered_ids.add(key)
                replaced_stubs.add(stub.id)
                by_coords = {(n.x, n.y): n.id for n in nodes.values()}
                ids = []
                for i, pos in enumerate((p, q, r)):
                    if pos not in by_coords:
                        node = Node(id=f"{key}-{i}", x=pos[0], y=pos[1])
                        nodes[node.id] = node
                        by_coords[pos] = node.id
                    ids.append(by_coords[pos])
                host_a, host_b = ids[:2] if sign > 0 else ids[:2][::-1]
                additions.extend((
                    Wall(id=key, a=host_a, b=host_b, thickness_px=ht, height_m=stub.height_m),
                    Wall(id=key+"-return", a=ids[1], b=ids[2], thickness_px=vt, height_m=stub.height_m),
                ))
                confidence = 0.6+0.3*swing[1]
                span = point(lo, c), point(hi, c)
                openings.append(Opening(
                    id=key+"-opening", kind="door", host_wall_id=key,
                    offset_px=lo-min(u, corner), width_px=hi-lo,
                    span=tuple(Pt(x=x, y=y) for x, y in span),
                    height_m=min(2.1, stub.height_m), confidence=confidence,
                    status="confirmed" if confidence >= confirm_at else "proposed",
                    hinge="start" if swing[3] else "end",
                    swing="left" if swing[4] == (1 if axis == 0 else -1) else "right",
                ))
                apertures.append(LineString([p, q, r]))
    if not openings:
        return model
    walls = [w for w in model.walls if w.id not in replaced_stubs] + additions
    used = {key for w in walls for key in (w.a, w.b)}
    tips = {key for w in model.walls if w.id in replaced_stubs for key in (w.a, w.b)}
    return _join_tees(model.model_copy(update={
        "nodes": [n for n in nodes.values() if n.id not in tips or n.id in used],
        "walls": walls,
        "openings": model.openings+openings,
    }))
