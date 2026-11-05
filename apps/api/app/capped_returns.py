"""Recover short, outlined wall returns missed by the main wall detector."""
from hashlib import sha256

import cv2
import numpy as np
from shapely.geometry import LineString, Polygon

from .plan_model import Node, Wall
from .plan_workspace import Point, Segment


def detect_returns(image, strips):
    if strips.boundary_mask is None or strips.structural_colour is None:
        return []
    tint = strips.structural_colour.astype(np.uint8)
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    minimum = max(10, round(0.04 * min(tint.shape)))
    maximum = max(3 * minimum, round(0.15 * min(tint.shape)))
    candidates = []
    for vertical in (True, False):
        # In this view the first axis is always the length of the return.
        src, g = (tint, gray) if vertical else (tint.T, gray.T)
        opened = cv2.morphologyEx(src, cv2.MORPH_OPEN, np.ones((minimum, 3), np.uint8))
        _, _, stats, _ = cv2.connectedComponentsWithStats(opened)
        for x, y, width, length, area in stats[1:]:
            if not (minimum <= length <= maximum and 3 <= width <= 0.7 * minimum
                    and length >= 3 * width and area >= 0.8 * width * length):
                continue
            if x < 4 or x + width + 4 >= g.shape[1]:
                continue
            lane = x + (width - 1) / 2
            body = g[y:y + length]
            middle = body[:, round(lane)].astype(float)
            left = body[:, x - 3:x + 1].min(axis=1)
            right = body[:, x + width - 1:x + width + 3].min(axis=1)
            if min(np.mean(middle - left >= 24), np.mean(middle - right >= 24)) < 0.75:
                continue
            for direction in (-1, 1):
                near, anchor = (y, y + length - 1) if direction < 0 else (y + length - 1, y)
                for gap in range(1, 8):
                    tip = near + direction * gap
                    beyond = tip + direction * 2
                    if not (0 <= tip < len(g) and 0 <= beyond < len(g)):
                        break
                    # A wall end has a dark crossbar and clear paper beyond.
                    # This rejects continuing dimension strokes and open gaps.
                    cap = g[tip, x:x + width]
                    if np.max(cap) > np.median(middle) - 35:
                        continue
                    if np.median(g[beyond, x:x + width]) < np.median(middle) - 10:
                        continue
                    def point(along):
                        return Point(x=lane, y=along) if vertical else Point(x=along, y=lane)
                    candidates.append(Segment(
                        id=f"return-{int(vertical)}-{x}-{tip}", start=point(tip), end=point(anchor),
                        thickness_px=width + 1, boundary_supported=True,
                    ))
                    break
    return candidates[:100]


def restore_returns(model, candidates):
    """Add only interior, perpendicular returns anchored to a solid wall face."""
    from .wall_alignment import _join_tees

    if not candidates or not model.walls:
        return model
    nodes = {n.id: n for n in model.nodes}
    walls = list(model.walls)
    lines = {w.id: LineString([(nodes[k].x, nodes[k].y) for k in (w.a, w.b)]) for w in walls}
    coords = [xy for line in lines.values() for xy in line.coords]
    bounds = [(min(p[i] for p in coords), max(p[i] for p in coords)) for i in (0, 1)]
    envelope = Polygon([(p.x, p.y) for p in model.envelope]) if model.envelope else None
    apertures = []
    for opening in model.openings:
        if opening.status == "rejected":
            continue
        host = lines.get(opening.host_wall_id)
        if host is not None:
            span = [host.interpolate(d).coords[0]
                    for d in (opening.offset_px, opening.offset_px + opening.width_px)]
        elif opening.span:
            span = [(p.x, p.y) for p in opening.span]
        else:
            continue
        apertures.append(LineString(span))

    for run in candidates:
        tip, tail = (run.start.x, run.start.y), (run.end.x, run.end.y)
        axis = 1 if tip[0] == tail[0] else 0
        cross = 1 - axis
        width = run.thickness_px
        if not all(lo + width < v < hi - width for v, (lo, hi) in zip(tip, bounds)):
            continue
        choices = []
        for wall in walls:
            p, q = lines[wall.id].coords
            if abs(p[axis] - q[axis]) > 1e-5:
                continue
            lo, hi = sorted((p[cross], q[cross]))
            if not lo + width / 2 < tail[cross] < hi - width / 2:
                continue
            gap = abs(p[axis] - tail[axis])
            if (gap <= wall.thickness_px / 2 + min(6, width)
                    and (p[axis] - tip[axis]) * (tail[axis] - tip[axis]) > 0):
                choices.append((gap, wall.id, p[axis]))
        if not choices:
            continue
        _, host, at = min(choices)
        joint = (tail[0], at) if axis else (at, tail[1])
        path = LineString([tip, joint])
        if envelope is not None and not envelope.covers(path):
            continue
        if any(path.distance(hole) < width / 2 for hole in apertures):
            continue
        # Ignore the anchor's own footprint. Other intersecting geometry
        # means this is already represented or is not a free-ended return.
        if any(path.distance(lines[w.id]) < (width + w.thickness_px) / 2
               for w in walls if w.id != host):
            continue
        wid = "source-" + sha256(run.id.encode()).hexdigest()[:20]
        a, b = wid + "-a", wid + "-b"
        if wid in lines or a in nodes or b in nodes or len(walls) >= 9998 or len(nodes) >= 19998:
            continue
        nodes[a], nodes[b] = Node(id=a, x=tip[0], y=tip[1]), Node(id=b, x=joint[0], y=joint[1])
        walls.append(Wall(id=wid, a=a, b=b, thickness_px=width))
        lines[wid] = path
    if len(walls) == len(model.walls):
        return model
    return _join_tees(model.model_copy(update={"nodes": list(nodes.values()), "walls": walls}))
