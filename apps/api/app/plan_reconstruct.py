"""Turn raw extractor segments into a connected PlanModel v2.

Order: straighten near-axis runs, merge collinear fragments (bridging a gap only
when covered by classified opening evidence), snap L/T junctions to shared
nodes, split at T-junctions and crossings, prune dangling stubs, then host
openings on the consolidated walls. Openings the pipeline is unsure about stay
``proposed`` until the user decides; nothing is auto-confirmed below threshold.
"""

from __future__ import annotations
import math
from dataclasses import dataclass, field
from statistics import median
from .plan_model import PlanModel, Node, Wall, Opening, Pt, ImageTransform, Scale
from .plan_workspace import Document


@dataclass
class ReconstructConfig:
    straighten_deg: float = 3.0
    gap_merge_factor: float = 1.5  # compatibility only; plain gaps are never filled
    opening_gap_cover: float = 0.6
    auto_confirm: float = 0.85
    auto_confirm_by_kind: dict[str, float] = field(default_factory=dict)
    min_length_px: float = 12.0


def configured_config():
    cfg = ReconstructConfig()
    from .config import settings

    if settings.opening_confidence_profile:
        from .opening_calibration import load_profile

        cfg.auto_confirm_by_kind = load_profile(
            settings.opening_confidence_profile
        ).thresholds
    return cfg


@dataclass
class Run:
    a: list[float]
    b: list[float]
    t: float
    material: str = "block"
    exterior: bool | None = None
    confidence: float = 1.0
    height: float = 2.8
    sources: list[str] = field(default_factory=list)

    @property
    def length(self):
        return math.hypot(self.b[0] - self.a[0], self.b[1] - self.a[1])

    def orientation(self):
        dx, dy = abs(self.b[0] - self.a[0]), abs(self.b[1] - self.a[1])
        if dy < 1e-9:
            return "h"
        if dx < 1e-9:
            return "v"
        return "d"


@dataclass
class Counters:
    merged_duplicates: int = 0
    pruned_fragments: int = 0


def _straighten(runs, cfg):
    limit = math.radians(cfg.straighten_deg)
    for r in runs:
        angle = math.atan2(r.b[1] - r.a[1], r.b[0] - r.a[0]) % math.pi
        if min(angle, math.pi - angle) <= limit:
            y = (r.a[1] + r.b[1]) / 2
            r.a[1] = r.b[1] = y
            if r.a[0] > r.b[0]:
                r.a, r.b = r.b, r.a
        elif abs(angle - math.pi / 2) <= limit:
            x = (r.a[0] + r.b[0]) / 2
            r.a[0] = r.b[0] = x
            if r.a[1] > r.b[1]:
                r.a, r.b = r.b, r.a


def _weighted_median(values, weights):
    pairs = sorted(zip(values, weights))
    half = sum(weights) / 2
    acc = 0
    for v, w in pairs:
        acc += w
        if acc >= half:
            return v
    return pairs[-1][0]


def _majority(values, weights):
    score = {}
    for v, w in zip(values, weights):
        score[v] = score.get(v, 0) + w
    return max(score, key=score.get)


def _run_thickness(parts, weights):
    """Reject a width outlier within one supported run, not across the house.

    Three independent pieces are needed to identify an outlier. Using the
    unweighted centre first prevents one long, bloated piece from dominating
    the subsequent length-weighted estimate.
    """
    values = [p.t for p in parts]
    if len(values) >= 3:
        centre = median(values)
        values = [v if 0.6 * centre <= v <= 1.6 * centre else centre for v in values]
    return _weighted_median(values, weights)


