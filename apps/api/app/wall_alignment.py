"""Align wall axes and weld small seams in the authoritative plan graph."""

from collections import defaultdict
from itertools import product
from hashlib import sha256
import math

from .plan_model import PlanModel, Pt


class Coordinates:
    """Coordinate equality constraints with a fixed displacement budget."""

    def __init__(self, values):
        self.root = {k: k for k in values}
        self.members = {k: {k} for k in values}
        self.values = dict(values)
        self.original = values

    def at(self, key):
        return self.values[self.root[key]]

    def propose(self, a, b, limit):
        a, b = self.root[a], self.root[b]
        if a == b:
            return None
        keys = self.members[a] | self.members[b]
        lo = max(self.original[k] - limit for k in keys)
        hi = min(self.original[k] + limit for k in keys)
        if lo > hi:
            return False
        # Keep the established axis whenever possible.
        return a, b, min(hi, max(lo, self.values[a])), keys

    def commit(self, proposal):
        if proposal is None:
            return
        a, b, value, keys = proposal
        self.values[a] = value
        self.members[a] = keys
        del self.members[b]
        for k in keys:
            self.root[k] = a


def align_walls(model: PlanModel) -> PlanModel:
    """Repair near-axis walls and local joints without bridging unknown openings."""
    nodes = {n.id: n for n in model.nodes}
    old = {n.id: (n.x, n.y) for n in model.nodes}
    coords = [Coordinates({k: p[i] for k, p in old.items()}) for i in range(2)]
    incident = defaultdict(list)
    axes = {}
    required = defaultdict(lambda: 1e-5)
    for o in model.openings:
        if o.host_wall_id:
            required[o.host_wall_id] = max(required[o.host_wall_id], o.width_px)

    def point(k):
        return tuple(c.at(k) for c in coords)

    def valid_move(updates):
        touched = {w.id: w for k in updates for w in incident[k]}
        for w in touched.values():
            a, b = point(w.a), point(w.b)
            p, q = updates.get(w.a, a), updates.get(w.b, b)
            length = math.dist(p, q)
            if length + 1e-8 < min(math.dist(a, b), max(1e-5, required[w.id] - 0.49)):
                return False
            if length < 1e-5 or sum((b[i] - a[i]) * (q[i] - p[i]) for i in range(2)) <= 0:
                return False
        return True

    def apply(proposals):
        if any(p is False for p in proposals):
            return False
        changed = {}
        for i, p in enumerate(proposals):
            if p is not None:
                for k in p[3]:
                    changed.setdefault(k, list(point(k)))[i] = p[2]
        if not valid_move(changed):
            return False
        for c, p in zip(coords, proposals):
            c.commit(p)
        return True

    lengths = {w.id: math.dist(old[w.a], old[w.b]) for w in model.walls}
    for w in model.walls:
        incident[w.a].append(w)
        incident[w.b].append(w)
    for w in sorted(model.walls, key=lambda w: (-lengths[w.id], w.id)):
        a, b = old[w.a], old[w.b]
        dx, dy = abs(b[0] - a[0]), abs(b[1] - a[1])
        axis = 0 if dx >= dy else 1
        drift = min(dx, dy)
        # Thick extracted fragments can acquire steep angles from a few
        # pixels of endpoint error. Leave deliberate diagonals alone.
        close = drift <= max(dx, dy) * math.tan(math.radians(8))
        stub = w.source == "extracted" and drift <= min(8, 0.5 * w.thickness_px)
        if not (close or stub):
            continue
        cross = 1 - axis
        c = coords[cross]
        p = c.propose(w.a, w.b, 8)
        if p is not False and p is not None and len(c.members[p[0]]) == len(c.members[p[1]]) == 1:
            p = p[:2] + ((a[cross] + b[cross]) / 2,) + p[3:]
        proposals = [None, None]
        proposals[cross] = p
        if apply(proposals):
            axes[w.id] = axis

    # Close only small local seams. A collinear pair must face into the
    # seam; nearby parallel walls with overlapping runs are not one wall.
    parent = {k: k for k in nodes}
    ends = defaultdict(list)
    for w in model.walls:
        if w.id in axes:
            ends[w.a].append((w, w.b))
            ends[w.b].append((w, w.a))

    def root(k):
        while parent[k] != k:
            k = parent[k]
        return k

    def joint(a, b):
        p, q = point(a), point(b)
        for w, far_a in ends[a]:
            for v, far_b in ends[b]:
                if w.id == v.id:
                    continue
                axis, other = axes[w.id], axes[v.id]
                limit = min(9.0, 1 + 0.55 * max(w.thickness_px, v.thickness_px))
                if max(abs(p[i] - q[i]) for i in range(2)) > limit:
                    continue
                da = p[axis] - point(far_a)[axis]
                db = q[other] - point(far_b)[other]
                if axis == other:
                    if da * db >= 0 or (q[axis] - p[axis]) * math.copysign(1, da) < -1:
                        continue
                elif ((q[axis] - p[axis]) * math.copysign(1, da) < -1
                      or (p[other] - q[other]) * math.copysign(1, db) < -1):
                    continue
                return True
        return False

    ordered = sorted(ends, key=lambda k: (*point(k), k))
    positions = {k: point(k) for k in ordered}
    candidates = []
    for i, a in enumerate(ordered):
        for j in range(i + 1, len(ordered)):
            b = ordered[j]
            if positions[b][0] - positions[a][0] > 9:
                break
            if abs(positions[b][1] - positions[a][1]) <= 9 and joint(a, b):
                candidates.append((math.dist(positions[a], positions[b]), a, b))
    for _, a, b in sorted(candidates):
        if root(a) == root(b) or not joint(a, b):
            continue
        choices = []
        for c in coords:
            first, second = a, b
            if len(c.members[c.root[b]]) > len(c.members[c.root[a]]):
                first, second = b, a
            choices.append((c.propose(first, second, 8), c.propose(second, first, 8)))
        for proposals in product(*choices):
            if apply(proposals):
                parent[root(b)] = root(a)
                break

    walls = [w.model_copy(update={"a": root(w.a), "b": root(w.b)}) for w in model.walls]
    by_id = {w.id: w for w in walls}
    original = {w.id: w for w in model.walls}
    openings = []
    for o in model.openings:
        w = by_id.get(o.host_wall_id)
        if w is None:
            openings.append(o)
            continue
        src = original[w.id]
        a, b = old[src.a], old[src.b]
        p, q = point(w.a), point(w.b)
        if (a, b) == (p, q):
            openings.append(o)
            continue
        length = math.dist(p, q)
        if length < o.width_px - 0.5:
            # Older valid plans can contain subpixel host overhangs. Never
            # shorten a recorded opening to make an alignment fit.
            return model
        before = math.dist(a, b)
        t = (o.offset_px + o.width_px / 2) / before if before else 0
        centre = tuple(a[i] + (b[i] - a[i]) * t for i in range(2))
        unit = tuple((q[i] - p[i]) / length for i in range(2))
        offset = sum((centre[i] - p[i]) * unit[i] for i in range(2)) - o.width_px / 2
        offset = max(0, min(length - o.width_px, offset))
        span = tuple(Pt(x=p[0] + unit[0] * d, y=p[1] + unit[1] * d)
                     for d in (offset, offset + o.width_px))
        openings.append(o.model_copy(update={"offset_px": offset, "span": span}))

    kept = [n.model_copy(update={"x": point(n.id)[0], "y": point(n.id)[1]})
            for n in model.nodes if root(n.id) == n.id]
    return _join_tees(model.model_copy(update={"nodes": kept, "walls": walls, "openings": openings}))


