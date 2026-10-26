"""Model-disagreement-aware wall evidence on one canonical pixel grid.

Keep YOLO-only proposals for explicit human review rather than discarding them.
Agreement boosts review priority; heuristic scores are NOT calibrated probabilities.
No structural wall is verified automatically.
"""
from __future__ import annotations
from math import hypot
import numpy as np
import cv2
from pydantic import BaseModel,Field
from .geometry import Geometry,Wall,Pt
from .pretrained_detector import DetectorResult
from .model_reconstruction import _model_wall_candidates
from .wall_segmentation import WallMaskReport
from .wall_run_normalization import consolidate_wall_runs
from .graph_reconstruction import propose_connected_geometry
from .topology import audit_topology

class FusedCandidate(BaseModel):
    id: str
    start: Pt
    end: Pt
    sources: list[str]
    mask_support: float = Field(ge=0,le=1)
    reviewed: bool = False
    category: str = 'yytsi_only'
    review_priority: float = Field(default=0,ge=0,le=1)
    yolo_confidence: float | None = None

class FusionComparison(BaseModel):
    image_width: int
    image_height: int
    mask_lines: int
    yolo_wall_boxes: int
    accepted_yolo_candidates: int
    rejected_yolo_candidates: int
    yolo_only_candidates: int = 0
    yytsi_only_candidates: int = 0
    agreed_candidates: int = 0
    fused_walls: int
    topology: dict
    warnings: list[str]

def _support(mask:np.ndarray,a:Pt,b:Pt)->float:
    h,w=mask.shape
    count=max(12,int(hypot(b.x-a.x,b.y-a.y)/3))
    xs=np.clip(np.rint(np.linspace(a.x,b.x,count)).astype(int),0,w-1)
    ys=np.clip(np.rint(np.linspace(a.y,b.y,count)).astype(int),0,h-1)
    # A 5px neighborhood tolerates line-center drift without allowing wide
    # furniture regions to lend support across unrelated wall candidates.
    return float(np.mean([np.any(mask[max(0,y-2):min(h,y+3),
                                       max(0,x-2):min(w,x+3)]>0)
                          for x,y in zip(xs,ys)]))

def _same_axis(a:Pt,b:Pt,c:Pt,d:Pt,tolerance:float=8)->bool:
    ah=abs(b.x-a.x)>=abs(b.y-a.y)
    bh=abs(d.x-c.x)>=abs(d.y-c.y)
    if ah!=bh:return False
    if ah:
        return abs((a.y+b.y-c.y-d.y)/2)<=tolerance and (
            min(max(a.x,b.x),max(c.x,d.x))-max(min(a.x,b.x),min(c.x,d.x))>0)
    return abs((a.x+b.x-c.x-d.x)/2)<=tolerance and (
        min(max(a.y,b.y),max(c.y,d.y))-max(min(a.y,b.y),min(c.y,d.y))>0)

def _overlap_fraction(a:Pt,b:Pt,c:Pt,d:Pt)->float:
    horizontal=abs(b.x-a.x)>=abs(b.y-a.y)
    lo1,hi1=sorted((a.x,b.x)) if horizontal else sorted((a.y,b.y))
    lo2,hi2=sorted((c.x,d.x)) if horizontal else sorted((c.y,d.y))
    return max(0,min(hi1,hi2)-max(lo1,lo2))/max(1,min(hi1-lo1,hi2-lo2))

