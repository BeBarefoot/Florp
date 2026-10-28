"""Strict non-mutating checks for graph edits and persistence."""
from __future__ import annotations

from collections import Counter
from math import hypot
from shapely.geometry import Polygon
from .plan_graph import CanonicalPlan


def validate_plan(plan: CanonicalPlan) -> list[str]:
    issues: list[str] = []
    nodes = {n.id: n for n in plan.nodes}
    walls = {w.id: w for w in plan.walls}
    for category, ids in [('node', [n.id for n in plan.nodes]),
                          ('wall', [w.id for w in plan.walls]),
                          ('opening', [o.id for o in plan.openings]),
                          ('room', [r.id for r in plan.rooms])]:
        issues += [f'Duplicate {category} ID: {k}' for k, n in Counter(ids).items() if n > 1]
    for n in plan.nodes:
        if not (0 <= n.point.x <= plan.width_px and 0 <= n.point.y <= plan.height_px):
            issues.append(f'Node {n.id} outside source image')
    for w in plan.walls:
        if w.start_node_id not in nodes or w.end_node_id not in nodes:
            issues.append(f'Wall {w.id} references missing junction')
        elif w.start_node_id == w.end_node_id or hypot(
            nodes[w.start_node_id].point.x - nodes[w.end_node_id].point.x,
            nodes[w.start_node_id].point.y - nodes[w.end_node_id].point.y,
        ) < .001:
            # Edges are subdivisions of source walls. A real intersection can
            # leave a short but nonzero fragment; discarding it loses evidence.
            issues.append(f'Wall {w.id} has zero-length geometry')
    by_host: dict[str, list] = {}
    for o in plan.openings:
        if o.wall_id not in walls:
            issues.append(f'Opening {o.id} has missing host wall')
            continue
        w = walls[o.wall_id]
        if o.kind == 'door' and o.sill_m > 0.001:
            issues.append(f'Door {o.id} must start at floor')
        if o.sill_m + o.height_m > w.height_m + 0.001:
            issues.append(f'Opening {o.id} exceeds host height')
        if plan.px_per_meter:
            a, b = nodes.get(w.start_node_id), nodes.get(w.end_node_id)
            if a and b:
                length = hypot(a.point.x-b.point.x, a.point.y-b.point.y) / plan.px_per_meter
                if o.offset_m + o.width_m > length + 0.001:
                    issues.append(f'Opening {o.id} exceeds host length')
        else:
            issues.append(f'Opening {o.id} has uncalibrated physical length')
        by_host.setdefault(o.wall_id, []).append(o)
    for host, openings in by_host.items():
        ordered = sorted(openings, key=lambda o: o.offset_m)
        for left, right in zip(ordered, ordered[1:]):
            if left.offset_m + left.width_m > right.offset_m + 0.001:
                issues.append(f'Overlapping openings {left.id}, {right.id} on {host}')
    for room in plan.rooms:
        # Boundary edges must represent an actual, continuous closed loop;
        # a polygon predicted from pixels alone cannot pass this check.
        first = previous = None
        touched = set()
        polygon_points = []
        for ref in room.boundary:
            w = walls.get(ref.wall_id)
            if not w:
                issues.append(f'Room {room.id} references missing wall {ref.wall_id}')
                break
            a, b = (w.start_node_id, w.end_node_id) if ref.forward else (w.end_node_id, w.start_node_id)
            if first is None:
                first = a
            elif previous != a:
                issues.append(f'Room {room.id} has disconnected boundary')
                break
            if a not in nodes:
                issues.append(f'Room {room.id} references missing junction')
                break
            polygon_points.append((nodes[a].point.x,nodes[a].point.y))
            previous = b
            touched.add(ref.wall_id)
        else:
            if previous != first or len(touched) < 3:
                issues.append(f'Room {room.id} is not a closed wall cycle')
            elif len(polygon_points) >= 3:
                polygon = Polygon(polygon_points)
                if not polygon.is_valid or polygon.area < 4:
                    issues.append(f'Room {room.id} has invalid or self-intersecting floor geometry')
    return issues


def require_valid(plan: CanonicalPlan) -> CanonicalPlan:
    issues = validate_plan(plan)
    if issues:
        raise ValueError('; '.join(issues))
    return plan
