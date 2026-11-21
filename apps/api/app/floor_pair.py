"""Review two plan images in their own normalized coordinate systems."""
import re
from pathlib import Path
from typing import Annotated, Literal

import cv2
import numpy as np
from PIL import Image
from pydantic import BaseModel, Field, model_validator

from .stair_detection import detect_stairs

Unit = Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]


class Region(BaseModel):
    holes: list[Annotated[list[tuple[Unit, Unit]], Field(min_length=3, max_length=256)]] = Field(default_factory=list, max_length=128)
    kind: Literal['garden', 'stairs']
    points: list[tuple[Unit, Unit]] = Field(min_length=3, max_length=256)


class Pair(BaseModel):
    first: str
    second: str
    regions: dict[str, Annotated[list[Region], Field(max_length=100)]] = Field(default_factory=dict)

    @model_validator(mode='after')
    def distinct(self):
        if self.first == self.second or set(self.regions) != {self.first, self.second}:
            raise ValueError('Choose two distinct plans and mark regions on those plans.')
        return self


def name_level(filename):
    name = re.sub(r'[_\-.]+', ' ', Path(filename).stem.casefold())
    first = re.search(r'\b(ground|first|1st|floor\s*1|level\s*1|קומת קרקע|קרקע)\b', name)
    second = re.search(r'\b(upper|second|2nd|floor\s*2|level\s*2|קומה שנייה)\b', name)
    return 1 if first and not second else 2 if second and not first else None


def inspect_floor(bp):
    with Image.open(bp.preview_path) as src:
        src.thumbnail((1400, 1400))
        image = cv2.cvtColor(np.asarray(src.convert('RGB')), cv2.COLOR_RGB2BGR)
    h, w = image.shape[:2]
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    green = cv2.inRange(hsv, (31, 18, 45), (90, 255, 255))
    contours, hierarchy = cv2.findContours(green, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
    regions = []
    outer = [i for i in range(len(contours)) if hierarchy[0,i,3] < 0]
    for i in sorted(outer, key=lambda i:cv2.contourArea(contours[i]), reverse=True)[:12]:
        contour = contours[i]
        x, y, cw, ch = cv2.boundingRect(contour)
        margin = min(x/w, y/h, (w-x-cw)/w, (h-y-ch)/h)
        if margin > .2 or cv2.contourArea(contour) < .008*w*h:
            continue
        poly = cv2.approxPolyDP(contour, max(1., cv2.arcLength(contour, True)*.004), True)
        if 3 <= len(poly) <= 256:
            holes = []
            child = hierarchy[0,i,2]
            while child >= 0:
                inside = contours[child]
                if cv2.contourArea(inside) >= .0005*w*h:
                    ring = cv2.approxPolyDP(inside, max(1., cv2.arcLength(inside, True)*.004), True)
                    if 3 <= len(ring) <= 256:
                        holes.append([(float(a)/w,float(b)/h) for a,b in ring[:,0]])
                child = hierarchy[0,child,0]
            if len(holes) > 128:
                continue
            regions.append({'kind':'garden','holes':holes,'points':[(float(a)/w,float(b)/h) for a,b in poly[:,0]]})
    for stair in detect_stairs(image):
        mask = np.zeros((h,w), np.uint8)
        for tread in stair.treads:
            cv2.fillPoly(mask,[np.rint([(p.x,p.y) for p in tread]).astype(np.int32)],255)
        outlines, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for outline in outlines:
            poly = cv2.approxPolyDP(outline, 1.5, True)
            if 3 <= len(poly) <= 256:
                regions.append({'kind':'stairs','points':[(float(a)/w,float(b)/h) for a,b in poly[:,0]]})
    return regions


def suggest(a, b):
    regions = {bp.id:inspect_floor(bp) for bp in (a,b)}
    levels = [name_level(bp.filename) for bp in (a,b)]
    first = None
    reason = 'Choose which drawing shows the first floor.'
    if levels[0] != levels[1] and any(levels):
        first = a if levels[0] == 1 or levels[1] == 2 else b
        reason = 'Floor order suggested from the filenames. Check both drawings.'
    elif levels == [None,None]:
        gardens = [any(r['kind']=='garden' for r in regions[bp.id]) for bp in (a,b)]
        if gardens[0] != gardens[1]:
            first = a if gardens[0] else b
            reason = 'Possible first floor based on garden shading. Confirm the level.'
    return {'first':first.id if first else None,'regions':regions,'reason':reason}
