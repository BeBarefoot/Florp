from typing import Any
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
    kind: str
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
    rooms: list[Room] = Field(default_factory=list)
    walls: list[Wall] = Field(default_factory=list)
    openings: list[Opening] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    @model_validator(mode='after')
    def check(self):
        ids={w.id for w in self.walls}
        for o in self.openings:
            if o.wall_id not in ids: raise ValueError(f'Opening {o.id} has unknown wall')
            w=next(w for w in self.walls if w.id==o.wall_id)
            length=hypot(w.end.x-w.start.x,w.end.y-w.start.y)
            if self.px_per_meter and (o.offset_m+o.width_m)*self.px_per_meter > length+1:
                raise ValueError(f'Opening {o.id} exceeds wall length')
        return self

def validate_geometry(g:Geometry)->list[str]:
    errors=[]
    for room in g.rooms:
        coords=[(p.x,p.y) for p in room.points]
        area=abs(sum(x*y2-x2*y for (x,y),(x2,y2) in zip(coords,coords[1:]+coords[:1]))/2)
        if area<4: errors.append(f'Room {room.id} has near-zero area')
        for p in room.points:
            if not (0<=p.x<=g.width_px and 0<=p.y<=g.height_px): errors.append(f'Room {room.id} exceeds image')
    if not g.px_per_meter: errors.append('Scale is not calibrated; metric geometry is provisional')
    return errors

def fallback_geometry(width:int,height:int)->Geometry:
    pad=min(width,height)*0.12
    x0,y0,x1,y1=pad,pad,width-pad,height-pad
    walls=[Wall(id=f'w{i}',start=Pt(x=a[0],y=a[1]),end=Pt(x=b[0],y=b[1])) for i,(a,b) in enumerate(zip([(x0,y0),(x1,y0),(x1,y1),(x0,y1)],[(x1,y0),(x1,y1),(x0,y1),(x0,y0)]))]
    return Geometry(width_px=width,height_px=height,rooms=[Room(id='room-1',label='Unverified room',points=[Pt(x=x0,y=y0),Pt(x=x1,y=y0),Pt(x=x1,y=y1),Pt(x=x0,y=y1)])],walls=walls,warnings=['Starter geometry for manual editing only; not AI extraction','Calibrate the scale before relying on dimensions'])