def _merge_collinear(runs, openings, t_med, cfg, counters, gaps):
    """Collinear non-maximum suppression on axis-aligned runs.

    ``gaps`` collects bridged intervals as (horizontal, cross, lo, hi) so the
    opening stage can use the real wall gap as the opening span.
    """
    out = [r for r in runs if r.orientation() == "d"]
    for orient in ("h", "v"):
        axis, cross = (0, 1) if orient == "h" else (1, 0)
        group = sorted(
            (r for r in runs if r.orientation() == orient), key=lambda r: r.a[cross]
        )
        clusters = []
        for r in group:
            for c in clusters:
                if abs(r.a[cross] - c["cross"]) <= median([r.t, c["t"], t_med]) / 2 + 2:
                    c["runs"].append(r)
                    total = sum(x.length for x in c["runs"])
                    c["cross"] = sum(x.a[cross] * x.length for x in c["runs"]) / total
                    c["t"] = median([p.t for p in c["runs"]])
                    break
            else:
                clusters.append({"cross": r.a[cross], "t": r.t, "runs": [r]})
        spans = [
            (o.start.y + o.end.y) / 2 if orient == "h" else (o.start.x + o.end.x) / 2
            for o in openings
        ]
        for c in clusters:
            items = sorted(c["runs"], key=lambda r: r.a[axis])
            merged = []
            for r in items:
                if merged:
                    m = merged[-1]
                    gap = r.a[axis] - m["hi"]
                    t = max(m["t"], r.t)
                    intervals = []
                    if gap > 0:
                        for o, oc in zip(openings, spans):
                            if abs(oc - c["cross"]) > t + 2:
                                continue
                            lo = min(
                                getattr(o.start, "xy"[axis]), getattr(o.end, "xy"[axis])
                            )
                            hi = max(
                                getattr(o.start, "xy"[axis]), getattr(o.end, "xy"[axis])
                            )
                            lo, hi = max(lo, m["hi"]), min(hi, r.a[axis])
                            if hi > lo:
                                intervals.append((lo, hi))
                    covered, right = 0.0, float("-inf")
                    for lo, hi in sorted(intervals):
                        covered += max(0, hi - max(lo, right))
                        right = max(right, hi)
                    if gap <= 0 or (covered >= cfg.opening_gap_cover * gap):
                        if gap <= 0:
                            counters.merged_duplicates += 1
                        elif gap > 1:
                            gaps.append((orient == "h", c["cross"], m["hi"], r.a[axis]))
                        m["hi"] = max(m["hi"], r.b[axis])
                        m["parts"].append(r)
                        continue
                merged.append(
                    {"lo": r.a[axis], "hi": r.b[axis], "t": r.t, "parts": [r]}
                )
            for m in merged:
                parts = m["parts"]
                weights = [max(1, p.length) for p in parts]
                cr = sum(p.a[cross] * w for p, w in zip(parts, weights)) / sum(weights)
                a = [0.0, 0.0]
                b = [0.0, 0.0]
                a[axis], b[axis] = m["lo"], m["hi"]
                a[cross] = b[cross] = cr
                out.append(
                    Run(
                        a=a,
                        b=b,
                        t=_run_thickness(parts, weights),
                        material=_majority([p.material for p in parts], weights),
                        exterior=_majority([p.exterior for p in parts], weights),
                        confidence=min(p.confidence for p in parts),
                        height=max(p.height for p in parts),
                        sources=[s for p in parts for s in p.sources],
                    )
                )
    return out


def _line_intersection(p, d, q, e):
    det = d[0] * -e[1] - d[1] * -e[0]
    if abs(det) < 1e-9:
        return None
    rx, ry = q[0] - p[0], q[1] - p[1]
    t = (rx * -e[1] - ry * -e[0]) / det
    s = (d[0] * ry - d[1] * rx) / det
    return t, s


def _snap_junctions(runs):
    """Move endpoints onto the axis intersection of a nearby non-parallel run."""
    original = [(list(r.a), list(r.b)) for r in runs]
    for i, r in enumerate(runs):
        a0, b0 = original[i]
        d = (b0[0] - a0[0], b0[1] - a0[1])
        length = math.hypot(*d)
        if length < 1e-6:
            continue
        for end, point in (("a", a0), ("b", b0)):
            best = None
            for j, (qa, qb) in enumerate(original):
                if i == j:
                    continue
                e = (qb[0] - qa[0], qb[1] - qa[1])
                other = math.hypot(*e)
                if other < 1e-6:
                    continue
                if abs(d[0] * e[0] + d[1] * e[1]) / (length * other) > 0.35:
                    continue
                hit = _line_intersection(a0, d, qa, e)
                if hit is None:
                    continue
                t, s = hit
                x = (a0[0] + t * d[0], a0[1] + t * d[1])
                dist = math.hypot(x[0] - point[0], x[1] - point[1])
                radius = (r.t + runs[j].t) / 2 + 3
                if dist <= radius and -radius / other <= s <= 1 + radius / other:
                    if best is None or dist < best[0]:
                        best = (dist, x, j, s)
            if best:
                setattr(r, end, [best[1][0], best[1][1]])
                j, s = best[2], best[3]
                # Extend the other run to the corner when the junction is past its end (L).
                q = runs[j]
                if s < 0 or s > 1:
                    near = "a" if s < 0.5 else "b"
                    setattr(q, near, [best[1][0], best[1][1]])
    return [r for r in runs if r.length >= 1]


