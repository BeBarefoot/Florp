"""Vectorize segmented wall pixels into structural axis runs.

Connected regions / directional morphology identify spans and local thickness.
Produces candidates in SOURCE pixel coordinates. Shapely planarization runs
afterwards; no floor/room is verified from a mask alone.
"""
from __future__ import annotations
import cv2
import numpy as np
from .wall_segmentation import MaskLine, WallMaskReport

def region_wall_lines(mask:np.ndarray,min_length:int=22)->WallMaskReport:
    if mask.ndim!=2 or mask.dtype!=np.uint8:raise ValueError('Expected uint8 2D wall mask')
    h,w=mask.shape
    if min(h,w)<16:raise ValueError('Mask too small')
    binary=np.where(mask>0,255,0).astype(np.uint8)
    coverage=float(np.count_nonzero(binary))/(w*h)
    if coverage>.65:raise ValueError('Wall mask covers most of image')
    if coverage==0:return WallMaskReport(coverage_fraction=0,line_count=0,lines=[])
    lines=[]
    # Directional erosion/opening preserves long wall features; contour bounding
    # boxes provide a stable region axis rather than many parallel Hough edges.
    run=max(8,min_length//2)
    for horizontal in (True,False):
        kernel=cv2.getStructuringElement(cv2.MORPH_RECT,(run,1) if horizontal else (1,run))
        opened=cv2.morphologyEx(binary,cv2.MORPH_OPEN,kernel)
        count,labels,stats,_=cv2.connectedComponentsWithStats(opened,8)
        for i in range(1,count):
            x,y,bw,bh,area=[int(v) for v in stats[i]]
            length=bw if horizontal else bh
            thickness=bh if horizontal else bw
            if length<min_length or thickness>max(22,length*.40):continue
            # Ask the ORIGINAL mask whether a candidate has continuous support.
            if horizontal:
                x1,y1,x2,y2=x,y+(bh-1)/2,x+bw-1,y+(bh-1)/2
            else:
                x1,y1,x2,y2=x+(bw-1)/2,y,x+(bw-1)/2,y+bh-1
            n=max(10,int(length/3))
            xs=np.clip(np.rint(np.linspace(x1,x2,n)).astype(int),0,w-1)
            ys=np.clip(np.rint(np.linspace(y1,y2,n)).astype(int),0,h-1)
            radius=max(2,min(6,int(thickness/2)+1))
            support=float(np.mean([bool(np.any(binary[max(0,yy-radius):min(h,yy+radius+1),
                                                         max(0,xx-radius):min(w,xx+radius+1)]))
                                  for xx,yy in zip(xs,ys)]))
            if support<.83:continue
            lines.append(MaskLine(x1=float(x1),y1=float(y1),x2=float(x2),y2=float(y2),
                                  support=round(support,3)))
    # Remove near-identical or mostly contained parallel runs, preserve
    # T-junctions and perpendicular crossing lines.
    lines.sort(key=lambda l:-np.hypot(l.x2-l.x1,l.y2-l.y1))
    unique=[]
    for l in lines:
        is_h=abs(l.x2-l.x1)>=abs(l.y2-l.y1)
        def duplicate(p):
            ph=abs(p.x2-p.x1)>=abs(p.y2-p.y1)
            if is_h!=ph:return False
            if is_h:
                if abs(l.y1-p.y1)>5:return False
                lo=max(min(l.x1,l.x2),min(p.x1,p.x2))
                hi=min(max(l.x1,l.x2),max(p.x1,p.x2))
                extent=min(abs(l.x2-l.x1),abs(p.x2-p.x1))
            else:
                if abs(l.x1-p.x1)>5:return False
                lo=max(min(l.y1,l.y2),min(p.y1,p.y2))
                hi=min(max(l.y1,l.y2),max(p.y1,p.y2))
                extent=min(abs(l.y2-l.y1),abs(p.y2-p.y1))
            return hi-lo>=extent*.75
        if not any(duplicate(p) for p in unique):unique.append(l)
    return WallMaskReport(source='directional_connected_mask_regions',
                          coverage_fraction=round(coverage,5),
                          line_count=len(unique),lines=unique,
                          warning='Connected mask spans are unverified; walls and junctions require review.')
