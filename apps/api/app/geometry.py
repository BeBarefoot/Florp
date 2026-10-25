from typing import Any, Literal
from pydantic import BaseModel, Field, model_validator
from math import hypot
class Pt(BaseModel):
    x: float
    y: float
class Room(BaseModel):
    id: str
    label: str = 'Room'
    points: list[Pt] = Field(min_length=3)
    confidence: float = Field(default=0.0, ge=0, le=1)
class Wall(BaseModel):
    id: str
    start: Pt
    end: Pt
    thickness_m: float = Field(default=0.15, gt=0, le=2)
    height_m: float = Field(default=2.8, gt=0, le=20)
    inferred: bool = True
class Opening(BaseModel):
    id: str
    kind: Literal['door', 'window']
    wall_id: str
    offset_m: float = Field(ge=0)
    width_m: float = Field(gt=0)
    height_m: float = Field(gt=0)
    sill_m: float = Field(default=0.0, ge=0)
    inferred: bool = True
class Geometry(BaseModel):
    width_px: int = Field(gt=0)
    height_px: int = Field(gt=0)
    px_per_meter: float | None = Field(default=None, gt=0)
    scale_source: Literal['unknown','provisional_auto','user_confirmed'] = 'unknown'
    structure_reviewed: bool = False
    rooms: list[Room] = Field(default_factory=list)
    walls: list[Wall] = Field(default_factory=list)
    openings: list[Opening] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    @model_validator(mode='after')
    def check(self):
        edges={w.id:(w.start,w.end,w.height_m) for w in self.walls}
        for room in self.rooms:
            for i,a in enumerate(room.points):
                edges['boundary:'+room.id+':'+str(i)]=(a,room.points[(i+1)%len(room.points)],2.8)
        by_wall={}
        for o in self.openings:
            if o.wall_id not in edges: raise ValueError(f'Opening {o.id} has unknown wall')
            a,b,height=edges[o.wall_id]
            if o.sill_m+o.height_m>height+0.001:
                raise ValueError(f'Opening {o.id} exceeds wall height')
            if o.kind=='door' and o.sill_m>0.001:
                raise ValueError(f'Door {o.id} must start at floor')
            if self.px_per_meter:
                length=hypot(b.x-a.x,b.y-a.y)/self.px_per_meter
                if o.offset_m+o.width_m>length+0.001:
                    raise ValueError(f'Opening {o.id} exceeds wall length')
            by_wall.setdefault(o.wall_id,[]).append(o)
        for wall_id,items in by_wall.items():
            items=sorted(items,key=lambda x:x.offset_m)
            for left,right in zip(items,items[1:]):
                if left.offset_m+left.width_m>right.offset_m+0.001:
                    raise ValueError(f'Overlapping openings on {wall_id}')
        return self

def _segments_cross(a,b,c,d):
    def orient(p,q,r):
        return (q.x-p.x)*(r.y-p.y)-(q.y-p.y)*(r.x-p.x)
    return orient(a,b,c)*orient(a,b,d)<0 and orient(c,d,a)*orient(c,d,b)<0

def validate_geometry(g:Geometry)->list[str]:
    errors=[]
    for room in g.rooms:
        coords=[(p.x,p.y) for p in room.points]
        area=abs(sum(x*y2-x2*y for (x,y),(x2,y2) in zip(coords,coords[1:]+coords[:1]))/2)
        if area<4: errors.append(f'Room {room.id} has near-zero area')
        pts=room.points
        for i in range(len(pts)):
            if hypot(pts[i].x-pts[(i+1)%len(pts)].x,pts[i].y-pts[(i+1)%len(pts)].y)<2:
                errors.append(f'Room {room.id} has a zero-length edge')
            for j in range(i+1,len(pts)):
                if j==i+1 or (i==0 and j==len(pts)-1): continue
                if _segments_cross(pts[i],pts[(i+1)%len(pts)],pts[j],pts[(j+1)%len(pts)]):
                    errors.append(f'Room {room.id} self-intersects')
                    break
        for p in room.points:
            if not (0<=p.x<=g.width_px and 0<=p.y<=g.height_px): errors.append(f'Room {room.id} exceeds image')
    for wall in g.walls:
        if hypot(wall.end.x-wall.start.x,wall.end.y-wall.start.y)<3:
            errors.append(f'Wall {wall.id} is too short')
        for p in (wall.start,wall.end):
            if not (0<=p.x<=g.width_px and 0<=p.y<=g.height_px):
                errors.append(f'Wall {wall.id} exceeds image')
    if g.openings and not g.px_per_meter: errors.append('Openings require calibrated scale')
    if not g.px_per_meter: errors.append('Metric scale could not be inferred from blueprint; verify a dimension')
    elif g.scale_source=='provisional_auto': errors.append('Automatic scale is provisional; confirm a shown dimension before verification')
    return errors

def fallback_geometry(width:int,height:int)->Geometry:
    pad=min(width,height)*0.12
    x0,y0,x1,y1=pad,pad,width-pad,height-pad
    walls=[Wall(id=f'w{i}',start=Pt(x=a[0],y=a[1]),end=Pt(x=b[0],y=b[1])) for i,(a,b) in enumerate(zip([(x0,y0),(x1,y0),(x1,y1),(x0,y1)],[(x1,y0),(x1,y1),(x0,y1),(x0,y0)]))]
    return Geometry(width_px=width,height_px=height,rooms=[Room(id='room-1',label='Unverified room',points=[Pt(x=x0,y=y0),Pt(x=x1,y=y0),Pt(x=x1,y=y1),Pt(x=x0,y=y1)])],walls=walls,warnings=['Starter geometry for manual editing only; not AI extraction','Calibrate the scale before relying on dimensions'])
