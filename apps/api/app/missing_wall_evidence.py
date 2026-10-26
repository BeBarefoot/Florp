"""Recover *suggestions* for walls omitted by box detection.

A candidate must connect near dangling existing endpoints and have continuous
dark source-image support. These are review items, never auto-added walls.
"""
from __future__ import annotations
from math import hypot
from pathlib import Path
import cv2
import numpy as np
from pydantic import BaseModel, Field
from .geometry import Geometry, Pt

class GapSuggestion(BaseModel):
    id: str
    start: Pt
    end: Pt
    axis: str
    image_support: float = Field(ge=0,le=1)
    kind: str = 'suggested_missing_wall'
    explanation: str = 'Aligned dangling wall endpoints with source-image support; unverified'

def _endpoint_neighbors(geometry: Geometry, tolerance: float=9.):
    ends=[(wall.id,point) for wall in geometry.walls for point in (wall.start,wall.end)]
    return [(wall_id,p) for wall_id,p in ends
            if not any(other_id!=wall_id and hypot(q.x-p.x,q.y-p.y)<=tolerance
                       for other_id,q in ends)]

def gap_suggestions(geometry:Geometry, preview:Path, max_gap_px:float=200,
                    min_support:float=.64, max_results:int=32)->list[GapSuggestion]:
    if not 10<=max_gap_px<=400:raise ValueError('Invalid maximum gap')
    image=cv2.imread(str(preview),cv2.IMREAD_GRAYSCALE)
    if image is None:raise ValueError('Unable to read plan image')
    h,w=image.shape
    if (w,h)!=(geometry.width_px,geometry.height_px):
        raise ValueError('Preview and geometry dimensions disagree')
    # Local adaptive threshold is more tolerant of uneven scans.
    binary=cv2.adaptiveThreshold(image,255,cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                  cv2.THRESH_BINARY_INV,31,9)
    ends=_endpoint_neighbors(geometry)
    proposals=[]
    seen=set()
    for i,(wall_a,a) in enumerate(ends):
        for wall_b,b in ends[i+1:]:
            if wall_a==wall_b:continue
            dx=b.x-a.x;dy=b.y-a.y
            span=hypot(dx,dy)
            if not 12<=span<=max_gap_px:continue
            horizontal=abs(dy)<=min(7.,span*.07)
            vertical=abs(dx)<=min(7.,span*.07)
            if not (horizontal or vertical):continue
            axis='horizontal' if horizontal else 'vertical'
            # Reject lines that retrace an existing wall rather than fill a gap.
            midpoint=Pt(x=(a.x+b.x)/2,y=(a.y+b.y)/2)
            if any(_distance(midpoint,edge.start,edge.end)<5 for edge in geometry.walls):
                continue
            count=max(10,int(span/2))
            xs=np.rint(np.linspace(a.x,b.x,count)).astype(int).clip(0,w-1)
            ys=np.rint(np.linspace(a.y,b.y,count)).astype(int).clip(0,h-1)
            radius=2
            supported=0
            # Remove endpoint neighborhoods so existing wall ink does not
            # inflate a gap's source support score.
            for k in range(2,count-2):
                x=xs[k];y=ys[k]
                x0=max(0,x-radius);x1=min(w,x+radius+1)
                y0=max(0,y-radius);y1=min(h,y+radius+1)
                supported+=bool(np.any(binary[y0:y1,x0:x1]))
            usable=count-4
            support=supported/usable if usable>0 else 0
            if support<min_support:continue
            key=tuple(sorted(((round(a.x/5),round(a.y/5)),
                              (round(b.x/5),round(b.y/5)))))
            if key in seen:continue
            seen.add(key)
            proposals.append(GapSuggestion(id=f'gap-{len(proposals)}',
               start=a,end=b,axis=axis,image_support=round(support,3)))
    proposals.sort(key=lambda item:(-item.image_support,
                  -hypot(item.end.x-item.start.x,item.end.y-item.start.y)))
    return proposals[:max_results]

def _distance(p:Pt,a:Pt,b:Pt)->float:
    dx=b.x-a.x;dy=b.y-a.y
    denom=dx*dx+dy*dy
    if denom<1e-6:return hypot(p.x-a.x,p.y-a.y)
    t=max(0,min(1,((p.x-a.x)*dx+(p.y-a.y)*dy)/denom))
    return hypot(p.x-a.x-t*dx,p.y-a.y-t*dy)
