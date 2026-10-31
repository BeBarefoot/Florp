"""Derived plan data: rooms from closed wall cycles and clustered review findings.

The face/inset algorithm is mirrored in apps/web/lib/plan/derive.ts so room
areas update live in the editor; keep both implementations in step.
"""

from __future__ import annotations
import hashlib
import math
from statistics import median
from .plan_model import PlanModel, Room, Finding, Pt

MIN_ROOM_PX2 = 400.0
FINDING_CAP = 50


def _signed_area(points):
    return sum(
        points[i][0] * points[(i + 1) % len(points)][1]
        - points[(i + 1) % len(points)][0] * points[i][1]
        for i in range(len(points))
    ) / 2


def faces(model: PlanModel):
    """Bounded faces of the wall graph as lists of (node_id, wall_id) steps."""
    pos = {n.id: (n.x, n.y) for n in model.nodes}
    edges = {}
    for w in model.walls:
        if w.a != w.b:
            edges[w.id] = (w.a, w.b)
    # Dangling chains cannot bound a room; peel them off first.
    while True:
        deg = {}
        for a, b in edges.values():
            deg[a] = deg.get(a, 0) + 1
            deg[b] = deg.get(b, 0) + 1
        loose = [k for k, (a, b) in edges.items() if deg[a] == 1 or deg[b] == 1]
        if not loose:
            break
        for k in loose:
            del edges[k]
    out = {}
    for wid, (a, b) in edges.items():
        out.setdefault(a, []).append((b, wid))
        out.setdefault(b, []).append((a, wid))
    for n, items in out.items():
        x, y = pos[n]
        items.sort(key=lambda item: math.atan2(pos[item[0]][1] - y, pos[item[0]][0] - x))
    seen = set()
    result = []
    for start, items in out.items():
        for nxt, wid in items:
            if (start, nxt, wid) in seen:
                continue
            cycle = []
            u, v, w = start, nxt, wid
            while (u, v, w) not in seen and len(cycle) <= len(edges) * 2:
                seen.add((u, v, w))
                cycle.append((u, w))
                around = out[v]
                i = next(k for k, item in enumerate(around) if item == (u, w))
                u, (v, w) = v, around[(i - 1) % len(around)]
            points = [pos[n] for n, _ in cycle]
            if len(points) >= 3 and _signed_area(points) > 0:
                result.append(cycle)
    return result


def inset(points, thickness):
    """Offset each edge inward by half its wall thickness (polygon must be CCW-positive)."""
    n = len(points)
    lines = []
    for i in range(n):
        p, q = points[i], points[(i + 1) % n]
        dx, dy = q[0] - p[0], q[1] - p[1]
        length = math.hypot(dx, dy) or 1
        nx, ny = -dy / length, dx / length
        off = thickness[i] / 2
        lines.append(((p[0] + nx * off, p[1] + ny * off), (dx / length, dy / length), (nx, ny), off))
    result = []
    for i in range(n):
        (p1, d1, _, _), (p2, d2, n2, off2) = lines[i - 1], lines[i]
        det = d1[0] * d2[1] - d1[1] * d2[0]
        if abs(det) < 1e-6:
            v = points[i]
            result.append((v[0] + n2[0] * off2, v[1] + n2[1] * off2))
            continue
        rx, ry = p2[0] - p1[0], p2[1] - p1[1]
        t = (rx * d2[1] - ry * d2[0]) / det
        result.append((p1[0] + t * d1[0], p1[1] + t * d1[1]))
    return result


def _inside(pt, poly):
    x, y = pt
    hit = False
    for i in range(len(poly)):
        (x1, y1), (x2, y2) = poly[i], poly[(i + 1) % len(poly)]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            hit = not hit
    return hit


def rooms(model: PlanModel) -> list[Room]:
    pos = {n.id: (n.x, n.y) for n in model.nodes}
    walls = {w.id: w for w in model.walls}
    t_med = median([w.thickness_px for w in model.walls]) if model.walls else 8
    previous = [
        (r.label, _centroid([(p.x, p.y) for p in r.polygon])) for r in model.rooms if r.label
    ]
    result = []
    for cycle in faces(model):
        outline = [pos[n] for n, _ in cycle]
        inner = inset(outline, [walls[w].thickness_px for _, w in cycle])
        area = _signed_area(inner)
        if area < max(MIN_ROOM_PX2, 9 * t_med**2):
            continue
        ids = sorted({w for _, w in cycle})
        label = next((lab for lab, c in previous if _inside(c, inner)), None)
        result.append(
            Room(
                id="r-" + hashlib.sha1(".".join(ids).encode()).hexdigest()[:10],
                wall_ids=ids,
                polygon=[Pt(x=x, y=y) for x, y in inner],
                area_px2=area,
                label=label,
            )
        )
    result.sort(key=lambda r: (min(p.y for p in r.polygon), min(p.x for p in r.polygon)))
    return result


