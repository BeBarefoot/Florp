"""Discard detached photo marks without treating a detected aperture as masonry."""

from collections import defaultdict
from dataclasses import dataclass


@dataclass(frozen=True)
class Run:
    horizontal: bool
    lane: float
    lo: float
    hi: float
    thickness: float

    @classmethod
    def from_points(cls, a, b, thickness):
        dx, dy = abs(a.x - b.x), abs(a.y - b.y)
        if min(dx, dy) > 0.1 * max(dx, dy) or max(dx, dy) < 1e-5:
            return None
        if dx >= dy:
            return cls(True, (a.y + b.y) / 2, min(a.x, b.x), max(a.x, b.x), thickness)
        return cls(False, (a.x + b.x) / 2, min(a.y, b.y), max(a.y, b.y), thickness)

    @property
    def length(self):
        return self.hi - self.lo

    def same_lane(self, other):
        return self.horizontal == other.horizontal and abs(self.lane - other.lane) <= min(
            6, 1 + max(self.thickness, other.thickness) / 2
        )

    def coverage(self, sources):
        intervals = sorted(
            (max(self.lo, s.lo), min(self.hi, s.hi))
            for s in sources if self.same_lane(s) and min(self.hi, s.hi) > max(self.lo, s.lo)
        )
        end, covered = self.lo, 0.0
        for lo, hi in intervals:
            covered += max(0.0, hi - max(end, lo))
            end = max(end, hi)
        return covered / self.length


def _groups(walls):
    incident = defaultdict(list)
    for w in walls.values():
        incident[w.a].append(w.id)
        incident[w.b].append(w.id)
    seen, groups = set(), []
    for wid in walls:
        if wid in seen:
            continue
        group, pending = [], [wid]
        seen.add(wid)
        while pending:
            current = pending.pop()
            group.append(current)
            w = walls[current]
            for other in incident[w.a] + incident[w.b]:
                if other not in seen:
                    seen.add(other)
                    pending.append(other)
        groups.append(group)
    return groups