def fuse_evidence(base:Geometry,mask:np.ndarray,report:WallMaskReport,
                  detector:DetectorResult|None, min_support:float=.55):
    if mask.shape!=(base.height_px,base.width_px):
        raise ValueError('Segmentation mask does not match original blueprint pixels')
    if detector and (detector.image_width,detector.image_height)!=(base.width_px,base.height_px):
        raise ValueError('YOLO and Yytsi coordinates differ: no fusion performed')
    lines=consolidate_wall_runs(report).lines
    mask_axes=[(Pt(x=l.x1,y=l.y1),Pt(x=l.x2,y=l.y2),l) for l in lines]
    candidates=[]
    accepted=rejected=0
    matched=set()
    if detector:
        for index,a,b in _model_wall_candidates(detector)[0]:
            support=_support(mask,a,b)
            confidence=float(detector.boxes[index].confidence)
            matches=[i for i,(p,q,_) in enumerate(mask_axes)
                     if _same_axis(a,b,p,q,tolerance=10)]
            matched.update(matches)
            agreed=bool(matches) or support>=min_support
            accepted+=int(agreed)
            rejected+=int(not agreed)
            candidates.append(FusedCandidate(id=f'yolo-wall-{index}',start=a,end=b,
                sources=[f'yolo_box:{index}']+(['yytsi_mask'] if agreed else []),
                mask_support=round(support,3),
                category='agreed' if agreed else 'yolo_only',
                review_priority=round(min(1,.55+.25*confidence+.2*support),3)
                    if agreed else round(min(.75,.2+.45*confidence),3),
                yolo_confidence=confidence))
    for i,(a,b,line) in enumerate(mask_axes):
        if i in matched:continue
        if any(_same_axis(a,b,item.start,item.end,tolerance=10) for item in candidates):
            continue
        candidates.append(FusedCandidate(id=f'mask-{i}',start=a,end=b,
            sources=['yytsi_mask'],mask_support=_support(mask,a,b),
            category='yytsi_only',review_priority=round(.35+.4*line.support,3)))
    candidates.sort(key=lambda c:(-hypot(c.end.x-c.start.x,c.end.y-c.start.y),c.id))
    unique=[]
    for item in candidates:
        prior=next((p for p in unique if _same_axis(item.start,item.end,p.start,p.end,7)
                    and _overlap_fraction(item.start,item.end,p.start,p.end)>=.8),None)
        if prior is None:unique.append(item)
        else:
            prior.sources=list(dict.fromkeys(prior.sources+item.sources))
            prior.mask_support=max(prior.mask_support,item.mask_support)
            prior.review_priority=max(prior.review_priority,item.review_priority)
            if item.category=='agreed':prior.category='agreed'
    candidates=sorted(unique,key=lambda item:(-item.review_priority,item.id))
    proposed=base.model_copy(deep=True)
    proposed.rooms=[]
    # Default preview is deliberately conservative: YOLO-only walls require
    # explicit acceptance, while mask-derived proposals remain unverified.
    proposed.walls=[Wall(id=item.id,start=item.start,end=item.end,inferred=True)
                    for item in candidates if item.category!='yytsi_only']
    proposed.openings=[]  # Opening association needs a separate verified step.
    proposed.structure_reviewed=False
    proposed.warnings=list(dict.fromkeys(base.warnings+[
        'Fused wall proposal: original YOLO boxes and Yytsi mask compared in identical pixels.',
        'Opening detections remain separate; DO NOT assume exact wall attachment.',
        'No wall or room is verified by AI confidence alone.']))
    proposed=propose_connected_geometry(proposed)
    audit=audit_topology(proposed)
    comparison=FusionComparison(image_width=base.width_px,image_height=base.height_px,
       mask_lines=len(lines),yolo_wall_boxes=sum(b.category=='wall' for b in detector.boxes) if detector else 0,
       accepted_yolo_candidates=accepted,rejected_yolo_candidates=rejected,
       yolo_only_candidates=sum(c.category=='yolo_only' for c in candidates),
       yytsi_only_candidates=sum(c.category=='yytsi_only' for c in candidates),
       agreed_candidates=sum(c.category=='agreed' for c in candidates),
       fused_walls=len(proposed.walls),topology=audit.model_dump(),
       warnings=['YOLO unavailable: mask-only comparison' if detector is None else
                 'YOLO-only wall candidates preserved for review; none automatically verified'])
    return proposed,candidates,comparison
