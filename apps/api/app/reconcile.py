"""Conservative deterministic fusion; geometry remains unverified until reviewed."""
from __future__ import annotations
from math import hypot
from .evidence import Evidence
from .geometry import Geometry, Pt, Wall, validate_geometry

def _distance_point_segment(px:float,py:float,a,b)->float:
    dx,dy=b[0]-a[0],b[1]-a[1]
    t=max(0,min(1,((px-a[0])*dx+(py-a[1])*dy)/(dx*dx+dy*dy))) if dx*dx+dy*dy else 0
    return hypot(px-(a[0]+t*dx),py-(a[1]+t*dy))

def reconcile(geometry:Geometry,evidence:Evidence)->Geometry:
    """Only annotate and deduplicate: never shift architectural points on weak evidence."""
    g=geometry.model_copy(deep=True)
    warnings=list(dict.fromkeys(g.warnings))
    if (g.width_px,g.height_px)!=(evidence.width,evidence.height):
        raise ValueError('Geometry and evidence image coordinate systems differ')
    unique=[]
    for wall in g.walls:
        a,b=wall.start,wall.end
        if hypot(a.x-b.x,a.y-b.y)<3:
            warnings.append('Discarded near-zero wall '+wall.id)
            if any(o.wall_id==wall.id for o in g.openings):
                # Preserve referenced wall so openings cannot silently move.
                unique.append(wall)
            continue
        def similar(other:Wall)->bool:
            return ((hypot(a.x-other.start.x,a.y-other.start.y)<3 and
                    hypot(b.x-other.end.x,b.y-other.end.y)<3) or
                    (hypot(a.x-other.end.x,a.y-other.end.y)<3 and
                    hypot(b.x-other.start.x,b.y-other.start.y)<3))
        if any(similar(prev) for prev in unique):
            # Keep referenced wall IDs to avoid orphaning an opening.
            if any(o.wall_id==wall.id for o in g.openings):unique.append(wall)
            else:warnings.append('Omitted duplicate wall '+wall.id)
            continue
        unique.append(wall)
    g.walls=unique
    segments=evidence.segments
    supported=0
    for wall in g.walls:
        midx=(wall.start.x+wall.end.x)/2
        midy=(wall.start.y+wall.end.y)/2
        wall_angle=__import__('math').atan2(wall.end.y-wall.start.y,wall.end.x-wall.start.x)
        match=False
        for s in segments:
            dx,dy=s.x2-s.x1,s.y2-s.y1
            angle=__import__('math').atan2(dy,dx)
            if abs(__import__('math').sin(wall_angle-angle))>.13:continue
            if _distance_point_segment(midx,midy,(s.x1,s.y1),(s.x2,s.y2))<=max(7,min(g.width_px,g.height_px)*.01):
                match=True;break
        if match:supported+=1
    if g.walls and supported<len(g.walls):
        warnings.append(str(len(g.walls)-supported)+' of '+str(len(g.walls))+' wall centerlines lack nearby parallel detected evidence; review manually')
    warnings.extend(validate_geometry(g))
    g.warnings=list(dict.fromkeys(warnings+evidence.warnings))
    return g
