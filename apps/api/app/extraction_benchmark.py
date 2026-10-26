"""Reproducible extraction benchmark. No production layout writes or hidden AI calls.

Inputs are explicit normalized JSON exports from YOLO/Yytsi, Raster2Seq,
Tectly or human ground truth. Unsupported vendor schemas are rejected rather
than silently guessed. Both wall and room geometry are evaluated in ORIGINAL
raster coordinates. Run: uv run python -m app.extraction_benchmark ... 
"""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import argparse
import hashlib
import json
import math
from typing import Any
from PIL import Image
from pydantic import BaseModel, Field, model_validator
from shapely.geometry import Polygon
from shapely.ops import unary_union

class Point(BaseModel):
    x: float
    y: float

class Segment(BaseModel):
    start: Point
    end: Point
    kind: str = 'wall'

class OpeningLabel(BaseModel):
    kind: str
    start: Point
    end: Point

class PlanPrediction(BaseModel):
    schema_version: int = 1
    provider: str = Field(min_length=1)
    image_sha256: str = Field(min_length=64,max_length=64)
    width_px: int = Field(gt=0)
    height_px: int = Field(gt=0)
    walls: list[Segment] = Field(default_factory=list)
    rooms: list[list[Point]] = Field(default_factory=list)
    openings: list[OpeningLabel] = Field(default_factory=list)
    px_per_meter: float | None = Field(default=None,gt=0)
    scale_source: str | None = None
    metadata: dict[str,Any] = Field(default_factory=dict)

    @model_validator(mode='after')
    def validate_geometry(self):
        if self.schema_version!=1:
            raise ValueError('Unsupported benchmark schema')
        for segment in [*self.walls,*self.openings]:
            if segment.start==segment.end:
                raise ValueError('Zero length geometry')
            for point in (segment.start,segment.end):
                if not (0<=point.x<=self.width_px and 0<=point.y<=self.height_px):
                    raise ValueError('Point outside original image coordinates')
        for room in self.rooms:
            if len(room)<3:raise ValueError('Room polygon needs 3 vertices')
            for point in room:
                if not (0<=point.x<=self.width_px and 0<=point.y<=self.height_px):
                    raise ValueError('Room point outside original image')
            poly=Polygon([(p.x,p.y) for p in room])
            if not poly.is_valid or poly.area<=0:
                raise ValueError('Invalid room polygon')
        return self

def image_identity(path:Path)->dict:
    with Image.open(path) as im:
        width,height=im.size
        im.verify()
    return {'image_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
            'width_px':width,'height_px':height}

def load_prediction(path:Path)->PlanPrediction:
    return PlanPrediction.model_validate_json(path.read_text(encoding='utf-8'))

def save_prediction(path:Path,model:PlanPrediction)->None:
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(model.model_dump_json(indent=2)+'\n',encoding='utf-8')

def _wall_match(a:Segment,b:Segment,tolerance_px:float)->bool:
    ax=a.end.x-a.start.x;ay=a.end.y-a.start.y
    bx=b.end.x-b.start.x;by=b.end.y-b.start.y
    la=math.hypot(ax,ay);lb=math.hypot(bx,by)
    if la<1e-6 or lb<1e-6:return False
    cosine=abs((ax*bx+ay*by)/(la*lb))
    if cosine<math.cos(math.radians(12)):return False
    def dist_to_line(p,s):
        dx=s.end.x-s.start.x;dy=s.end.y-s.start.y
        return abs((p.x-s.start.x)*dy-(p.y-s.start.y)*dx)/math.hypot(dx,dy)
    if (dist_to_line(a.start,b)+dist_to_line(a.end,b))/2>tolerance_px:return False
    ux=ax/la;uy=ay/la
    aa=(0.,la)
    t1=(b.start.x-a.start.x)*ux+(b.start.y-a.start.y)*uy
    t2=(b.end.x-a.start.x)*ux+(b.end.y-a.start.y)*uy
    overlap=max(0.,min(aa[1],max(t1,t2))-max(aa[0],min(t1,t2)))
    return overlap>=.5*min(la,lb)

