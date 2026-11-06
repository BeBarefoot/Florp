"""Discard detached photo marks without treating a detected aperture as masonry."""

from collections import defaultdict
from dataclasses import dataclass
import math


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


def prune_detached_photo_walls(model, objects):
    """Keep the main building, substantial traced walls, and genuine nearby piers."""
    walls = {w.id: w for w in model.walls}
    nodes = {n.id: n for n in model.nodes}
    incident = defaultdict(list)
    for w in walls.values():
        incident[w.a].append(w.id)
        incident[w.b].append(w.id)
    lengths = {w.id: math.hypot(nodes[w.a].x - nodes[w.b].x, nodes[w.a].y - nodes[w.b].y)
               for w in walls.values()}
    seen = set()
    groups = []
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
    if len(groups) < 2:
        return model, 0

    core = max(groups, key=lambda ids: sum(lengths[k] for k in ids))
    corners = [nodes[k] for wid in core for k in (walls[wid].a, walls[wid].b)]
    width, height = model.image_transform.width, model.image_transform.height
    if (sum(lengths[k] for k in core) < 0.55 * sum(lengths.values())
            or max(p.x for p in corners) - min(p.x for p in corners) < 0.2 * width
            or max(p.y for p in corners) - min(p.y for p in corners) < 0.2 * height):
        return model, 0  # no reliable main building; leave fragments for review

    measured, physical = [], []
    for o in objects:
        if o.kind != "wall" or o.id.startswith("gap-host-"):
            continue
        r = Run.from_points(o.start, o.end, o.thickness_px)
        if r is not None:
            measured.append(r)
            if o.boundary_supported or o.material == "concrete":
                physical.append(r)
    traces = {w.id: Run.from_points(nodes[w.a], nodes[w.b], w.thickness_px) for w in walls.values()}
    anchor = [traces[k] for k in core if traces[k] is not None]
    keep = set(core)
    for group in groups:
        if group is core:
            continue
        for wid in group:
            r = traces[wid]
            if r is None:  # this axis-only evidence cannot judge sloped walls
                keep.update(group)
                break
            substantial = r.length >= max(0.06 * min(width, height), 4 * r.thickness)
            # A short isolated pier can be real if it faces the main wall
            # across a gap. Merely being parallel or near another orphan
            # doesn't make a dimension leader part of the building.
            gaps = [(max(r.lo, s.lo) - min(r.hi, s.hi), max(r.thickness, s.thickness))
                    for s in anchor if r.same_lane(s)]
            faces_core = any(-1 <= gap <= 2 * thickness for gap, thickness in gaps)
            close_seam = any(-1 <= gap <= max(8, min(12, thickness)) for gap, thickness in gaps)
            if ((substantial or faces_core) and r.coverage(physical) >= 0.75
                    or close_seam and r.coverage(measured) >= 0.75):
                keep.update(group)
                break
    if len(keep) == len(walls):
        return model, 0
    retained = [w for w in model.walls if w.id in keep]
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
        "nodes": [n for n in model.nodes if n.id in node_ids],
        "openings": [o for o in model.openings if keep_opening(o)],
    }), len(walls) - len(keep)
