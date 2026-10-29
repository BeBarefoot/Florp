"""Local wall-mask segmentation adapter and conservative mask-to-centerline proposal.

A segmentation-capable checkpoint is REQUIRED. The existing YOLO detection
checkpoint does not provide masks. No rectangles are substituted as wall masks.
"""
from __future__ import annotations
from pathlib import Path
import cv2
import numpy as np
from pydantic import BaseModel, Field
from .geometry import Geometry, Wall, Pt
from .pretrained_detector import DetectorUnavailable, _load_model
from .config import settings

class MaskLine(BaseModel):
    x1: float
    y1: float
    x2: float
    y2: float
    support: float = Field(ge=0,le=1)

class WallMaskReport(BaseModel):
    source: str='local_wall_segmentation'
    coverage_fraction: float
    line_count: int
    lines: list[MaskLine]
    warning: str='These are proposed centerlines from a pretrained mask, not verified wall geometry.'

def mask_centerlines(mask: np.ndarray, min_length: int=24) -> WallMaskReport:
    if mask.ndim!=2 or mask.dtype!=np.uint8:
        raise ValueError('Wall mask must be a two-dimensional uint8 array')
    h,w=mask.shape
    if w<16 or h<16:raise ValueError('Wall mask too small')
    binary=(mask>0).astype('uint8')*255
    coverage=float(np.count_nonzero(binary))/(h*w)
    if coverage==0:return WallMaskReport(coverage_fraction=0,line_count=0,lines=[])
    if coverage>.65:raise ValueError('Wall mask covers most of the drawing; wrong class or incompatible checkpoint')
    # Erode gently to center strong wall regions and reduce thick double edges.
    kernel=cv2.getStructuringElement(cv2.MORPH_CROSS,(3,3))
    core=cv2.erode(binary,kernel,iterations=1)
    if not np.any(core):core=binary
    # OpenCV's Hough transform yields (N,1,4) or (N,4).
    raw=cv2.HoughLinesP(core,1,np.pi/180,threshold=max(12,min_length//2),
                        minLineLength=min_length,maxLineGap=5)
    if raw is None:raw=np.empty((0,4),dtype=np.int32)
    lines=[]
    for x1,y1,x2,y2 in np.asarray(raw).reshape(-1,4):
        dx=int(x2-x1);dy=int(y2-y1)
        length=float(np.hypot(dx,dy))
        if length<min_length:continue
        # Prefer near-axis components; diagonals are not silently straightened.
        if min(abs(dx),abs(dy))>max(abs(dx),abs(dy))*.16:continue
        samples=np.linspace(0,1,max(8,int(length/4)))
        xs=np.clip(np.rint(x1+samples*dx).astype(int),0,w-1)
        ys=np.clip(np.rint(y1+samples*dy).astype(int),0,h-1)
        support=float(np.mean(binary[ys,xs]>0))
        if support<.8:continue
        line=MaskLine(x1=float(x1),y1=float(y1),x2=float(x2),y2=float(y2),support=round(support,3))
        if any(_equivalent(line,existing) for existing in lines):continue
        lines.append(line)
    # Long morphological runs recover contiguous thick/thin interior wall
    # regions that probabilistic Hough may miss. They are still proposals.
    # Generate only from actual mask pixels, never from PDF line annotations.
    run_length=max(12,min_length//2)
    for axis,kernel in (
        ('horizontal',cv2.getStructuringElement(cv2.MORPH_RECT,(run_length,1))),
        ('vertical',cv2.getStructuringElement(cv2.MORPH_RECT,(1,run_length)))):
        retained=cv2.morphologyEx(binary,cv2.MORPH_OPEN,kernel)
        contours,_=cv2.findContours(retained,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
        for contour in contours:
            x,y,bw,bh=cv2.boundingRect(contour)
            length=bw if axis=='horizontal' else bh
            if length<min_length:continue
            if axis=='horizontal':
                x1,y1,x2,y2=x,y+bh//2,x+bw-1,y+bh//2
            else:
                x1,y1,x2,y2=x+bw//2,y,x+bw//2,y+bh-1
            count=max(8,int(length/3))
            xs=np.clip(np.rint(np.linspace(x1,x2,count)).astype(int),0,w-1)
            ys=np.clip(np.rint(np.linspace(y1,y2,count)).astype(int),0,h-1)
            # Center can be blank in ring-shaped masks; nearby wall pixels still
            # count as evidence, but not unrelated distant drawing content.
            support=float(np.mean([
                np.any(binary[max(0,yy-2):min(h,yy+3),max(0,xx-2):min(w,xx+3)])
                for xx,yy in zip(xs,ys)
            ]))
            if support<.8:continue
            proposed=MaskLine(x1=float(x1),y1=float(y1),x2=float(x2),y2=float(y2),support=round(support,3))
            if any(_equivalent(proposed,existing) or _overlap(proposed,existing) for existing in lines):
                continue
            lines.append(proposed)
    return WallMaskReport(coverage_fraction=round(coverage,5),
        line_count=len(lines),lines=lines)

def _overlap(a:MaskLine,b:MaskLine)->bool:
    ah=abs(a.x2-a.x1)>=abs(a.y2-a.y1)
    bh=abs(b.x2-b.x1)>=abs(b.y2-b.y1)
    if ah!=bh:return False
    if ah:
        if abs((a.y1+a.y2-b.y1-b.y2)/2)>5:return False
        length=min(a.x2,b.x2)-max(a.x1,b.x1)
        shorter=min(abs(a.x2-a.x1),abs(b.x2-b.x1))
    else:
        if abs((a.x1+a.x2-b.x1-b.x2)/2)>5:return False
        length=min(a.y2,b.y2)-max(a.y1,b.y1)
        shorter=min(abs(a.y2-a.y1),abs(b.y2-b.y1))
    return length>0 and length>=shorter*.75

def _equivalent(a:MaskLine,b:MaskLine)->bool:
    return ((np.hypot(a.x1-b.x1,a.y1-b.y1)<7 and np.hypot(a.x2-b.x2,a.y2-b.y2)<7)
        or (np.hypot(a.x1-b.x2,a.y1-b.y2)<7 and np.hypot(a.x2-b.x1,a.y2-b.y1)<7))

def infer_wall_mask(preview:Path,width:int,height:int)->tuple[np.ndarray,str]:
    configured=settings.wall_segmentation_weights.strip()
    if not configured:
        raise DetectorUnavailable('WALL_SEGMENTATION_WEIGHTS is not configured. Provide a trusted wall-segmentation YOLO checkpoint; the current detection best.pt produces boxes only.')
    path=Path(configured).expanduser().resolve()
    if not path.is_file():
        raise DetectorUnavailable('Wall segmentation weights do not exist at the configured path.')
    try:
        model=_load_model(str(path))
        results=model.predict(source=str(preview),device='cpu',verbose=False,conf=.3,retina_masks=True)
    except Exception as exc:
        raise DetectorUnavailable('Wall-mask inference failed: '+type(exc).__name__) from exc
    if not results or results[0].masks is None:
        raise DetectorUnavailable('Checkpoint returned bounding boxes but no instance masks. Use a segmentation checkpoint with a wall class.')
    result=results[0]
    if tuple(result.orig_shape)!=(height,width):
        raise DetectorUnavailable('Segmentation result does not match the source raster dimensions.')
    names=result.names
    masks=result.masks.data.cpu().numpy()
    if masks.ndim!=3 or masks.shape[1:]!=(height,width):
        raise DetectorUnavailable('Segmentation masks are not in source coordinates; refusing to stretch padded masks.')
    if result.boxes is None or len(masks)!=len(result.boxes):
        raise DetectorUnavailable('Segmentation mask/object count mismatch.')
    if not np.isfinite(masks).all() or np.any((masks<0)|(masks>1)):
        raise DetectorUnavailable('Segmentation masks contain invalid values.')
    merged=np.zeros((height,width),dtype=np.uint8)
    wall_count=0
    for i,b in enumerate(result.boxes):
        cls=int(b.cls.item())
        label=str(names.get(cls,cls) if isinstance(names,dict) else names[cls]).lower()
        if label not in ('wall','walls'):continue
        candidate=masks[i]
        merged[candidate>.5]=255
        wall_count+=1
    if not wall_count:
        raise DetectorUnavailable('Segmentation checkpoint produced no wall-class masks.')
    return merged,str(path.name)

def propose_mask_walls(base:Geometry, report:WallMaskReport)->Geometry:
    result=base.model_copy(deep=True)
    result.walls=[Wall(id='mask-'+str(i),start=Pt(x=l.x1,y=l.y1),
                       end=Pt(x=l.x2,y=l.y2),inferred=True)
                  for i,l in enumerate(report.lines)]
    result.rooms=[]
    # Existing openings depend on old wall identities; never silently reassign.
    result.openings=[]
    result.structure_reviewed=False
    result.warnings=list(dict.fromkeys(result.warnings+
        ['Experimental segmentation proposal. Previously confirmed wall edits were not transferred.',
         'Review mask centerlines and restore opening associations before verifying.']))
    return result