class _Nodes:
    def __init__(self, tol):
        self.tol = tol
        self.points: list[list[float]] = []

    def get(self, p):
        for i, q in enumerate(self.points):
            if math.hypot(q[0] - p[0], q[1] - p[1]) <= self.tol:
                return i
        self.points.append([p[0], p[1]])
        return len(self.points) - 1


def _build_graph(runs):
    nodes = _Nodes(2.0)
    edges = []
    for r in runs:
        edges.append([nodes.get(r.a), nodes.get(r.b), r])
    # Proper crossings: add a node where two interiors intersect.
    for i in range(len(edges)):
        for j in range(i + 1, len(edges)):
            pa, pb = nodes.points[edges[i][0]], nodes.points[edges[i][1]]
            qa, qb = nodes.points[edges[j][0]], nodes.points[edges[j][1]]
            d = (pb[0] - pa[0], pb[1] - pa[1])
            e = (qb[0] - qa[0], qb[1] - qa[1])
            hit = _line_intersection(pa, d, qa, e)
            if hit is None:
                continue
            t, s = hit
            if 0.02 < t < 0.98 and 0.02 < s < 0.98:
                nodes.get((pa[0] + t * d[0], pa[1] + t * d[1]))
    # Split every edge at nodes lying on its interior (T-junctions and crossings).
    result = []
    for u, v, r in edges:
        p, q = nodes.points[u], nodes.points[v]
        d = (q[0] - p[0], q[1] - p[1])
        l2 = d[0] ** 2 + d[1] ** 2
        if l2 < 1e-9:
            continue
        cuts = []
        for k, n in enumerate(nodes.points):
            if k in (u, v):
                continue
            t = ((n[0] - p[0]) * d[0] + (n[1] - p[1]) * d[1]) / l2
            if not 0 < t < 1:
                continue
            dist = math.hypot(p[0] + t * d[0] - n[0], p[1] + t * d[1] - n[1])
            if dist <= max(2.0, r.t / 2 + 1):
                cuts.append((t, k))
        chain = [u] + [k for _, k in sorted(cuts)] + [v]
        for a, b in zip(chain, chain[1:]):
            if a != b:
                result.append([a, b, r])
    return nodes.points, result


def _degrees(edges):
    deg = {}
    for u, v, _ in edges:
        deg[u] = deg.get(u, 0) + 1
        deg[v] = deg.get(v, 0) + 1
    return deg


def _merge_degree_two(points, edges):
    changed = True
    while changed:
        changed = False
        deg = _degrees(edges)
        for node, count in deg.items():
            if count != 2:
                continue
            pair = [e for e in edges if node in (e[0], e[1])]
            if len(pair) != 2 or pair[0] is pair[1]:
                continue
            (a1, b1, r1), (a2, b2, r2) = pair
            o1 = b1 if a1 == node else a1
            o2 = b2 if a2 == node else a2
            if o1 == o2:
                continue
            p, n, q = points[o1], points[node], points[o2]
            d1 = (n[0] - p[0], n[1] - p[1])
            d2 = (q[0] - n[0], q[1] - n[1])
            l1, l2 = math.hypot(*d1), math.hypot(*d2)
            if l1 < 1e-6 or l2 < 1e-6:
                continue
            if abs(d1[0] * d2[1] - d1[1] * d2[0]) / (l1 * l2) > math.sin(
                math.radians(2)
            ):
                continue
            if d1[0] * d2[0] + d1[1] * d2[1] <= 0:
                continue
            if (
                abs(r1.t - r2.t) > max(2, 0.35 * max(r1.t, r2.t))
                or r1.material != r2.material
            ):
                continue
            keep = r1 if l1 >= l2 else r2
            edges.remove(pair[0])
            edges.remove(pair[1])
            edges.append([o1, o2, keep])
            changed = True
            break
    return edges