def _join_tees(model):
    """Split a perpendicular host at a nearby dangling end outside openings."""
    nodes = {n.id: n for n in model.nodes}
    walls = {w.id: w for w in model.walls}
    hosted = defaultdict(list)
    incident = defaultdict(list)
    for i, o in enumerate(model.openings):
        hosted[o.host_wall_id].append((i, o))
    openings = list(model.openings)
    for w in walls.values():
        incident[w.a].append(w.id)
        incident[w.b].append(w.id)

    def axis(a, b):
        if a.y == b.y and a.x != b.x:
            return "x"
        if a.x == b.x and a.y != b.y:
            return "y"
        return None

    for k, ids in incident.items():
        if len(ids) != 1:
            continue
        w = walls[ids[0]]
        if k not in (w.a, w.b) or hosted[w.id]:
            continue
        p, q = nodes[k], nodes[w.b if k == w.a else w.a]
        along = axis(p, q)
        if along is None:
            continue
        cross = "y" if along == "x" else "x"
        pa, qa, pc = getattr(p, along), getattr(q, along), getattr(p, cross)
        choices = []
        for host in walls.values():
            a, b = nodes[host.a], nodes[host.b]
            if axis(a, b) != cross:
                continue
            target = getattr(a, along)
            delta = target - pa
            if delta * (pa - qa) < -1e-8 or abs(delta) > min(6, (w.thickness_px + host.thickness_px) / 2):
                continue
            ac, bc = getattr(a, cross), getattr(b, cross)
            if not min(ac, bc) + 1 < pc < max(ac, bc) - 1:
                continue
            cut = abs(pc - ac)
            if any(o.offset_px + o.width_px > cut > o.offset_px for _, o in hosted[host.id]):
                continue
            choices.append((abs(delta), host.id, target, cut))
        if not choices or len(walls) >= 10000:
            continue
        _, wid, target, cut = min(choices)
        host = walls[wid]
        new_id = "join-" + sha256(f"{wid}:{k}".encode()).hexdigest()[:24]
        if new_id in walls:
            continue
        nodes[k] = p.model_copy(update={along: target})
        walls[wid] = host.model_copy(update={"b": k})
        walls[new_id] = host.model_copy(update={"id": new_id, "a": k})
        # Update endpoint incidence in place; all node keys already exist.
        incident[host.b].remove(wid)
        incident[host.b].append(new_id)
        incident[k].extend((wid, new_id))
        stay = []
        for i, o in hosted[wid]:
            if o.offset_px >= cut:
                o = o.model_copy(update={"host_wall_id": new_id, "offset_px": o.offset_px - cut})
                hosted[new_id].append((i, o))
                openings[i] = o
            else:
                stay.append((i, o))
        hosted[wid] = stay
    return model.model_copy(update={"nodes": list(nodes.values()), "walls": list(walls.values()),
                                    "openings": openings})