def _centroid(points):
    return (
        sum(p[0] for p in points) / len(points),
        sum(p[1] for p in points) / len(points),
    )


def _cluster(category, items, radius, message, severity="warn"):
    """Spatial NMS from fixed seeds (no chaining), capped per category."""
    groups = []
    for target, x, y in items:
        group = next(
            (g for g in groups if math.hypot(g["x"] - x, g["y"] - y) <= radius), None
        )
        if group:
            group["targets"].append(target)
        else:
            groups.append({"x": x, "y": y, "targets": [target]})
    groups.sort(key=lambda g: -len(g["targets"]))
    return [
        Finding(
            id=f"{category}:{g['targets'][0]}",
            category=category,
            severity=severity,
            target_ids=g["targets"],
            anchor=Pt(x=g["x"], y=g["y"]),
            count=len(g["targets"]),
            message=message(len(g["targets"])),
        )
        for g in groups[:FINDING_CAP]
    ]


def findings(model: PlanModel, counters: dict | None = None) -> list[Finding]:
    pos = {n.id: (n.x, n.y) for n in model.nodes}
    walls = {w.id: w for w in model.walls}
    t_med = median([w.thickness_px for w in model.walls]) if model.walls else 8
    radius = max(6 * t_med, 40)
    out = []
    for o in model.openings:
        if o.status != "proposed":
            continue
        if o.host_wall_id and o.host_wall_id in walls:
            w = walls[o.host_wall_id]
            a, b = pos[w.a], pos[w.b]
            length = math.hypot(b[0] - a[0], b[1] - a[1]) or 1
            t = (o.offset_px + o.width_px / 2) / length
            anchor = (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)
        else:
            s, e = o.span
            anchor = ((s.x + e.x) / 2, (s.y + e.y) / 2)
        out.append(
            Finding(
                id=f"opening_needs_approval:{o.id}",
                category="opening_needs_approval",
                target_ids=[o.id],
                anchor=Pt(x=anchor[0], y=anchor[1]),
                message=f"Confirm this {o.kind}"
                + ("" if o.host_wall_id else " and attach it to a wall"),
            )
        )
    deg = {}
    for w in model.walls:
        deg[w.a] = deg.get(w.a, 0) + 1
        deg[w.b] = deg.get(w.b, 0) + 1
    out += _cluster(
        "open_wall_end",
        [(n, *pos[n]) for n, d in deg.items() if d == 1],
        radius,
        lambda c: f"{c} wall end{'s' if c > 1 else ''} not connected to another wall",
    )
    out += _cluster(
        "low_confidence_wall",
        [
            (w.id, (pos[w.a][0] + pos[w.b][0]) / 2, (pos[w.a][1] + pos[w.b][1]) / 2)
            for w in model.walls
            if w.confidence < 0.6
        ],
        radius,
        lambda c: f"{c} wall{'s' if c > 1 else ''} detected without color evidence",
    )
    if len(model.walls) >= 3 and not model.rooms:
        w, h = model.image_transform.width, model.image_transform.height
        out.append(
            Finding(
                id="unclosed_region:plan",
                category="unclosed_region",
                anchor=Pt(x=w / 2, y=h / 2),
                message="No closed room was found. Connect open wall ends to close rooms.",
            )
        )
    if counters is not None:
        w, h = model.image_transform.width, model.image_transform.height
        out += _cluster(
            "open_passage",
            [(f"passage{i}", x, y) for i, (x, y) in enumerate(counters.get("passages", []))],
            radius,
            lambda c: f"{c} open passage{'s' if c > 1 else ''} kept as a wall gap (no door symbol)",
            severity="info",
        )
        for key, text in (
            ("pruned_fragments", "short disconnected fragments removed"),
            ("merged_duplicates", "overlapping wall fragments merged"),
        ):
            if counters.get(key):
                out.append(
                    Finding(
                        id=f"{key}:plan",
                        category=key,
                        severity="info",
                        anchor=Pt(x=w / 2, y=h / 2),
                        count=counters[key],
                        message=f"{counters[key]} {text}",
                    )
                )
    else:
        out += [
            f for f in model.findings if f.category in ("pruned_fragments", "merged_duplicates", "open_passage")
        ]
    dismissed = set(model.dismissed_findings)
    return [
        f for f in out if f.category == "opening_needs_approval" or f.id not in dismissed
    ]


def derive(model: PlanModel, counters: dict | None = None) -> PlanModel:
    model = model.model_copy(deep=True)
    model.rooms = rooms(model)
    model.findings = findings(model, counters)
    return PlanModel.model_validate(model.dump())
