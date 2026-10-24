"""High-precision wall *suggestions* from paired parallel line evidence.

Long, axis-aligned, similarly sized strokes at plausible wall-thickness separations
get suggested. Single lines, furniture edges and dimensions remain raw evidence.
Not a segmentation model: all candidates require human confirmation.
"""
from __future__ import annotations
from math import hypot
from pydantic import BaseModel, Field

class WallCandidate(BaseModel):
    x1: float
    y1: float
    x2: float
    y2: float
    score: float = Field(ge=0, le=1)
    support: int = 2

def wall_candidates(segments, labels, width: int, height: int) -> list[WallCandidate]:
    minimum = max(45, min(width, height) * .13)
    min_sep = max(3, min(width, height) * .004)
    max_sep = max(12, min(width, height) * .035)
    raw=[]
    # Ignore strokes overlapping recognized writing, measurements and labels.
    for s in segments:
        dx=s.x2-s.x1;dy=s.y2-s.y1
        length=hypot(dx,dy)
        if length < minimum: continue
        horizontal=abs(dy) <= abs(dx)*.055
        vertical=abs(dx) <= abs(dy)*.055
        if not (horizontal or vertical):continue
        x0,x1=sorted((s.x1,s.x2));y0,y1=sorted((s.y1,s.y2))
        center=((s.x1+s.x2)/2,(s.y1+s.y2)/2)
        # Exclude any detection crossing a text bbox; OCR may be absent.
        if any(t.bbox[0]-4<=center[0]<=t.bbox[2]+4 and
               t.bbox[1]-4<=center[1]<=t.bbox[3]+4 for t in labels):continue
        raw.append((s,horizontal,x0,x1,y0,y1,length))
    output=[]
    for i,(a,h,ax0,ax1,ay0,ay1,alen) in enumerate(raw):
        for b,hb,bx0,bx1,by0,by1,blen in raw[i+1:]:
            if h!=hb:continue
            if h:
                overlap=min(ax1,bx1)-max(ax0,bx0)
                sep=abs((a.y1+a.y2-b.y1-b.y2)/2)
                begin=max(ax0,bx0);end=min(ax1,bx1)
                position=(a.y1+a.y2+b.y1+b.y2)/4
                coords=(begin,position,end,position)
            else:
                overlap=min(ay1,by1)-max(ay0,by0)
                sep=abs((a.x1+a.x2-b.x1-b.x2)/2)
                begin=max(ay0,by0);end=min(ay1,by1)
                position=(a.x1+a.x2+b.x1+b.x2)/4
                coords=(position,begin,position,end)
            if not(min_sep<=sep<=max_sep and overlap>=minimum and
                   overlap/min(alen,blen)>=.65):continue
            score=min(.94,.48+.3*overlap/max(width,height)+.12*min(alen,blen)/max(width,height))
            output.append(WallCandidate(x1=coords[0],y1=coords[1],x2=coords[2],y2=coords[3],score=score))
    output.sort(key=lambda c:(-c.score,-hypot(c.x2-c.x1,c.y2-c.y1)))
    chosen=[]
    for c in output:
        if any(hypot(c.x1-v.x1,c.y1-v.y1)<min_sep*2 and
               hypot(c.x2-v.x2,c.y2-v.y2)<min_sep*2 for v in chosen):continue
        chosen.append(c)
        if len(chosen)==120:break
    return chosen
