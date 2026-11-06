"""Remove traced swing symbols and recover painted partitions beside door jambs."""
from collections import defaultdict
from hashlib import sha256
import math

import numpy as np
from shapely.geometry import LineString

from .plan_model import Node, Wall
from .wall_alignment import _join_tees


def _axis(a, b):
    if abs(a.y - b.y) < 1e-5 and abs(a.x - b.x) > 1e-5:
        return 0
    if abs(a.x - b.x) < 1e-5 and abs(a.y - b.y) > 1e-5:
        return 1
    return None


def _coords(p):
    return p.x, p.y


def _samples(mask, a, b, radius):
    a, b = np.asarray(a, float), np.asarray(b, float)
    d = b - a
    length = np.linalg.norm(d)
    if length < 1e-5:
        return np.zeros(1)
    p = np.linspace(a, b, max(4, round(length)))
    normal = np.array([-d[1], d[0]]) / length
    x, y = np.rint(p[None] + np.arange(-radius, radius + 1)[:, None, None] * normal).astype(int).transpose(2, 0, 1)
    h, w = mask.shape
    valid = (x >= 0) & (x < w) & (y >= 0) & (y < h)
    return (valid & mask[y.clip(0, h - 1), x.clip(0, w - 1)]).sum(axis=0)


def repair_photo_doors(model, strips):
    """Adjust extracted geometry only; preserve apertures and manually drawn walls."""
    tint = strips.source_tint
    if strips.boundary_mask is None or tint is None:
        return model

    nodes = {n.id: n for n in model.nodes}
    walls = {w.id: w for w in model.walls}
    hosted = {o.host_wall_id for o in model.openings}
    doors, apertures = [], []
    for o in model.openings:
        if o.status == "rejected" or not o.span:
            continue
        host = walls.get(o.host_wall_id)
        if host is not None:
            a, b = nodes[host.a], nodes[host.b]
            distance = math.dist(_coords(a), _coords(b))
            if distance < 1e-5:
                continue
            unit = (np.array(_coords(b)) - _coords(a)) / distance
            p, q = (np.array(_coords(a)) + d * unit for d in (o.offset_px, o.offset_px + o.width_px))
        else:
            p, q = (np.array(_coords(x)) for x in o.span)
        apertures.append((o.id, LineString([p, q])))
        if o.kind == "door" and host and o.swing and o.confidence >= 0.8:
            axis = _axis(nodes[host.a], nodes[host.b])
            if axis is not None:
                doors.append((o, host, axis, p, q))
    if not doors:
        return model

    incident = defaultdict(list)
    for w in walls.values():
        incident[w.a].append(w)
        incident[w.b].append(w)
    removed = set()
    for w in walls.values():
        if w.source != "extracted" or w.id in hosted:
            continue
        a, b = nodes[w.a], nodes[w.b]
        axis = _axis(a, b)
        if axis is None:
            continue
        u, v = np.array(_coords(a)), np.array(_coords(b))
        length = np.linalg.norm(v - u)
        # Check the narrow core of the stroke. A wide band can pick up the
        # real partition a few pixels beside the neutral door leaf.
        paint = _samples(tint, u + 0.19 * (v - u), v - 0.19 * (v - u), 1)
        if np.mean(paint >= 1) >= 0.25:
            continue
        for o, host, door_axis, p, q in doors:
            width = o.width_px
            normal = np.array((p[1] - q[1], q[0] - p[0])) / width
            hinge = q if o.hinge == "end" else p
            end = hinge + normal * width * (-1 if o.swing == "right" else 1)
            if (axis != door_axis and 0.65 * width <= length <= 1.35 * width
                    and min(np.linalg.norm(u - hinge) + np.linalg.norm(v - end),
                            np.linalg.norm(v - hinge) + np.linalg.norm(u - end)) <= 0.28 * width):
                removed.add(w.id)
                break
            # A dangling tip at a T near the door may be a dimension or an
            # outline overrun. A second collinear arm must face into the T.
            if length > min(24, 0.57 * width) or min(math.dist(u, p), math.dist(v, p),
                                                        math.dist(u, q), math.dist(v, q)) > 1.75 * width:
                continue
            for root, tip in ((w.a, w.b), (w.b, w.a)):
                if len(incident[tip]) != 1 or len(incident[root]) < 3:
                    continue
                pos = getattr(nodes[root], "x" if axis == 0 else "y")
                direct = getattr(nodes[tip], "x" if axis == 0 else "y") - pos
                others = [n for n in incident[root] if n.id != w.id]
                if any(_axis(nodes[n.a], nodes[n.b]) == axis
                       and (getattr(nodes[n.b if n.a == root else n.a], "x" if axis == 0 else "y") - pos)
                       * direct < 0 for n in others):
                    removed.add(w.id)
                    break
            if w.id in removed:
                break

    for wid in removed:
        del walls[wid]
    initial = len(walls)
    _restore_returns(model, walls, nodes, doors, apertures, tint)
    if not removed and len(walls) == initial:
        return model
    used = {k for w in walls.values() for k in (w.a, w.b)}
    return _join_tees(model.model_copy(update={
        "walls": list(walls.values()), "nodes": [n for k, n in nodes.items() if k in used],
    }))


