"""Conservative exterior/bottom wall recovery from source pixels.

Only proposes long horizontal runs near the bottom of an existing model wall
assembly, supported by actual darkness in the source image and a close vertical
wall endpoint. Never creates an entire bounding rectangle without evidence.
"""
from __future__ import annotations
from pathlib import Path
import cv2
import numpy as np
from math import hypot
from pydantic import BaseModel, Field
from .geometry import Geometry, Pt

class ExteriorRun(BaseModel):
    id: str
    start: Pt
    end: Pt
    support: float = Field(ge=0,le=1)
    kind: str = 'exterior_wall_candidate'

def suggest_bottom_runs(geometry:Geometry, preview:Path,
                        min_length_fraction:float=.28)->list[ExteriorRun]:
    image=cv2.imread(str(preview),cv2.IMREAD_GRAYSCALE)
    if image is None:raise ValueError('Cannot read blueprint preview')
    height,width=image.shape
    if (width,height)!=(geometry.width_px,geometry.height_px):
        raise ValueError('Geometry and source preview dimensions disagree')
    if len(geometry.walls)<2:return []
    vertical=[w for w in geometry.walls if
        abs(w.end.y-w.start.y)>max(35,abs(w.end.x-w.start.x)*3)]
    if not vertical:return []
    bottoms=[max(w.start.y,w.end.y) for w in vertical]
    # Candidates must lie at the lower structural band established by vertical
    # walls, NOT at an arbitrary dimension line at the page margin.
    bottom=max(bottoms)
    band=max(12,min(height*.045,28))
    if bottom<height*.52:return []
    dark=cv2.adaptiveThreshold(image,255,cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                               cv2.THRESH_BINARY_INV,31,8)
    length=max(55,int(width*min_length_fraction))
    kernel=cv2.getStructuringElement(cv2.MORPH_RECT,(max(15,length//4),1))
    horizontal=cv2.morphologyEx(dark,cv2.MORPH_OPEN,kernel)
    hough=cv2.HoughLinesP(horizontal,1,np.pi/180,threshold=max(20,length//5),
                           minLineLength=max(40,length//2),maxLineGap=22)
    if hough is None:return []
    suggestions=[]
    for x1,y1,x2,y2 in np.asarray(hough).reshape(-1,4):
        if abs(y2-y1)>3:continue
        y=(float(y1)+float(y2))/2
        if abs(y-bottom)>band:continue
        if abs(x2-x1)<length:continue
        left,right=sorted((float(x1),float(x2)))
        # Existing vertical endpoint anchors constrain which horizontal evidence
        # is likely to belong to the building, rather than annotations.
        close_anchors=[w for w in vertical if any(
            hypot(p.x-(left if abs(p.x-left)<abs(p.x-right) else right),p.y-y)<max(25,band*1.6)
            for p in (w.start,w.end))]
        if not close_anchors:continue
        samples=max(15,int(right-left)//3)
        xs=np.linspace(left,right,samples).astype(int).clip(0,width-1)
        yy=int(round(y))
        supports=[np.any(dark[max(0,yy-2):min(height,yy+3),max(0,x-2):min(width,x+3)])
                  for x in xs]
        score=float(np.mean(supports))
        if score<.82:continue
        # If the whole candidate is already represented, don't duplicate it.
        if any(abs(w.start.y-y)<7 and abs(w.end.y-y)<7 and
               min(w.start.x,w.end.x)<=left+14 and max(w.start.x,w.end.x)>=right-14
               for w in geometry.walls):continue
        suggestions.append(ExteriorRun(id=f'bottom-{len(suggestions)}',
            start=Pt(x=left,y=y),end=Pt(x=right,y=y),support=round(score,3)))
    # Return longest evidence-backed run; avoid multiple parallel wall layers.
    suggestions.sort(key=lambda item:(-(item.end.x-item.start.x),-item.support))
    return suggestions[:1]
