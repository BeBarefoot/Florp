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
    image_support: float = Field(ge=0,le=1)
    axis: str = 'horizontal'
    kind: str = 'exterior_wall_candidate'

def _extend_on_supported_ink(horizontal:np.ndarray, y:float, left:float,
                             right:float, max_gap:int=5)->tuple[float,float]:
    """Grow a Hough fragment only within its connected source-ink run.

    HoughLinesP may report a fragment of a continuous wall. Horizontal
    morphology has already removed short isolated marks; a one-dimensional
    closing fills only tiny breaks and never invents a door-sized span.
    """
    height,width=horizontal.shape
    center=int(round(y))
    row=np.any(horizontal[max(0,center-2):min(height,center+3)]>0,axis=0)
    kernel=np.ones(max_gap,dtype=np.uint8)
    continuous=cv2.morphologyEx(row.astype(np.uint8)[None,:],
                                cv2.MORPH_CLOSE,kernel)[0]>0
    labels_count,labels,stats,_=cv2.connectedComponentsWithStats(
        continuous.astype(np.uint8)[None,:],connectivity=8)
    best=(left,right)
    overlap_max=0.
    for index in range(1,labels_count):
        x=int(stats[index,cv2.CC_STAT_LEFT])
        span=int(stats[index,cv2.CC_STAT_WIDTH])
        lo,hi=float(x),float(x+span-1)
        overlap=max(0.,min(right,hi)-max(left,lo))
        if overlap>overlap_max and overlap>=min(20.,(right-left)*.35):
            overlap_max=overlap
            best=(lo,hi)
    return best

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
        left,right=_extend_on_supported_ink(horizontal,y,left,right)
        if right-left<length:continue
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
            start=Pt(x=left,y=y),end=Pt(x=right,y=y),image_support=round(score,3)))
    # Return longest evidence-backed run; avoid multiple parallel wall layers.
    suggestions.sort(key=lambda item:(-(item.end.x-item.start.x),-item.image_support))
    return suggestions[:1]
