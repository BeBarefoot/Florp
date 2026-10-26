"""Reversible image padding for floor-plan inference (never changes stored preview)."""
from __future__ import annotations
from dataclasses import dataclass
import numpy as np

@dataclass(frozen=True)
class InputFrame:
    width:int
    height:int
    left:int
    top:int
    right:int
    bottom:int

def add_inference_border(rgb:np.ndarray, fraction:float=.10, min_px:int=24,
                         max_px:int=256)->tuple[np.ndarray,InputFrame]:
    if rgb.ndim!=3 or rgb.shape[2]!=3 or rgb.dtype!=np.uint8:
        raise ValueError('Expected RGB uint8 image')
    if not 0<=fraction<=.4 or min_px<0 or max_px<min_px:
        raise ValueError('Invalid border parameters')
    h,w=rgb.shape[:2]
    pad=max(min_px,min(max_px,round(min(h,w)*fraction)))
    # Top and bottom are symmetrical: avoid encoding false building direction.
    frame=InputFrame(w,h,pad,pad,pad,pad)
    canvas=np.pad(rgb,((pad,pad),(pad,pad),(0,0)),
                  mode='constant',constant_values=255)
    return canvas,frame

def unpad_probabilities(probabilities:np.ndarray,frame:InputFrame)->np.ndarray:
    end_y=frame.top+frame.height
    end_x=frame.left+frame.width
    if probabilities.shape[0]<end_y or probabilities.shape[1]<end_x:
        raise ValueError('Predicted mask smaller than original content')
    return probabilities[frame.top:end_y,frame.left:end_x].copy()

def translate_box(box:tuple[float,float,float,float],frame:InputFrame):
    x1,y1,x2,y2=box
    x1=max(0.,min(frame.width,float(x1)-frame.left))
    y1=max(0.,min(frame.height,float(y1)-frame.top))
    x2=max(0.,min(frame.width,float(x2)-frame.left))
    y2=max(0.,min(frame.height,float(y2)-frame.top))
    return (x1,y1,x2,y2)
