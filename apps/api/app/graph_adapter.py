"""Loss-aware adapter from independent legacy wall segments to CanonicalPlan.

Only exact/<=1px evidenced junctions are shared. Never bridges unsupported
gaps, invents metric scale, or silently drops incompatible opening evidence.
"""
from __future__ import annotations

from hashlib import sha1
from math import hypot
from shapely.geometry import LineString
from shapely.ops import polygonize
from .geometry import Geometry, Wall, Opening, Room, Pt
from .structural_graph import build_structural_graph
from .plan_graph import CanonicalPlan, PlanNode, PlanWall, PlanRoom, BoundaryEdge, PlanOpening
from .graph_validation import require_valid


def derive_faces(plan: CanonicalPlan) -> list[PlanRoom]:
    """Closed source-wall cycles only; open contours never become rooms."""
    nodes = {n.id: n.point for n in plan.nodes}
    edge_lookup = {}
    lines = []
    for w in plan.walls:
        if w.start_node_id not in nodes or w.end_node_id not in nodes:
            continue
        a, b = nodes[w.start_node_id], nodes[w.end_node_id]
        key = frozenset((w.start_node_id, w.end_node_id))
        if key in edge_lookup:  # ambiguous duplicate geometry: do not declare a face
            return []
        edge_lookup[key] = w
        lines.append(LineString([(a.x, a.y), (b.x, b.y)]))
    # Map polygonized coordinates back to existing shared graph nodes,
    # never to newly inferred points.
    coord_to_id = {(round(n.point.x, 3), round(n.point.y, 3)): n.id for n in plan.nodes}
    rooms = []
    for polygon in polygonize(lines):
        if not polygon.is_valid or polygon.area < 4 or polygon.interiors:
            continue
        coords = list(polygon.exterior.coords)
        keys = [(round(x, 3), round(y, 3)) for x, y in coords]
        if any(k not in coord_to_id for k in keys):
            continue
        refs = []
        for a, b in zip(keys, keys[1:]):
            start, end = coord_to_id[a], coord_to_id[b]
            wall = edge_lookup.get(frozenset((start, end)))
            if wall is None:
                refs = []
                break
            refs.append(BoundaryEdge(wall_id=wall.id, forward=wall.start_node_id == start))
        if len(refs) < 3:
            continue
        digest = sha1('|'.join(sorted(r.wall_id for r in refs)).encode()).hexdigest()[:12]
        rooms.append(PlanRoom(id='face-'+digest, boundary=refs))
    return sorted(rooms, key=lambda r: r.id)


def from_geometry(geometry: Geometry) -> CanonicalPlan:
    graph = build_structural_graph(geometry)
    nodes = [PlanNode(id=n.id, point=n.position.model_copy(deep=True))
             for n in graph.nodes]
    original = {w.id: w for w in geometry.walls}
    per_source = {}
    for e in graph.edges:
        per_source.setdefault(e.source_wall_id, []).append(e)
    walls = []
    for e in graph.edges:
        source = original[e.source_wall_id]
        sole = len(per_source[e.source_wall_id]) == 1
        walls.append(PlanWall(
            id=source.id if sole else e.id,
            start_node_id=e.start_node_id, end_node_id=e.end_node_id,
            source_wall_id=source.id,
            thickness_m=source.thickness_m, height_m=source.height_m,
            inferred=source.inferred, evidence_ids=[source.id]))
    plan = CanonicalPlan(width_px=geometry.width_px, height_px=geometry.height_px,
                         px_per_meter=geometry.px_per_meter, scale_source=geometry.scale_source,
                         nodes=nodes, walls=walls, legacy_rooms=[r.model_copy(deep=True) for r in geometry.rooms],
                         warnings=list(geometry.warnings),
                         provenance={'adapter':'legacy-geometry-v1', 'source':'stored wall axes'})
    graph_nodes = {n.id: n.position for n in graph.nodes}
    for opening in geometry.openings:
        source = original.get(opening.wall_id)
        if source is None or not geometry.px_per_meter:
            plan.pending_openings.append(opening.model_copy(deep=True))
            continue
        length_px = hypot(source.start.x-source.end.x, source.start.y-source.end.y)
        span_start = opening.offset_m * geometry.px_per_meter
        span_end = (opening.offset_m + opening.width_m) * geometry.px_per_meter
        # All graph edges preserve the parent source-axis orientation.
        matches = []
        for e in per_source.get(source.id, []):
            a = graph_nodes[e.start_node_id]
            b = graph_nodes[e.end_node_id]
            start_px = hypot(a.x-source.start.x, a.y-source.start.y)
            end_px = hypot(b.x-source.start.x, b.y-source.start.y)
            lo, hi = sorted((start_px, end_px))
            if span_start >= lo-0.001 and span_end <= hi+0.001:
                matches.append((e, lo))
        if len(matches) != 1 or span_end > length_px + 0.001:
            plan.pending_openings.append(opening.model_copy(deep=True))
            continue
        e, lo = matches[0]
        wall_id = source.id if len(per_source[source.id]) == 1 else e.id
        plan.openings.append(PlanOpening(
            id=opening.id, wall_id=wall_id, kind=opening.kind,
            offset_m=round(opening.offset_m-lo/geometry.px_per_meter, 6),
            width_m=opening.width_m, height_m=opening.height_m,
            sill_m=opening.sill_m, source_detection_id=opening.source_detection_id,
            reviewed=opening.reviewed, inferred=opening.inferred))
    if plan.pending_openings:
        plan.warnings.append(f'{len(plan.pending_openings)} opening anchors awaiting explicit reconciliation; no openings discarded')
    plan.rooms = derive_faces(plan)
    return plan


def to_geometry(plan: CanonicalPlan, *, include_derived_rooms: bool = False) -> Geometry:
    """Explicit export. Refuse ambiguous source opening anchors rather than losing them."""
    require_valid(plan)
    if plan.pending_openings:
        raise ValueError('Cannot export: pending legacy opening anchors need reconciliation')
    nodes = {n.id: n.point for n in plan.nodes}
    walls = [Wall(id=w.id, start=nodes[w.start_node_id], end=nodes[w.end_node_id],
                  thickness_m=w.thickness_m, height_m=w.height_m, inferred=w.inferred)
             for w in plan.walls]
    openings = [Opening(**o.model_dump()) for o in plan.openings]
    rooms = [r.model_copy(deep=True) for r in plan.legacy_rooms]
    if include_derived_rooms and not rooms:
        for face in plan.rooms:
            boundary = []
            by_wall = {w.id: w for w in plan.walls}
            for ref in face.boundary:
                w = by_wall[ref.wall_id]
                boundary.append(nodes[w.start_node_id if ref.forward else w.end_node_id])
            rooms.append(Room(id=face.id, label=face.label, points=boundary))
    return Geometry(width_px=plan.width_px, height_px=plan.height_px,
                    px_per_meter=plan.px_per_meter, scale_source=plan.scale_source,
                    structure_reviewed=False, walls=walls, openings=openings,
                    rooms=rooms, warnings=list(plan.warnings))
