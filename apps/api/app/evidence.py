"""Deterministic, inspectable evidence. Never claims room topology from line detection."""
from __future__ import annotations
import io, re, shutil
from pathlib import Path
from typing import Literal
import cv2
import fitz
import numpy as np
from PIL import Image
from pydantic import BaseModel, Field
from .wall_candidates import WallCandidate, wall_candidates
from .measurements import ScaleSuggestion, scale_suggestions

class Segment(BaseModel):
    x1: float
    y1: float
    x2: float
    y2: float
    source: Literal['pdf_vector', 'raster_hough']
    confidence: float = Field(ge=0, le=1)

class TextEvidence(BaseModel):
    text: str
    bbox: list[float]
    source: Literal['pdf_text', 'tesseract']
    confidence: float = Field(ge=0, le=1)

class Evidence(BaseModel):
    width: int
    height: int
    segments: list[Segment] = Field(default_factory=list)
    labels: list[TextEvidence] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    vector_pdf: bool = False
    ocr_available: bool = False
    candidates: list[WallCandidate] = Field(default_factory=list)
    scale_suggestions: list[ScaleSuggestion] = Field(default_factory=list)

def _segments(image: Image.Image) -> list[Segment]:
    rgb = np.asarray(image.convert('RGB'))
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    h, w = gray.shape
    scale = min(1.0, 1700.0 / max(w, h))
    if scale < 1:
        gray = cv2.resize(gray, (max(1,int(w*scale)),max(1,int(h*scale))),interpolation=cv2.INTER_AREA)
    gray = cv2.GaussianBlur(gray,(3,3),0)
    edges = cv2.Canny(gray, 60, 165)
    lines = cv2.HoughLinesP(edges, 1, np.pi/180, threshold=65,
                           minLineLength=max(25,int(min(gray.shape)*0.045)),
                           maxLineGap=max(6,int(min(gray.shape)*0.012)))
    out=[]
    if lines is None: return out
    inv=1/scale
    for item in lines[:,0][:1200]:
        x1,y1,x2,y2=[float(v)*inv for v in item]
        length=((x2-x1)**2+(y2-y1)**2)**0.5
        if length<min(w,h)*.035: continue
        out.append(Segment(x1=x1,y1=y1,x2=x2,y2=y2,source='raster_hough',
                           confidence=min(.8,.35+length/max(w,h)*.6)))
    return out

def _pdf_data(path: Path, image_width: int, image_height: int):
    doc=fitz.open(path)
    try:
        page=doc[0]
        sx=image_width/page.rect.width
        sy=image_height/page.rect.height
        lines=[]
        for drawing in page.get_drawings():
            for item in drawing.get('items',[]):
                if item[0]=='l':
                    a,b=item[1],item[2]
                    lines.append(Segment(x1=a.x*sx,y1=a.y*sy,x2=b.x*sx,y2=b.y*sy,
                                         source='pdf_vector',confidence=.94))
                elif item[0]=='re':
                    rect=item[1]
                    corners=[(rect.x0,rect.y0),(rect.x1,rect.y0),(rect.x1,rect.y1),(rect.x0,rect.y1)]
                    for j in range(4):
                        a,b=corners[j],corners[(j+1)%4]
                        lines.append(Segment(x1=a[0]*sx,y1=a[1]*sy,x2=b[0]*sx,y2=b[1]*sy,
                                             source='pdf_vector',confidence=.9))
                if len(lines)>=1200:break
            if len(lines)>=1200:break
        texts=[]
        for word in page.get_text('words'):
            x0,y0,x1,y1,value,*_=word
            if str(value).strip():
                texts.append(TextEvidence(text=str(value),bbox=[x0*sx,y0*sy,x1*sx,y1*sy],
                                          source='pdf_text',confidence=.97))
            if len(texts)>=500:break
        return lines,texts
    finally:doc.close()

def inspect_plan(original: Path, preview: Path) -> Evidence:
    with Image.open(preview) as source:
        image=source.convert('RGB')
    result=Evidence(width=image.width,height=image.height,ocr_available=bool(shutil.which('tesseract')))
    if original.suffix.lower()=='.pdf':
        try:
            lines, labels=_pdf_data(original,image.width,image.height)
            result.segments.extend(lines);result.labels.extend(labels)
            result.vector_pdf=bool(lines)
        except Exception as exc:
            result.warnings.append('Could not inspect PDF drawing objects: '+type(exc).__name__)
    if not result.vector_pdf:
        result.segments.extend(_segments(image))
    if not result.labels and result.ocr_available:
        try:
            import pytesseract
            # Word-level OCR for labels/dimensions; no automatic metric calibration.
            output=pytesseract.image_to_data(image,output_type=pytesseract.Output.DICT,config='--psm 11')
            for i,word in enumerate(output['text']):
                if not word.strip():continue
                confidence=float(output['conf'][i])
                if confidence<40:continue
                x,y,w,h=[int(output[k][i]) for k in ('left','top','width','height')]
                result.labels.append(TextEvidence(text=word,bbox=[x,y,x+w,y+h],
                                                  source='tesseract',confidence=min(1,confidence/100)))
                if len(result.labels)>=500:break
        except (ImportError,RuntimeError):
            result.warnings.append('OCR skipped; install pytesseract and Tesseract for local OCR')
    if not result.ocr_available:
        result.warnings.append('Tesseract not installed: raster OCR unavailable; vector PDF text still works')
    result.candidates = wall_candidates(result.segments, result.labels, result.width, result.height)
    result.scale_suggestions = scale_suggestions(result.segments, result.labels, result.width, result.height)
    result.warnings.append('Wall candidates are heuristic paired-lines; manually accept only actual walls')
    result.warnings.append('Lines and text are evidence only, not verified walls, rooms or scale')
    return result