def _collinear_sibling(points, edges, edge, reach):
    """True when another run lies on the same axis line within ``reach`` (a pier between openings)."""
    u, v, r = edge
    p, q = points[u], points[v]
    horizontal = abs(q[0] - p[0]) >= abs(q[1] - p[1])
    for u2, v2, r2 in edges:
        if (u2, v2) == (u, v):
            continue
        a, b = points[u2], points[v2]
        if (abs(b[0] - a[0]) >= abs(b[1] - a[1])) != horizontal:
            continue
        ci, cj = (1, 1) if horizontal else (0, 0)
        if abs(a[ci] - p[ci]) > max(r.t, r2.t) / 2 + 2:
            continue
        ax = 0 if horizontal else 1
        lo, hi = sorted((p[ax], q[ax]))
        lo2, hi2 = sorted((a[ax], b[ax]))
        if max(lo, lo2) - min(hi, hi2) <= reach:
            return True
    return False


def _prune(points, edges, t_med, cfg, counters, supported_sources=frozenset()):
    for _ in range(3):
        deg = _degrees(edges)
        keep = []
        for u, v, r in edges:
            # A thick exterior wall must not set the minimum return length
            # for a much thinner interior partition.
            limit = max(2 * min(t_med, r.t), cfg.min_length_px)
            p, q = points[u], points[v]
            length = math.hypot(q[0] - p[0], q[1] - p[1])
            if length >= max(2, 0.5 * r.t) and any(source in supported_sources for source in r.sources):
                # A short pier or return with two observed wall faces is not
                # an unsupported stub. The default dark-plan path has no
                # boundary-supported sources and follows the original rules.
                keep.append([u, v, r])
                continue
            dangling = deg[u] == 1 or deg[v] == 1
            isolated = deg[u] == 1 and deg[v] == 1
            if (dangling and length < limit) or (
                isolated and length < max(2 * limit, 5 * r.t)
            ):
                if length >= 1.5 * r.t and _collinear_sibling(
                    points, edges, (u, v, r), 24 * r.t
                ):
                    keep.append([u, v, r])
                    continue
                counters.pruned_fragments += 1
                continue
            keep.append([u, v, r])
        if len(keep) == len(edges):
            break
        edges = keep
    return edges


