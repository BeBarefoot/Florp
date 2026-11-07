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


def contextual_hits(hits, model):
    """Conservatively reject structural/site clutter; retain candidates for review."""
    from shapely.geometry import Polygon, LineString, box, Point
    from shapely.ops import unary_union
    mpp = model.scale.meters_per_pixel
    if not mpp:
        return []
    nodes = {n.id:n for n in model.nodes}
    walls = [LineString([(nodes[w.a].x,nodes[w.a].y),(nodes[w.b].x,nodes[w.b].y)])
             .buffer(w.thickness_px/2, cap_style=2) for w in model.walls]
    stairs = [Polygon([(p.x,p.y) for p in tread]) for stair in model.stairs for tread in stair.treads]
    obstacles = unary_union([*walls,*stairs])
    outline = Polygon([(p.x,p.y) for p in model.envelope]) if model.envelope else None
    kept = []
    for hit in sorted(hits,key=lambda h:-h.score):
        if outline is not None and not outline.covers(Point(hit.x,hit.y)):
            continue
        bounds = box(hit.x-hit.width/mpp/2,hit.y-hit.depth/mpp/2,
                     hit.x+hit.width/mpp/2,hit.y+hit.depth/mpp/2)
        if bounds.area <= 0 or bounds.intersection(obstacles).area > .25*bounds.area:
            continue
        if any(hit.kind==other.kind and bounds.intersection(old).area /
               bounds.union(old).area > .5 for other,old in kept):
            continue
        kept.append((hit,bounds))
    return [hit for hit,_ in kept]