def _matching(pred:list,truth:list,predicate)->int:
    # Maximum cardinality matching, not greedy, to prevent double-counting
    edges=[[j for j,t in enumerate(truth) if predicate(p,t)] for p in pred]
    used={}
    def augment(i,seen):
        for j in edges[i]:
            if j in seen:continue
            seen.add(j)
            if j not in used or augment(used[j],seen):
                used[j]=i
                return True
        return False
    return sum(augment(i,set()) for i in range(len(pred)))

def _prf(matches:int, predicted:int, actual:int)->dict:
    precision=matches/predicted if predicted else (1. if actual==0 else 0.)
    recall=matches/actual if actual else (1. if predicted==0 else 0.)
    f1=2*precision*recall/(precision+recall) if precision+recall else 0.
    return {'matched':matches,'predicted':predicted,'ground_truth':actual,
            'precision':round(precision,4),'recall':round(recall,4),'f1':round(f1,4)}

def compare(truth:PlanPrediction,pred:PlanPrediction,tolerance_px:float=8.)->dict:
    if tolerance_px<=0:raise ValueError('Positive wall tolerance required')
    if (truth.image_sha256,truth.width_px,truth.height_px)!=(pred.image_sha256,pred.width_px,pred.height_px):
        raise ValueError('Image hash or dimensions mismatch: cannot compare different crops')
    walls=_matching(pred.walls,truth.walls,lambda a,b:_wall_match(a,b,tolerance_px))
    openings=_matching(pred.openings,truth.openings,
        lambda a,b:a.kind==b.kind and _wall_match(
          Segment(start=a.start,end=a.end),Segment(start=b.start,end=b.end),tolerance_px*1.5))
    ppolys=[Polygon([(p.x,p.y) for p in poly]) for poly in pred.rooms]
    tpolys=[Polygon([(p.x,p.y) for p in poly]) for poly in truth.rooms]
    pa=unary_union(ppolys) if ppolys else Polygon()
    ta=unary_union(tpolys) if tpolys else Polygon()
    union=pa.union(ta).area
    iou=pa.intersection(ta).area/union if union else None
    scale_error=(abs(pred.px_per_meter-truth.px_per_meter)/truth.px_per_meter
        if pred.px_per_meter is not None and truth.px_per_meter is not None else None)
    return {'provider':pred.provider,'source_sha256':truth.image_sha256,
            'walls':_prf(walls,len(pred.walls),len(truth.walls)),
            'openings':_prf(openings,len(pred.openings),len(truth.openings)),
            'room_area_iou':round(iou,4) if iou is not None else None,
            'room_count':{'predicted':len(pred.rooms),'ground_truth':len(truth.rooms)},
            'relative_scale_error':round(scale_error,4) if scale_error is not None else None,
            'limitations':['Wall F1 matches segments, not exact pixel masks or connected topology.',
             'Room IoU compares the UNION of room polygons, not room-by-room adjacency.']}

def main()->None:
    parser=argparse.ArgumentParser(description='Compare extraction exports against an independently labeled truth')
    parser.add_argument('--truth',type=Path,required=True)
    parser.add_argument('--predictions',type=Path,nargs='+',required=True)
    parser.add_argument('--image',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--tolerance-px',type=float,default=8.)
    args=parser.parse_args()
    expected=image_identity(args.image)
    truth=load_prediction(args.truth)
    if any(getattr(truth,k)!=v for k,v in expected.items()):
        parser.error('Ground truth must refer to the exact original input image')
    results=[]
    for path in args.predictions:
        prediction=load_prediction(path)
        results.append(compare(truth,prediction,args.tolerance_px))
    report={'schema_version':1,'image':str(args.image),'metrics':results}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,indent=2))

if __name__=='__main__':
    main()