def _host_openings(model_nodes, walls, raw, gaps, cfg):
    nodes = {n.id: n for n in model_nodes}
    out = []
    for i, o in enumerate(raw):
        s = (o.start.x, o.start.y)
        e = (o.end.x, o.end.y)
        mid = ((s[0] + e[0]) / 2, (s[1] + e[1]) / 2)
        candidates = []
        for w in walls:
            a, b = nodes[w.a], nodes[w.b]
            d = (b.x - a.x, b.y - a.y)
            length = math.hypot(*d)
            if length < 1:
                continue
            u = (d[0] / length, d[1] / length)
            od = (e[0] - s[0], e[1] - s[1])
            ol = math.hypot(*od)
            if ol > 1 and abs(u[0] * od[1] - u[1] * od[0]) / ol > 0.3:
                continue
            perp = abs((mid[0] - a.x) * u[1] - (mid[1] - a.y) * u[0])
            if perp > max(w.thickness_px, 4) + 2:
                continue
            ts = [(p[0] - a.x) * u[0] + (p[1] - a.y) * u[1] for p in (s, e)]
            lo, hi = max(0, min(ts)), min(length, max(ts))
            if hi - lo < 1:
                continue
            candidates.append((perp, w, a, u, length, lo, hi))
        status = "proposed"
        confidence = (
            o.confidence if o.confidence is not None else (0.5 if o.uncertain else 0.9)
        )
        if not candidates:
            out.append(
                Opening(
                    id=f"o{i}",
                    kind=o.kind,
                    span=(Pt(x=s[0], y=s[1]), Pt(x=e[0], y=e[1])),
                    height_m=o.height_m,
                    sill_m=o.sill_m if o.kind == "window" else 0,
                    confidence=confidence,
                    status="proposed",
                )
            )
            continue
        candidates.sort(key=lambda c: c[0])
        ambiguous = len(candidates) > 1 and candidates[1][0] - candidates[0][0] < 2
        _, w, a, u, length, lo, hi = candidates[0]
        horizontal = abs(u[0]) >= abs(u[1])
        cross = a.y if horizontal else a.x
        for gh, gc, glo, ghi in gaps:
            if gh != horizontal or abs(gc - cross) > w.thickness_px + 2:
                continue
            base = a.x if horizontal else a.y
            sign = u[0] if horizontal else u[1]
            g = sorted(((glo - base) * sign, (ghi - base) * sign))
            overlap = min(hi, g[1]) - max(lo, g[0])
            if overlap > 0.5 * min(hi - lo, g[1] - g[0]):
                lo, hi = max(0, g[0]), min(length, g[1])
                break
        if (
            confidence >= cfg.auto_confirm_by_kind.get(o.kind, cfg.auto_confirm)
            and not ambiguous
            and o.kind != "garage"
        ):
            status = "confirmed"
        hinge, swing = "start", None
        if o.kind == "door":
            ts_s = (s[0] - a.x) * u[0] + (s[1] - a.y) * u[1]
            ts_e = (e[0] - a.x) * u[0] + (e[1] - a.y) * u[1]
            hinge = "start" if ts_s <= ts_e else "end"
            if o.leaf is not None:
                swing = "left" if o.leaf.x * -u[1] + o.leaf.y * u[0] > 0 else "right"
        out.append(
            Opening(
                id=f"o{i}",
                kind=o.kind,
                host_wall_id=w.id,
                offset_px=lo,
                width_px=hi - lo,
                span=(Pt(x=s[0], y=s[1]), Pt(x=e[0], y=e[1])),
                height_m=min(
                    o.height_m, w.height_m - (o.sill_m if o.kind == "window" else 0)
                ),
                sill_m=o.sill_m if o.kind == "window" else 0,
                swing=swing,
                hinge=hinge,
                confidence=confidence,
                status=status,
            )
        )
    return out


def reconstruct(doc: Document, plan_id: str, cfg: ReconstructConfig | None = None):
    if cfg is None:
        cfg = configured_config()
    counters = Counters()
    runs = [
        Run(
            a=[o.start.x, o.start.y],
            b=[o.end.x, o.end.y],
            t=o.thickness_px,
            material=o.material,
            exterior=o.exterior,
            confidence=0.5 if o.uncertain else 1.0,
            height=o.height_m,
            sources=[o.id],
        )
        for o in doc.objects
        if o.kind == "wall"
    ]
    raw_openings = [o for o in doc.objects if o.kind != "wall"]
    t_med = median([r.t for r in runs]) if runs else 8.0
    _straighten(runs, cfg)
    gaps: list = []
    runs = _merge_collinear(runs, raw_openings, t_med, cfg, counters, gaps)
    runs = _snap_junctions(runs)
    points, edges = _build_graph(runs)
    edges = _merge_degree_two(points, edges)
    supported_sources = {o.id for o in doc.objects if o.kind == "wall" and o.boundary_supported}
    edges = _prune(points, edges, t_med, cfg, counters, supported_sources)
    used = sorted({k for u, v, _ in edges for k in (u, v)})
    index = {k: i for i, k in enumerate(used)}
    w, h = doc.width, doc.height
    nodes = [
        Node(
            id=f"n{index[k]}",
            x=min(w, max(0, points[k][0])),
            y=min(h, max(0, points[k][1])),
        )
        for k in used
    ]
    walls = [
        Wall(
            id=f"w{i}",
            a=f"n{index[u]}",
            b=f"n{index[v]}",
            thickness_px=max(1, r.t),
            height_m=r.height,
            material=r.material,
            exterior=r.exterior,
            confidence=r.confidence,
        )
        for i, (u, v, r) in enumerate(edges)
    ]
    openings = _host_openings(nodes, walls, raw_openings, gaps, cfg)
    model = PlanModel(
        id=plan_id,
        image_transform=ImageTransform(width=w, height=h),
        scale=Scale(),
        nodes=nodes,
        walls=walls,
        openings=openings,
        notes=list(doc.warnings),
        envelope=[Pt(x=p.x, y=p.y) for p in doc.envelope] if doc.envelope else None,
    )
    from .plan_derive import derive

    return derive(
        model,
        counters={
            "merged_duplicates": counters.merged_duplicates,
            "pruned_fragments": counters.pruned_fragments,
            "passages": [(p.x, p.y) for p in doc.passages],
        },
    )


