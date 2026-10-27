"""Non-destructive, conservative cleanup of independently approved wall axes.

Only short, geometrically supported endpoint joins are suggested. Never adds
undetected partitions, alters room polygons, invents scale, or modifies walls
hosting doors/windows. All changes are visible and explicitly user-approved.
"""
from __future__ import annotations

from math import hypot
from pydantic import BaseModel, Field
from .geometry import Geometry, Pt
from .structural_graph import build_structural_graph, _project


class EndpointChange(BaseModel):
    wall_id: str
    endpoint: str
    original: Pt
    proposed: Pt
    distance_px: float = Field(ge=0)
    reason: str


class ConnectivityPreview(BaseModel):
    geometry: Geometry
    changes: list[EndpointChange]
    before_components: int
    after_components: int
    before_dangling: int
    after_dangling: int
    warning: str


def _distance(a: Pt, b: Pt) -> float:
    return hypot(a.x-b.x, a.y-b.y)


def _axis_error(p: Pt, a: Pt, b: Pt) -> float:
    dx=b.x-a.x;dy=b.y-a.y
    size=hypot(dx,dy)
    return (abs((p.x-a.x)*dy-(p.y-a.y)*dx)/size) if size>1 else float('inf')


def preview_connectivity(geometry: Geometry, tolerance_px: float = 5.) -> ConnectivityPreview:
    if not 0 < tolerance_px <= 8:
        raise ValueError('tolerance_px must be > 0 and <= 8')
    original=geometry.model_copy(deep=True)
    proposed=geometry.model_copy(deep=True)
    frozen={o.wall_id for o in geometry.openings}
    walls=proposed.walls
    proposals=[]
    # Disallow drift caused by multiple sequential snap passes: each source
    # wall can have at most one moved endpoint, determined from the original.
    for i, wall in enumerate(original.walls):
        if wall.id in frozen:continue
        for endpoint in ('start','end'):
            p=getattr(wall,endpoint)
            opposite=getattr(wall,'end' if endpoint=='start' else 'start')
            choices=[]
            for j, other in enumerate(original.walls):
                if i==j:continue
                for other_endpoint in ('start','end'):
                    q=getattr(other,other_endpoint)
                    d=_distance(p,q)
                    if d<=.05 or d>tolerance_px:continue
                    # Protect existing reviewed geometry and avoid bridging
                    # separate parallel offsets that resemble wall thickness.
                    if _axis_error(q,wall.start,wall.end)>1.75:continue
                    if _axis_error(p,other.start,other.end)>1.75:continue
                    # Both ends should meet: only nudge the current endpoint
                    # toward a fixed endpoint (not midpoint-created geometry).
                    if _distance(q,opposite)<3:continue
                    choices.append((d,j,q,'endpoint alignment'))
                # T junction: a perpendicular wall endpoint landing just
                # short of an existing wall's *interior* centerline.
                t,q,d=_project(p,other.start,other.end)
                dx=wall.end.x-wall.start.x;dy=wall.end.y-wall.start.y
                ux=other.end.x-other.start.x;uy=other.end.y-other.start.y
                norms=hypot(dx,dy)*hypot(ux,uy)
                orth=abs(dx*ux+dy*uy)/norms if norms>0 else 1.
                if .08<t<.92 and .05<d<=tolerance_px and orth<.25 and _axis_error(q,wall.start,wall.end)<=1.75:
                    choices.append((d,j,q,'perpendicular T junction'))
            choices.sort(key=lambda it:(round(it[0],4),it[1],it[2].x,it[2].y))
            if len(choices)!=1 and len(choices)>1:
                # Ambiguous nearby targets: never guess.
                if abs(choices[0][0]-choices[1][0])<2:continue
            if choices:
                d,j,q,reason=choices[0]
                proposals.append((i,endpoint,q,round(d,3),reason))
    # Two endpoints of the same wall must not move in opposite directions
    # during a single automatic proposal.
    by_wall={}
    for change in proposals:
        by_wall.setdefault(change[0],[]).append(change)
    changes=[]
    for i,items in by_wall.items():
        if len(items)!=1:continue
        _,endpoint,q,d,reason=items[0]
        before=getattr(original.walls[i],endpoint)
        candidate=original.walls[i].model_copy(update={endpoint:q})
        if _distance(candidate.start,candidate.end)<3:continue
        setattr(walls[i],endpoint,Pt(x=round(q.x,3),y=round(q.y,3)))
        changes.append(EndpointChange(wall_id=walls[i].id,endpoint=endpoint,
            original=before,proposed=getattr(walls[i],endpoint),
            distance_px=d,reason=reason))
    # No new rooms are inferred; existing room polygons remain unchanged.
    if changes:
        proposed.structure_reviewed=False
        proposed.warnings=list(dict.fromkeys(proposed.warnings+[
            'Connectivity adjustment is provisional; confirm wall junctions before saving.'
        ]))
    before=build_structural_graph(original)
    after=build_structural_graph(proposed)
    return ConnectivityPreview(geometry=proposed,changes=changes,
        before_components=before.disconnected_components,
        after_components=after.disconnected_components,
        before_dangling=before.dangling_nodes,
        after_dangling=after.dangling_nodes,
        warning='Only near-aligned junctions are proposed; unobserved wall spans, rooms, scale and opening anchors are unchanged.')
