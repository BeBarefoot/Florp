"""Optional local YOLO floor-plan symbol weights; predictions require review."""
from functools import lru_cache
from pathlib import Path
import math
import numpy as np
from .fixture_detection import Hit

CLASSES = {"bed": "bed", "wardrobe": "wardrobe", "toilet": "toilet",
           "bath_tub": "bathtub", "bathtub": "bathtub", "sink": "vanity",
           "washbasin": "vanity", "shower": "shower"}

@lru_cache(maxsize=1)
def load(path, stamp):
    from ultralytics import YOLO
    return YOLO(path, task="detect")

def detect(gray, mpp, weights):
    path = Path(weights).expanduser().resolve()
    if not path.is_file() or path.suffix.lower() != ".pt":
        raise ValueError("Fixture weights must name a trusted local .pt checkpoint.")
    model = load(str(path), path.stat().st_mtime_ns)
    results = model.predict(source=np.repeat(gray[:, :, None], 3, axis=2), device="cpu",
                            conf=.35, iou=.45, imgsz=1280, max_det=100, verbose=False)
    hits = []
    h, w = gray.shape
    for result in results:
        if result.boxes is None:
            continue
        for box, score, cls in zip(result.boxes.xyxy.cpu().tolist(),
                                   result.boxes.conf.cpu().tolist(), result.boxes.cls.cpu().tolist()):
            kind = CLASSES.get(str(result.names.get(int(cls), "")).lower().replace(" ", "_"))
            if kind is None or not all(math.isfinite(v) for v in [*box, score]):
                continue
            x1, y1, x2, y2 = box
            if not (0 <= x1 < x2 <= w and 0 <= y1 < y2 <= h):
                continue
            width, depth = (x2-x1)*mpp, (y2-y1)*mpp
            if not (.05 < width <= 8 and .05 < depth <= 8):
                continue
            # Boxes provide no front/back orientation evidence. Review rotation.
            hits.append(Hit(kind, score, (x1+x2)/2, (y1+y2)/2, width, depth, 0))
    return hits