def extend_dangling(objects, ink, factor: float = 4.0, cover: float = 0.8):
    """Extend dangling axis-aligned wall ends along drawn evidence.

    An end that touches no other wall is extended along its axis, at most
    ``factor * thickness``, to the nearest perpendicular wall - but only when at
    least ``cover`` of the extension path lies on ink (strip or outline). Returns
    the number of ends extended. ``objects`` are mutated in place.
    """
    import numpy as np

    h, w = ink.shape
    walls = [o for o in objects if o.kind == "wall"]
    horizontal = {}
    for o in walls:
        dx, dy = abs(o.end.x - o.start.x), abs(o.end.y - o.start.y)
        horizontal[o.id] = (
            True if dy <= 0.2 * dx + 1 else False if dx <= 0.2 * dy + 1 else None
        )

    def body_distance(px, py, skip):
        best = None
        for q in walls:
            if q.id == skip:
                continue
            ax, ay, bx, by = q.start.x, q.start.y, q.end.x, q.end.y
            l2 = (bx - ax) ** 2 + (by - ay) ** 2 or 1
            t = max(0, min(1, ((px - ax) * (bx - ax) + (py - ay) * (by - ay)) / l2))
            d = math.hypot(px - (ax + t * (bx - ax)), py - (ay + t * (by - ay)))
            best = d if best is None else min(best, d)
        return best if best is not None else 1e9

    count = 0
    for o in walls:
        axis = horizontal[o.id]
        if axis is None:
            continue
        for end in ("start", "end"):
            p, other = getattr(o, end), getattr(o, "end" if end == "start" else "start")
            if body_distance(p.x, p.y, o.id) <= o.thickness_px / 2 + 3:
                continue
            direction = np.array([p.x - other.x, p.y - other.y], float)
            direction /= np.linalg.norm(direction) or 1
            reach = factor * o.thickness_px
            target = None
            for q in walls:
                if q.id == o.id or horizontal[q.id] is None or horizontal[q.id] == axis:
                    continue
                if axis:  # extend in x toward a vertical wall at x = q.start.x
                    qx = (q.start.x + q.end.x) / 2
                    lo, hi = sorted((q.start.y, q.end.y))
                    dist = (qx - p.x) * direction[0]
                    ok = lo - q.thickness_px / 2 <= p.y <= hi + q.thickness_px / 2
                    stop = qx - direction[0] * q.thickness_px / 2
                else:
                    qy = (q.start.y + q.end.y) / 2
                    lo, hi = sorted((q.start.x, q.end.x))
                    dist = (qy - p.y) * direction[1]
                    ok = lo - q.thickness_px / 2 <= p.x <= hi + q.thickness_px / 2
                    stop = qy - direction[1] * q.thickness_px / 2
                if (
                    ok
                    and 0 < dist <= reach + q.thickness_px / 2
                    and (target is None or dist < target[0])
                ):
                    target = (dist, stop)
            if not target:
                continue
            nx, ny = (target[1], p.y) if axis else (p.x, target[1])
            # A wall face can project beyond a cropped photograph. Sampling
            # with clipped indices must not authorize out-of-image geometry.
            if not (0 <= nx < w and 0 <= ny < h):
                continue
            if math.hypot(nx - other.x, ny - other.y) < 2:
                continue
            n = max(2, int(math.hypot(nx - p.x, ny - p.y)))
            xs = np.rint(np.linspace(p.x, nx, n)).astype(int).clip(0, w - 1)
            ys = np.rint(np.linspace(p.y, ny, n)).astype(int).clip(0, h - 1)
            reach_px = max(1, int(o.thickness_px / 2))
            near = np.zeros(n, bool)
            for dx in range(-reach_px, reach_px + 1):
                near |= ink[
                    (ys + (dx if axis else 0)).clip(0, h - 1),
                    (xs + (0 if axis else dx)).clip(0, w - 1),
                ]
            if near.mean() >= cover:
                setattr(o, end, type(p)(x=float(nx), y=float(ny)))
                count += 1
    return count
