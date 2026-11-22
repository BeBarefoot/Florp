from typing import Annotated, Literal

import cv2
import numpy as np
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
    # Detect pale green relative to the paper's own colour cast.
    b,g,r = cv2.split(cv2.medianBlur(image, 3).astype(np.int16))
    paper = hsv[:,:,2] >= np.percentile(hsv[:,:,2], 60)
    gb, gr = g-b, g-r
    pale = ((gb >= np.median(gb[paper])+5) & (gr >= np.median(gr[paper])+1)
            & (hsv[:,:,0] >= 30) & (hsv[:,:,0] <= 85) & (hsv[:,:,2] >= 90))
    green |= pale.astype(np.uint8)*255
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
        rings = []
        child = hierarchy[0,i,2]
        while child >= 0:
            hole = contours[child]
            if len(hole) >= 3 and cv2.contourArea(hole) >= .0005*w*h:
                rings.append(hole[:,0])
            child = hierarchy[0,child,0]
        # Joint simplification keeps a patio hole inside the lawn outline.
        area = Polygon(contour[:,0], rings)
        if not area.is_valid:
            area = area.buffer(0)
        parts = area.geoms if area.geom_type == "MultiPolygon" else [area]
        for part in parts:
            if part.area < .008*w*h or part.area > .85*w*h:
                continue
            shape = part.simplify(max(1., part.exterior.length*.003), preserve_topology=True)
            def normalized(ring):
                return [(x/w,y/h) for x,y in list(ring.coords)[:-1]]
            points = normalized(shape.exterior)
            holes = [normalized(ring) for ring in shape.interiors]
            if len(points)<=256 and len(holes)<=128 and all(len(r)<=256 for r in holes):
                regions.append({'kind':'garden','points':points,'holes':holes})
    return regions[:12]
