"""Score a predicted PlanModel against a user-corrected gold PlanModel (pixel space)."""

from __future__ import annotations
import math
from statistics import median
from shapely.geometry import LineString, Polygon
from shapely.ops import unary_union
from .plan_model import PlanModel


def _wall_lines(m: PlanModel):
    nodes = {n.id: n for n in m.nodes}
    return [
        (w, LineString([(nodes[w.a].x, nodes[w.a].y), (nodes[w.b].x, nodes[w.b].y)]))
        for w in m.walls
    ]


def _coverage(lines, other, tol_fn):
    """Fraction of the length of ``lines`` lying within tolerance of ``other``."""
    total = covered = 0.0
    for w, line in lines:
        total += line.length
        if other.is_empty:
            continue
        covered += line.intersection(other.buffer(tol_fn(w))).length
    return covered / total if total else 1.0


def _opening_geom(m: PlanModel, o):
    nodes = {n.id: n for n in m.nodes}
    walls = {w.id: w for w in m.walls}
    w = walls.get(o.host_wall_id) if o.host_wall_id else None
    if not w:
        return None
    a, b = nodes[w.a], nodes[w.b]
    length = math.hypot(b.x - a.x, b.y - a.y) or 1
    ux, uy = (b.x - a.x) / length, (b.y - a.y) / length
    lo, hi = o.offset_px, o.offset_px + o.width_px
    p = (a.x + ux * lo, a.y + uy * lo)
    q = (a.x + ux * hi, a.y + uy * hi)
    return w, p, q


def _interval(p, q, horizontal):
    return sorted((p[0], q[0])) if horizontal else sorted((p[1], q[1]))


def _match_openings(pred, gold, kinds):
    gp = [(o, _opening_geom(gold, o)) for o in gold.openings if o.status != "rejected"]
    pp = [(o, _opening_geom(pred, o)) for o in pred.openings if o.status != "rejected"]
    out = {}
    for kind in kinds:
        g = [(o, geo) for o, geo in gp if o.kind == kind and geo]
        p = [(o, geo) for o, geo in pp if o.kind == kind]
        used, pairs = set(), []
        for po, pg in p:
            if pg is None:
                continue  # still counted as a false positive in the denominator
            _, a, b = pg
            horizontal = abs(b[0] - a[0]) >= abs(b[1] - a[1])
            best = None
            for i, (go, gg) in enumerate(g):
                if i in used:
                    continue
                gw, c, d = gg
                if horizontal != (abs(d[0] - c[0]) >= abs(d[1] - c[1])):
                    continue
                t = max(gw.thickness_px, pg[0].thickness_px, 6)
                cross = abs(
                    ((a[1] + b[1]) - (c[1] + d[1])) / 2
                    if horizontal
                    else ((a[0] + b[0]) - (c[0] + d[0])) / 2
                )
                if cross > t:
                    continue
                i1, i2 = _interval(a, b, horizontal), _interval(c, d, horizontal)
                inter = max(0, min(i1[1], i2[1]) - max(i1[0], i2[0]))
                union = max(i1[1], i2[1]) - min(i1[0], i2[0])
                iou = inter / union if union else 0
                if iou >= 0.5 and (best is None or iou > best[0]):
                    best = (iou, i)
            if best:
                used.add(best[1])
                pairs.append((po, g[best[1]][0]))
        tp = len(pairs)
        precision = tp / len(p) if p else (1.0 if not g else 0.0)
        recall = tp / len(g) if g else 1.0
        f1 = (
            2 * precision * recall / (precision + recall) if precision + recall else 0.0
        )
        out[kind] = {
            "f1": f1,
            "precision": precision,
            "recall": recall,
            "matched": pairs,
            "gold": len(g),
            "predicted": len(p),
        }
    return out


def _envelope(m: PlanModel):
    shapes = [line.buffer(w.thickness_px / 2) for w, line in _wall_lines(m)]
    if not shapes:
        return Polygon()
    t = max(w.thickness_px for w in m.walls)
    merged = unary_union(shapes).buffer(8 * t).buffer(-8 * t)
    parts = list(merged.geoms) if hasattr(merged, "geoms") else [merged]
    return unary_union([Polygon(p.exterior) for p in parts if p.geom_type == "Polygon"])


def score(pred: PlanModel, gold: PlanModel) -> dict:
    pl, gl = _wall_lines(pred), _wall_lines(gold)
    gold_union = unary_union([l for _, l in gl]) if gl else Polygon()
    pred_union = unary_union([l for _, l in pl]) if pl else Polygon()
    # A bloated prediction must not widen its own scoring tolerance.
    reference_width = median([w.thickness_px for w, _ in gl]) if gl else 6
    precision = _coverage(pl, gold_union, lambda _: max(reference_width, 6))
    recall = _coverage(gl, pred_union, lambda w: max(w.thickness_px, 6))
    env = _envelope(gold)
    outside = sum(l.difference(env).length for _, l in pl) if not env.is_empty else 0.0
    openings = _match_openings(pred, gold, ("door", "window", "garage"))
    swing_total = swing_ok = 0
    for r in openings["door"]["matched"]:
        po, go = r
        if go.swing is not None:
            swing_total += 1
            swing_ok += int(po.swing == go.swing)
    gm = gold.scale.meters_per_pixel or 1.0
    area = lambda m: sum(r.area_px2 for r in m.rooms) * gm * gm
    ga, pa = area(gold), area(pred)
    return {
        "wall_precision": precision,
        "wall_recall": recall,
        "false_wall_px_outside_envelope": outside,
        "openings": {
            k: {kk: vv for kk, vv in v.items() if kk != "matched"}
            for k, v in openings.items()
        },
        "door_swing_accuracy": swing_ok / swing_total if swing_total else None,
        "rooms": {
            "gold": len(gold.rooms),
            "predicted": len(pred.rooms),
            "area_error": abs(pa - ga) / ga if ga else None,
        },
    }


def opening_observations(pred, gold):
    """Confidence/correctness samples, including unhosted false positives."""
    result = _match_openings(pred, gold, ("door", "window"))
    observations = {}
    for kind, matched in result.items():
        correct = {p.id for p, _ in matched["matched"]}
        observations[kind] = [
            (o.confidence, o.id in correct)
            for o in pred.openings
            if o.kind == kind and o.status != "rejected"
        ]
    return observations


READINESS_MINIMUMS = {
    "wall_precision": 0.9,
    "wall_recall": 0.9,
    "door_f1": 0.8,
    "window_f1": 0.8,
    "garage_f1": 0.8,
}


def minimum_thresholds(existing):
    if set(existing) - set(READINESS_MINIMUMS) or any(
        not math.isfinite(v) or not 0 <= v <= 1 for v in existing.values()
    ):
        raise ValueError("Invalid gold regression thresholds")
    return {k: max(v, existing.get(k, v)) for k, v in READINESS_MINIMUMS.items()}


def flat_metrics(result):
    return {
        "wall_precision": result["wall_precision"],
        "wall_recall": result["wall_recall"],
        **{
            kind + "_f1": result["openings"][kind]["f1"]
            for kind in ("door", "window", "garage")
        },
    }
