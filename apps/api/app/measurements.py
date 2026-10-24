"""Conservative dimensional hypotheses, not verified measurement recognition.

An OCR numeric label (typically centimeters) is paired with nearby near-axis line
evidence. Dimension lines often include extension marks, so these are hypotheses
requiring explicit confirmation. Never silently set px_per_meter.
"""
from __future__ import annotations
import re
from math import hypot
from pydantic import BaseModel, Field

class ScaleSuggestion(BaseModel):
    text: str
    source: str
    confidence: float = Field(ge=0,le=1)
    dimension_m: float
    pixels: float
    px_per_meter: float
    line: dict

def scale_suggestions(segments, labels, width:int, height:int)->list[ScaleSuggestion]:
    out=[]
    for label in labels:
        value=label.text.strip().replace(',','.')
        if not re.fullmatch(r'\d{2,4}(?:\.\d)?',value):continue
        num=float(value)
        # Centimeter values in architectural dimension chains; other units need explicit support.
        if not 70<=num<=2500:continue
        meters=num/100
        cx=(label.bbox[0]+label.bbox[2])/2
        cy=(label.bbox[1]+label.bbox[3])/2
        ranked=[]
        for seg in segments:
            dx=seg.x2-seg.x1;dy=seg.y2-seg.y1
            length=hypot(dx,dy)
            if length<max(30,min(width,height)*.045):continue
            horiz=abs(dy)<length*.035
            vert=abs(dx)<length*.035
            if not (horiz or vert):continue
            # Same dimension string may sit above or beside its graphic. Search nearby,
            # not on top of the label (text can obscure the actual line).
            d=abs((seg.y1+seg.y2)/2-cy) if horiz else abs((seg.x1+seg.x2)/2-cx)
            along=abs((seg.x1+seg.x2)/2-cx) if horiz else abs((seg.y1+seg.y2)/2-cy)
            if d>max(42,min(width,height)*.065) or along>length*.55:continue
            ppm=length/meters
            if not 5<=ppm<=2000:continue
            ranked.append((d+along*.2,seg,length,ppm))
        if not ranked:continue
        ranked.sort(key=lambda t:t[0])
        _,seg,length,ppm=ranked[0]
        out.append(ScaleSuggestion(text=value,source=label.source,confidence=.3 if label.source=='tesseract' else .42,
            dimension_m=meters,pixels=round(length,2),px_per_meter=round(ppm,4),
            line={'x1':seg.x1,'y1':seg.y1,'x2':seg.x2,'y2':seg.y2}))
    # Avoid overwhelming the user with dozens of candidates.
    out.sort(key=lambda s:(-s.confidence,-s.pixels))
    unique=[]
    for item in out:
        if any(abs(item.px_per_meter-other.px_per_meter)/other.px_per_meter<.025 for other in unique):continue
        unique.append(item)
        if len(unique)==8:break
    return unique
