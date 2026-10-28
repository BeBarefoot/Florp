"""Transactional edit operations on the canonical graph.

Each call works on a deep copy, validates the complete result, and only then
returns it. The caller can persist that snapshot as an immutable revision.
"""
from __future__ import annotations

from math import hypot
from uuid import uuid4
from typing import Literal
from pydantic import BaseModel
from .geometry import Pt
from .plan_graph import CanonicalPlan, PlanWall, PlanNode, PlanOpening, BoundaryEdge
from .graph_validation import require_valid
from .graph_adapter import derive_faces


class GraphOperation(BaseModel):
    kind: Literal['move_junction', 'split_wall', 'remove_wall', 'add_wall', 'attach_opening']
    node_id: str | None = None
    wall_id: str | None = None
    point: Pt | None = None
    start: Pt | None = None
    end: Pt | None = None
    opening: PlanOpening | None = None


def apply_operation(source: CanonicalPlan, op: GraphOperation) -> CanonicalPlan:
    candidate = source.model_copy(deep=True)
    nodes = {n.id: n for n in candidate.nodes}
    walls = {w.id: w for w in candidate.walls}
    if op.kind == 'move_junction':
        if op.node_id not in nodes or op.point is None:
            raise ValueError('move_junction requires a known node_id and point')
        nodes[op.node_id].point = op.point.model_copy(deep=True)
    elif op.kind == 'split_wall':
        if op.wall_id not in walls or op.point is None:
            raise ValueError('split_wall requires wall_id and point')
        w = walls[op.wall_id]
        a, b = nodes[w.start_node_id].point, nodes[w.end_node_id].point
        dx, dy = b.x-a.x, b.y-a.y
        length2 = dx*dx + dy*dy
        if length2 < 9:
            raise ValueError('Cannot split a short wall')
        t = ((op.point.x-a.x)*dx + (op.point.y-a.y)*dy)/length2
        projected = Pt(x=a.x+t*dx, y=a.y+t*dy)
        if not .01<t<.99 or hypot(projected.x-op.point.x, projected.y-op.point.y)>1:
            raise ValueError('Split point must lie inside the wall centerline')
        new_node_id = 'node-'+uuid4().hex
        new_wall_id = 'wall-'+uuid4().hex
        candidate.nodes.append(PlanNode(id=new_node_id, point=projected))
        second = w.model_copy(deep=True)
        second.id = new_wall_id
        second.start_node_id = new_node_id
        second.end_node_id = w.end_node_id
        w.end_node_id = new_node_id
        candidate.walls.append(second)
        # Existing room boundary references stay continuous in both directions.
        for room in candidate.rooms:
            boundary = []
            for ref in room.boundary:
                if ref.wall_id != w.id:
                    boundary.append(ref)
                elif ref.forward:
                    boundary += [BoundaryEdge(wall_id=w.id,forward=True),
                                 BoundaryEdge(wall_id=second.id,forward=True)]
                else:
                    boundary += [BoundaryEdge(wall_id=second.id,forward=False),
                                 BoundaryEdge(wall_id=w.id,forward=False)]
            room.boundary = boundary
        hosted = [o for o in candidate.openings if o.wall_id == w.id]
        if hosted and not candidate.px_per_meter:
            raise ValueError('Cannot reanchor split openings without metric scale')
        first_length_m = hypot(dx,dy)*t / candidate.px_per_meter if candidate.px_per_meter else 0
        for opening in hosted:
            start, end = opening.offset_m, opening.offset_m + opening.width_m
            if start < first_length_m-0.001 and end > first_length_m+0.001:
                raise ValueError(f'Split would cut through opening {opening.id}')
            if start >= first_length_m-0.001:
                opening.wall_id = second.id
                opening.offset_m = max(0., round(start-first_length_m, 6))
    elif op.kind == 'remove_wall':
        if op.wall_id not in walls:
            raise ValueError('remove_wall requires a known wall_id')
        if any(o.wall_id == op.wall_id for o in candidate.openings):
            raise ValueError('Cannot remove a wall hosting an opening')
        if any(ref.wall_id == op.wall_id for room in candidate.rooms for ref in room.boundary):
            raise ValueError('Cannot remove a room boundary without explicit room reconciliation')
        candidate.walls = [w for w in candidate.walls if w.id != op.wall_id]
    elif op.kind == 'add_wall':
        if op.start is None or op.end is None:
            raise ValueError('add_wall requires start and end points')
        if hypot(op.start.x-op.end.x, op.start.y-op.end.y) < 3:
            raise ValueError('Cannot add a short wall')
        def endpoint(point: Pt) -> str:
            matches = [n.id for n in candidate.nodes if hypot(n.point.x-point.x,n.point.y-point.y)<.01]
            if len(matches)>1:
                raise ValueError('Ambiguous coincident junctions')
            if matches:
                return matches[0]
            nid = 'node-'+uuid4().hex
            candidate.nodes.append(PlanNode(id=nid,point=point.model_copy(deep=True)))
            return nid
        start, end = endpoint(op.start), endpoint(op.end)
        if start == end:
            raise ValueError('Cannot connect a junction to itself')
        if any({w.start_node_id,w.end_node_id}=={start,end} for w in candidate.walls):
            raise ValueError('Duplicate wall between same junctions')
        candidate.walls.append(PlanWall(id='wall-'+uuid4().hex,
                                        start_node_id=start,end_node_id=end,
                                        source_wall_id=None,inferred=False))
    elif op.kind == 'attach_opening':
        if op.opening is None:
            raise ValueError('attach_opening requires opening data')
        if candidate.scale_source != 'user_confirmed' or not candidate.px_per_meter:
            raise ValueError('Physical openings require user-confirmed metric scale')
        if op.opening.wall_id not in walls:
            raise ValueError('Opening host not found')
        if any(o.id == op.opening.id for o in candidate.openings):
            raise ValueError('Duplicate opening ID')
        candidate.openings.append(op.opening.model_copy(deep=True))
    # Preserve confirmed room references rather than silently re-polygonizing.
    # Only initialize room hypotheses when no room exists yet.
    if not candidate.rooms and op.kind == 'add_wall':
        candidate.rooms = derive_faces(candidate)
    return require_valid(candidate)
