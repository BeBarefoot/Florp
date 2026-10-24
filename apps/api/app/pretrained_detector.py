"""Optional local pretrained detector; boxes are never treated as verified walls.

Model: sanatladkat/floor-plan-object-detection/best.pt
Runtime: Ultralytics YOLOv8 (AGPL-3.0 / commercial licensing may apply).
Only load checkpoint from a trusted local path. PyTorch checkpoints may execute
arbitrary code during deserialization. Do not accept uploaded model weights.
"""
from __future__ import annotations
from functools import lru_cache
from pathlib import Path
from pydantic import BaseModel, Field
from .config import settings

class DetectorUnavailable(RuntimeError): pass

class DetectionBox(BaseModel):
    category: str
    confidence: float = Field(ge=0, le=1)
    x1: float
    y1: float
    x2: float
    y2: float

class DetectorResult(BaseModel):
    provider: str = 'sanatladkat/yolov8'
    output_type: str = 'object_bounding_boxes'
    image_width: int
    image_height: int
    boxes: list[DetectionBox]
    warning: str = 'Object boxes are not wall centerlines or verified architectural geometry.'

@lru_cache(maxsize=2)
def _load_model(weights_path: str):
    try:
        from ultralytics import YOLO
    except ImportError as exc:
        raise DetectorUnavailable('Local detector requires optional Ultralytics dependencies: cd apps/api && uv sync --extra pretrained-yolo. Review AGPL licensing before enabling.') from exc
    return YOLO(weights_path)

def normalize_yolo_boxes(results, width:int, height:int, threshold:float=.35) -> list[DetectionBox]:
    """Pure adapter from Ultralytics result objects; independently unit-testable."""
    normalized=[]
    for result in results:
        names=result.names
        if result.boxes is None:continue
        for box in result.boxes:
            conf=float(box.conf.item())
            if conf<threshold:continue
            raw=box.xyxy[0].tolist()
            cls=int(box.cls.item())
            category=str(names.get(cls,cls) if isinstance(names,dict) else names[cls]).strip().lower()
            x1,y1,x2,y2=float(raw[0]),float(raw[1]),float(raw[2]),float(raw[3])
            x1=max(0.,min(float(width),x1))
            x2=max(0.,min(float(width),x2))
            y1=max(0.,min(float(height),y1))
            y2=max(0.,min(float(height),y2))
            if x2<=x1 or y2<=y1:continue
            normalized.append(DetectionBox(category=category,confidence=conf,x1=x1,y1=y1,x2=x2,y2=y2))
    return normalized

def detect_objects(preview_path:Path, width:int, height:int, confidence:float=.35)->DetectorResult:
    if not settings.pretrained_yolo_weights:
        raise DetectorUnavailable('PRETRAINED_YOLO_WEIGHTS is empty. Download the reviewed upstream best.pt to a local path and configure it in apps/api/.env.')
    weights=Path(settings.pretrained_yolo_weights).expanduser().resolve()
    if not weights.is_file():
        raise DetectorUnavailable('Configured pretrained YOLO weights file does not exist: '+str(weights))
    # Image is not uploaded anywhere; only local CPU/GPU inference.
    model=_load_model(str(weights))
    try:
        results=model.predict(source=str(preview_path),conf=confidence,verbose=False,device='cpu')
    except Exception as exc:
        raise DetectorUnavailable('Local YOLO inference failed ('+type(exc).__name__+'). Confirm checkpoint compatibility with the installed Ultralytics version.') from exc
    return DetectorResult(image_width=width,image_height=height,
                          boxes=normalize_yolo_boxes(results,width,height,confidence))
