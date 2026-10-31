"""Fit straight wall runs without collapsing an entire connected L/T network.

Adjacent scan rows are associated by their interval endpoints. Perpendicular
branches become separate tracks instead of inflating a component bounding box.
"""

import numpy as np
from .plan_workspace import Segment, Point


def structural_runs(mask, min_length=10, pier_factor=2):
    tracks = []
    for horizontal in (True, False):
        raster = mask if horizontal else mask.T
        active = []
        completed = []
        for y, row in enumerate(raster):
            edges = np.diff(np.r_[False, row > 0, False].astype(np.int8))
            intervals = [
                (int(a), int(b - 1))
                for a, b in zip(np.flatnonzero(edges == 1), np.flatnonzero(edges == -1))
                if b - a >= min_length
            ]
            used = set()
            new = []
            for lo, hi in intervals:
                eligible = []
                for i, t in enumerate(active):
                    if i in used:
                        continue
                    prevlo, prevhi = t[-1][1:]
                    length = min(hi - lo + 1, prevhi - prevlo + 1)
                    if max(abs(lo - prevlo), abs(hi - prevhi)) <= max(
                        3, min(12, length * 0.12)
                    ):
                        eligible.append((abs(lo - prevlo) + abs(hi - prevhi), i))
                if eligible:
                    _, i = min(eligible)
                    t = active[i]
                    used.add(i)
                    t.append((y, lo, hi))
                    new.append(t)
                else:
                    new.append([(y, lo, hi)])
            completed.extend(t for i, t in enumerate(active) if i not in used)
            active = new
        completed.extend(active)
        for track in completed:
            data = np.asarray(track)
            lo = float(np.median(data[:, 1]))
            hi = float(np.median(data[:, 2]))
            thickness = int(data[-1, 0] - data[0, 0] + 1)
            if hi - lo < max(min_length - 1, thickness * pier_factor):
                continue
            center = float((data[0, 0] + data[-1, 0]) / 2)
            start = Point(x=lo, y=center) if horizontal else Point(x=center, y=lo)
            end = Point(x=hi, y=center) if horizontal else Point(x=center, y=hi)
            tracks.append(
                Segment(
                    id=f"run-{len(tracks)}",
                    start=start,
                    end=end,
                    thickness_px=max(1, thickness),
                )
            )
    # Merge overlapping scan bands into their actual strip, not one midpoint's
    # perpendicular branch thickness. Never bridge disjoint opening intervals.
    result = []
    for o in sorted(
        tracks,
        key=lambda o: -np.hypot(o.end.x - o.start.x, o.end.y - o.start.y)
        * o.thickness_px,
    ):
        horizontal = abs(o.end.x - o.start.x) > abs(o.end.y - o.start.y)
        axis = "x" if horizontal else "y"
        cross = "y" if horizontal else "x"
        merged = False
        for p in result:
            if horizontal != (abs(p.end.x - p.start.x) > abs(p.end.y - p.start.y)):
                continue
            lo = max(getattr(o.start, axis), getattr(p.start, axis))
            hi = min(getattr(o.end, axis), getattr(p.end, axis))
            short = min(
                getattr(o.end, axis) - getattr(o.start, axis),
                getattr(p.end, axis) - getattr(p.start, axis),
            )
            if (
                hi - lo < short * 0.25
                or abs(getattr(o.start, cross) - getattr(p.start, cross))
                > (o.thickness_px + p.thickness_px) / 2 + 1
            ):
                continue
            low = min(
                getattr(o.start, cross) - o.thickness_px / 2,
                getattr(p.start, cross) - p.thickness_px / 2,
            )
            high = max(
                getattr(o.start, cross) + o.thickness_px / 2,
                getattr(p.start, cross) + p.thickness_px / 2,
            )
            setattr(p.start, axis, min(getattr(o.start, axis), getattr(p.start, axis)))
            setattr(p.end, axis, max(getattr(o.end, axis), getattr(p.end, axis)))
            setattr(p.start, cross, (low + high) / 2)
            setattr(p.end, cross, (low + high) / 2)
            p.thickness_px = high - low
            merged = True
            break
        if not merged:
            result.append(o)
    return result


def join_intersections(objects):
    """Project endpoints to nearby perpendicular junctions without chain averaging."""
    import copy

    original = copy.deepcopy(objects)
    for o, old in zip(objects, original):
        v = np.array([old.end.x - old.start.x, old.end.y - old.start.y])
        length = np.linalg.norm(v)
        for end in ("start", "end"):
            point = getattr(old, end)
            p = np.array([point.x, point.y])
            choices = []
            for other in original:
                if other.id == old.id:
                    continue
                q = np.array([other.start.x, other.start.y])
                u = np.array([other.end.x - other.start.x, other.end.y - other.start.y])
                other_length = np.linalg.norm(u)
                if abs(np.dot(v, u) / max(1, length * other_length)) > 0.2:
                    continue
                matrix = np.column_stack((v, -u))
                det = np.linalg.det(matrix)
                if abs(det) < 1e-6:
                    continue
                t, s = np.linalg.solve(matrix, q - p)
                intersection = p + t * v
                distance = np.linalg.norm(intersection - p)
                radius = (old.thickness_px + other.thickness_px) / 2 + 2
                if (
                    distance <= radius
                    and -radius / other_length <= s <= 1 + radius / other_length
                ):
                    choices.append((distance, intersection))
            if choices:
                _, p = min(choices, key=lambda c: c[0])
                setattr(o, end, Point(x=float(p[0]), y=float(p[1])))
        if np.hypot(o.end.x - o.start.x, o.end.y - o.start.y) < max(2, length * 0.5):
            o.start = old.start
            o.end = old.end
    return objects