def _restore_returns(model, walls, nodes, doors, apertures, tint):
    """Only recover an L with both painted arms and an existing far wall."""
    from shapely.geometry import Polygon

    envelope = Polygon([_coords(p) for p in model.envelope]) if model.envelope else None
    at = {_coords(n): n.id for n in nodes.values()}

    def spans(axis, lane):
        other = 1 - axis
        return sorted((min(a[axis], b[axis]), max(a[axis], b[axis]))
                      for w in walls.values() if _axis(nodes[w.a], nodes[w.b]) == axis
                      and (a := _coords(nodes[w.a]))[other] == lane
                      and (b := _coords(nodes[w.b]))[other] == lane)

    def add_missing(a, b, axis, thickness, host):
        lo, hi = sorted((a[axis], b[axis]))
        lane = a[1 - axis]
        parts = []
        cursor = lo
        for start, end in spans(axis, lane):
            if end < cursor or start > hi:
                continue
            if start > cursor:
                parts.append((cursor, start))
            cursor = max(cursor, end)
        if hi > cursor:
            parts.append((cursor, hi))
        for start, end in parts:
            if end - start < 1:
                continue
            ends = [(d, lane) if axis == 0 else (lane, d) for d in (start, end)]
            key = "door-return-" + sha256(str(ends).encode()).hexdigest()[:16]
            if key in walls or len(walls) >= 9998 or len(nodes) >= 19998:
                continue
            for i, point in enumerate(ends):
                if point not in at:
                    node = Node(id=f"{key}-{i}", x=point[0], y=point[1])
                    at[point] = node.id
                    nodes[node.id] = node
            walls[key] = Wall(id=key, a=at[ends[0]], b=at[ends[1]], thickness_px=thickness,
                              height_m=host.height_m)

    for o, host, axis, p, q in doors:
        if host.id not in walls or host.source == "user":
            continue
        other = 1 - axis
        width = o.width_px
        lane = float(p[other])
        raster = tint.T if axis == 0 else tint
        radius = max(2, min(7, round(width * 0.13)))
        cross = round(lane)
        for sign, jamb in [(-1, min(p[axis], q[axis])), (1, max(p[axis], q[axis]))]:
            positions = round(jamb) + sign * np.arange(1, round(1.65 * width) + 1)
            positions = positions[(positions >= 0) & (positions < raster.shape[0])]
            band = raster[positions, max(0, cross - radius):cross + radius + 1].sum(axis=1)
            low = np.flatnonzero(band < 3)
            stop = next((j for j in low if j > 2 and j + 3 < len(band) and max(band[j:j + 4]) < 3), len(band))
            solid = np.flatnonzero(band[:stop] >= 3)
            if (not len(solid) or solid[0] > 5 or solid[-1] < 0.56 * width
                    or len(solid) / (solid[-1] + 1) < 0.88):
                continue
            distal = positions[solid[-1]]
            options = []
            # If an existing partition is on this track, don't draw a
            # parallel replacement just because its center is a pixel off.
            existing = {
                _coords(nodes[v.a])[axis] for v in walls.values()
                if _axis(nodes[v.a], nodes[v.b]) == other
                and abs(_coords(nodes[v.a])[axis] - distal) <= radius + 2
                and min(abs(_coords(nodes[k])[other] - lane) for k in (v.a, v.b)) <= 0.55 * width
                and math.dist(_coords(nodes[v.a]), _coords(nodes[v.b])) >= 0.35 * width
            }
            corners = sorted(existing) if existing else range(int(distal) - radius, int(distal) + radius + 1)
            for w in walls.values():
                a, b = nodes[w.a], nodes[w.b]
                wa, wb = _coords(a), _coords(b)
                if _axis(a, b) != axis or not 1.55 * width <= abs(wa[other] - lane) <= 3.4 * width:
                    continue
                lo, hi = sorted((wa[axis], wb[axis]))
                for corner in corners:
                    if not lo - 1e-5 <= corner <= hi + 1e-5 or not 0.55 * width <= (corner - jamb) * sign <= 1.72 * width:
                        continue
                    top = (corner, lane) if axis == 0 else (lane, corner)
                    end = (corner, wa[other]) if axis == 0 else (wa[other], corner)
                    begin = (jamb, lane) if axis == 0 else (lane, jamb)
                    # Paint from the original scan, not the filled wall mask.
                    a1, a2 = np.array(top), np.array(end)
                    profile = _samples(tint, a1 + 0.06 * (a2 - a1), a2 - 0.06 * (a2 - a1), radius)
                    if np.mean(profile >= 3) < 0.94:
                        continue
                    if any(
                        1e-5 < abs(_coords(nodes[v.a])[axis] - corner) <= radius + 2
                        and min(max(_coords(nodes[k])[other] for k in (v.a, v.b)), max(top[other], end[other]))
                        - max(min(_coords(nodes[k])[other] for k in (v.a, v.b)), min(top[other], end[other]))
                        > 0.35 * width
                        for v in walls.values() if _axis(nodes[v.a], nodes[v.b]) == other
                    ):
                        continue
                    # The painted path may touch its own jamb but must never
                    # cross any other opening or leave a user-drawn outline.
                    path = LineString([begin, top, end])
                    if envelope is not None and not envelope.covers(path):
                        continue
                    if any(path.distance(s) < 2 for oid, s in apertures if oid != o.id):
                        continue
                    options.append((np.mean(profile), -abs(corner - distal),
                                    begin, top, end, float(np.median(profile))))
            if options:
                _, _, begin, top, end, return_width = max(options)
                add_missing(begin, top, axis, float(np.clip(np.median(band[solid]), 3, 2 * radius + 1)), host)
                add_missing(top, end, other, float(np.clip(return_width, 3, 2 * radius + 1)), host)