def prune_detached_photo_walls(model, objects):
    """Prune unsupported islands once a building wall network has been found."""
    walls = {w.id: w for w in model.walls}
    nodes = {n.id: n for n in model.nodes}
    groups = _groups(walls)
    if len(groups) < 2:
        return model, 0

    def trace(w):
        return Run.from_points(nodes[w.a], nodes[w.b], w.thickness_px)

    measured, physical = [], []
    for o in objects:
        if o.kind != "wall" or o.id.startswith("gap-host-"):
            continue
        r = Run.from_points(o.start, o.end, o.thickness_px)
        if r is not None:
            measured.append(r)
            if o.boundary_supported or o.material == "concrete":
                physical.append(r)
    traces = {w.id: trace(w) for w in walls.values()}
    width, height = model.image_transform.width, model.image_transform.height
    short_side = min(width, height)
    evidence = {k: r.coverage(physical) if r else 0 for k, r in traces.items()}

    def spans_building(group):
        corners = [nodes[k] for wid in group for k in (walls[wid].a, walls[wid].b)]
        return (len(group) > 1
                and max(p.x for p in corners) - min(p.x for p in corners) >= 0.15 * width
                and max(p.y for p in corners) - min(p.y for p in corners) >= 0.15 * height)

    candidates = [group for group in groups if spans_building(group)]
    if not candidates:
        return model, 0  # no building network to distinguish from clutter
    # A pile of isolated strokes must not prevent cleanup of a real building.
    core = max(candidates, key=lambda ids: sum(
        (traces[k].length * traces[k].coverage(measured)) if traces[k] else 0 for k in ids
    ))
    if not any(traces[k] and traces[k].coverage(measured) >= 0.75 for k in core):
        return model, 0

    hosted = {o.host_wall_id for o in model.openings}
    apertures = [
        r for o in model.openings if o.span and o.status != "rejected"
        and (r := Run.from_points(*o.span, 2)) is not None
    ]

    def seam_clear(r, a, b):
        lo, hi = sorted((a, b))
        return all(not r.same_lane(o) or min(hi, o.hi) - max(lo, o.lo) < 1 for o in apertures)

    def endpoints(w, axis):
        return sorted((w.a, w.b), key=lambda k: getattr(nodes[k], axis))

    def attach_pier(w, r):
        if w.id in hosted or w.source != "extracted" or not r:
            return False
        if (evidence[w.id] < 0.75
                and (r.length < max(3 * r.thickness, 0.06 * short_side) or r.coverage(measured) < 0.75)):
            return False
        axis, cross = ("x", "y") if r.horizontal else ("y", "x")
        lo, hi = endpoints(w, axis)
        options = []
        for k in core:
            target = walls[k]
            s = traces[k]
            if not s or not r.same_lane(s) or abs(r.lane - s.lane) > 4.5:
                continue
            left, right = endpoints(target, axis)
            for gap, end, free, anchor, a, b in [
                (s.lo - r.hi, hi, lo, left, r.hi, s.lo),
                (r.lo - s.hi, lo, hi, right, s.hi, r.lo),
            ]:
                if 0 <= gap <= 8 and seam_clear(s, a, b):
                    options.append((gap, abs(r.lane - s.lane), end, free, anchor))
        if not options:
            return False
        _, _, end, free, anchor = min(options)
        nodes[free] = nodes[free].model_copy(update={cross: getattr(nodes[anchor], cross)})
        walls[w.id] = w.model_copy(update={"a" if w.a == end else "b": anchor})
        return True

    def long_traced(wid):
        r = traces[wid]
        return (r is not None and walls[wid].source == "extracted" and wid not in hosted
                and evidence[wid] >= 0.85 and r.length >= max(0.2 * short_side, 5 * r.thickness))

    def join_traced_corner(first, second):
        # Two long walls with independently observed faces can meet at an L
        # even if the scanner lost a thickness-sized patch at the corner.
        a, b = traces[first], traces[second]
        if a.horizontal == b.horizontal:
            return False
        if not a.horizontal:
            first, second, a, b = second, first, b, a
        u, v = walls[first], walls[second]
        end_u = min((u.a, u.b), key=lambda k: abs(nodes[k].x - b.lane))
        end_v = min((v.a, v.b), key=lambda k: abs(nodes[k].y - a.lane))
        gap_u, gap_v = abs(nodes[end_u].x - b.lane), abs(nodes[end_v].y - a.lane)
        reach = min(22, 1 + max(a.thickness, b.thickness))
        if (max(gap_u, gap_v) > reach or min(gap_u, gap_v) > 0.5 * reach
                or not seam_clear(a, nodes[end_u].x, b.lane)
                or not seam_clear(b, nodes[end_v].y, a.lane)):
            return False
        nodes[end_u] = nodes[end_u].model_copy(update={"x": b.lane, "y": a.lane})
        walls[second] = v.model_copy(update={"a" if v.a == end_v else "b": end_u})
        return True

    singles = [g[0] for g in groups if len(g) == 1]
    reconnected = {k for k in singles if attach_pier(walls[k], traces[k])}
    for i, first in enumerate(singles):
        if first in reconnected or not long_traced(first):
            continue
        for second in singles[i + 1:]:
            if second not in reconnected and long_traced(second) and join_traced_corner(first, second):
                reconnected.update((first, second))
                break

    def has_traced_junction(group):
        arms = defaultdict(set)
        for k in group:
            r = traces[k]
            if (r and evidence[k] >= 0.75
                    and r.length >= max(0.045 * short_side, 2.5 * r.thickness)):
                for endpoint in (walls[k].a, walls[k].b):
                    arms[endpoint].add(r.horizontal)
        return any(len(directions) > 1 for directions in arms.values())

    keep = set(core) | reconnected
    for group in groups:
        if any(walls[k].source == "user" for k in group) or has_traced_junction(group):
            keep.update(group)
    if len(keep) == len(walls) and not reconnected:
        return model, 0
    retained = [w for k, w in walls.items() if k in keep]
    node_ids = {k for w in retained for k in (w.a, w.b)}
    discarded_traces = [r for k, r in traces.items() if k not in keep and r is not None]
    retained_traces = [r for k, r in traces.items() if k in keep and r is not None]

    def keep_opening(o):
        if o.host_wall_id:
            return o.host_wall_id in keep
        if not o.span:
            return True
        r = Run.from_points(*o.span, 2)
        return (r is None or r.coverage(discarded_traces) < 0.8
                or r.coverage(retained_traces) >= 0.2)

    return model.model_copy(update={
        "walls": retained,
        "nodes": [n for n in nodes.values() if n.id in node_ids],
        "openings": [o for o in model.openings if keep_opening(o)],
    }), len(walls) - len(keep)
