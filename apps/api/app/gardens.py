from typing import Annotated, Literal

import cv2
from shapely.geometry import Polygon
from pydantic import BaseModel, Field, model_validator

Unit = Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]


class Region(BaseModel):
    holes: list[Annotated[list[tuple[Unit, Unit]], Field(min_length=3, max_length=256)]] = Field(default_factory=list, max_length=128)
    kind: Literal['garden', 'stairs']
    points: list[tuple[Unit, Unit]] = Field(min_length=3, max_length=256)

    @model_validator(mode='after')
    def measurable(self):
        polygon = Polygon(self.points, self.holes)
        if not polygon.is_valid or polygon.area <= 0:
            raise ValueError('Trace a closed area without crossing its edges. Remove or redraw the marked outline.')
        return self


class Garden(Region):
    kind: Literal['garden'] = 'garden'


def detect_gardens(image):
    h, w = image.shape[:2]
    factor = min(1., 1400/max(h,w))
    if factor < 1:
        image = cv2.resize(image, None, fx=factor, fy=factor, interpolation=cv2.INTER_AREA)
    h, w = image.shape[:2]
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    green = cv2.inRange(hsv, (31, 18, 45), (90, 255, 255))
    # Bridge narrow dimension lines crossing a continuous patch of lawn.
    radius = max(1, round(min(h, w) / 450))
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2*radius+1, 2*radius+1))
    green = cv2.morphologyEx(green, cv2.MORPH_CLOSE, kernel)
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
            if not Polygon(poly[:,0], [[(x*w,y*h) for x,y in ring] for ring in holes]).is_valid:
                continue
            regions.append({'kind':'garden','holes':holes,'points':[(float(a)/w,float(b)/h) for a,b in poly[:,0]]})
    return regions
