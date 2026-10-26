"""Suggest opening-to-wall associations in image pixels without mutating geometry.

YOLO boxes indicate likely opening regions, not verified wall cutouts.
Require a nearby approximately aligned wall and reject ambiguous matches.
"""
from __future__ import annotations
from math import hypot
from pydantic import BaseModel
from .geometry import Geometry, Opening, Pt

class OpeningHint(BaseModel):
    candidate_id:str
    kind:str
    x1:float
    y1:float
    x2:float
    y2:float
    source_confidence:float
    wall_id:str|None=None
    fraction:float|None=None
    reason:str

def associate_opening(geometry:Geometry, hint:OpeningHint, max_distance_px:float=24.)->OpeningHint:
    cx=(hint.x1+hint.x2)/2;cy=(hint.y1+hint.y2)/2
    horizontal_box=(hint.x2-hint.x1)>=(hint.y2-hint.y1)
    matches=[]
    for wall in geometry.walls:
        a,b=wall.start,wall.end
        dx=b.x-a.x;dy=b.y-a.y
        squared=dx*dx+dy*dy
        if squared<100:continue
        horizontal_wall=abs(dx)>=abs(dy)
        if horizontal_wall!=horizontal_box:continue
        t=max(0,min(1,((cx-a.x)*dx+(cy-a.y)*dy)/squared))
        x=a.x+t*dx;y=a.y+t*dy
        distance=hypot(cx-x,cy-y)
        if distance<=max_distance_px and .02<t<.98:
            matches.append((distance,wall.id,t))
    matches.sort()
    if not matches:return hint.model_copy(update={'reason':'No aligned wall nearby; manual placement required'})
    if len(matches)>1 and matches[1][0]-matches[0][0]<5:
        return hint.model_copy(update={'reason':'Two nearby walls; choose the host wall manually'})
    _,wall_id,t=matches[0]
    return hint.model_copy(update={'wall_id':wall_id,'fraction':round(t,5),
                                    'reason':'Provisional association — confirm span and scale'})

def create_opening(geometry:Geometry,hint:OpeningHint)->tuple[Geometry,str]:
    if hint.kind not in ('door','window') or hint.wall_id is None or hint.fraction is None:
        return geometry,'unresolved'
    result=geometry.model_copy(deep=True)
    wall=next((w for w in result.walls if w.id==hint.wall_id),None)
    if wall is None:return geometry,'unresolved'
    length_px=hypot(wall.end.x-wall.start.x,wall.end.y-wall.start.y)
    ppm=result.px_per_meter or 60.
    length_m=length_px/ppm
    box_pixels=max(hint.x2-hint.x1,hint.y2-hint.y1)
    width=max(.25,min(box_pixels/ppm,length_m*.65))
    offset=max(0.,min(length_m-width,hint.fraction*length_m-width/2))
    # Identity first: re-classification must not create a duplicate.
    match=next((o for o in result.openings if o.source_detection_id==hint.candidate_id),None)
    overlapping=[o for o in result.openings if o.wall_id==wall.id and o.id!=(match.id if match else None)
                 and offset<o.offset_m+o.width_m and o.offset_m<offset+width]
    if overlapping:return geometry,'overlap'
    if match:
        if not match.inferred:return geometry,'confirmed'
        match.kind=hint.kind;match.wall_id=wall.id
        match.offset_m=round(offset,4);match.width_m=round(width,4)
        match.height_m=2.1 if hint.kind=='door' else 1.2
        match.sill_m=0. if hint.kind=='door' else .9
        return result,'updated'
    result.openings.append(Opening(
        id='review-'+hint.candidate_id,source_detection_id=hint.candidate_id,
        kind=hint.kind,wall_id=wall.id,offset_m=round(offset,4),
        width_m=round(width,4),height_m=2.1 if hint.kind=='door' else 1.2,
        sill_m=0. if hint.kind=='door' else .9,inferred=True,reviewed=False))
    return result,'added'
