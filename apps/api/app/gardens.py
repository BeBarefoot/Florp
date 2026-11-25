from typing import Annotated, Literal

import cv2
import numpy as np
from shapely.geometry import Polygon, box
from shapely.ops import unary_union
from pydantic import BaseModel, Field, model_validator

Unit = Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]


class Region(BaseModel):
    holes: list[Annotated[list[tuple[Unit, Unit]], Field(min_length=3, max_length=256)]] = Field(default_factory=list, max_length=128)
    kind: Literal['garden', 'stairs']
    surface: Literal['paving'] | None = None
    points: list[tuple[Unit, Unit]] = Field(min_length=3, max_length=256)

    @model_validator(mode='after')
    def measurable(self):
        if self.surface and self.kind != "garden":
            raise ValueError("Only outdoor areas have an outdoor surface.")
        polygon = Polygon(self.points, self.holes)
        if not polygon.is_valid or polygon.area <= 0:
            raise ValueError('Trace a closed area without crossing its edges. Remove or redraw the marked outline.')
        return self


class Garden(Region):
    kind: Literal['garden'] = 'garden'


def _paved_areas(image, lawns):
    """Find broad warm fills that share edges with an established lawn."""
    h, w = image.shape[:2]
    hsv = cv2.cvtColor(cv2.medianBlur(image, 5), cv2.COLOR_BGR2HSV)
    warm = cv2.inRange(hsv, (4, 16, 110), (26, 150, 255))
    radius = max(2, round(min(h, w) / 45))
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2 * radius + 1, 2 * radius + 1))
    warm = cv2.morphologyEx(warm, cv2.MORPH_CLOSE, kernel)
    # Remove dimension strokes and other warm runs too narrow to be a surface.
    warm = cv2.morphologyEx(warm, cv2.MORPH_OPEN, kernel)
    contours, _ = cv2.findContours(warm, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    for contour in contours:
        x, y, width, height = cv2.boundingRect(contour)
        area = cv2.contourArea(contour)
        if min(width, height) < .12 * min(w, h) or area < .012 * w * h:
            continue
        if area < .72 * width * height:
            continue
        boundary = cv2.approxPolyDP(contour, 1.5 * radius, True)[:, 0]
        if not 4 <= len(boundary) <= 12:
            continue
        patio = Polygon(boundary)
        if not patio.is_valid or patio.area <= 0:
            continue
        # For near-rectangular paving, estimate the four edges from the middle
        # of each side. This prevents dimension ticks at corners from pulling
        # the patio into a neighboring wall or lawn.
        filled = np.zeros((height, width), dtype=np.uint8)
        cv2.drawContours(filled, [contour - [x, y]], -1, 1, cv2.FILLED)
        middle_rows = filled[height // 4 : 3 * height // 4]
        middle_cols = filled.T[width // 4 : 3 * width // 4]

        def median_edges(rows):
            rows = rows[rows.any(axis=1)]
            return np.median(rows.argmax(axis=1)), rows.shape[1] - 1 - np.median(rows[:, ::-1].argmax(axis=1))

        left, right = median_edges(middle_rows)
        top, bottom = median_edges(middle_cols)
        rectangle = box(x + left, y + top, x + right, y + bottom)
        if rectangle.intersection(patio).area >= .88 * rectangle.union(patio).area:
            patio = rectangle
        for lawn in lawns:
            edge = patio.boundary.intersection(lawn.buffer(2 * radius))
            # Match an inset or notch in the yard. Trim adjacent warm wall ink
            # outside that yard's extents.
            within_yard = patio.intersection(box(*lawn.bounds))
            if (edge.length >= .35 * patio.length and within_yard.area >= .85 * patio.area
                    and patio.intersection(lawn).area <= .2 * patio.area):
                yield within_yard
                break


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
    radius = max(1, round(min(h, w) / 120))
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2*radius+1, 2*radius+1))
    green = cv2.morphologyEx(green, cv2.MORPH_CLOSE, kernel)
    contours, hierarchy = cv2.findContours(green, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
    lawns = []
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
            lawns.append(shape)
    paving = list(_paved_areas(image, lawns)) if lawns else []
    paved_ground = unary_union(paving)
    regions = []
    for surfaces, surface in (([lawn.difference(paved_ground) for lawn in lawns], None), ([paved_ground], "paving")):
        for shape in surfaces:
            parts = shape.geoms if hasattr(shape, "geoms") else [shape]
            for part in parts:
                if part.geom_type != "Polygon" or part.area < .008 * w * h:
                    continue
                def normalized(ring):
                    return [(x/w,y/h) for x,y in list(ring.coords)[:-1]]
                points = normalized(part.exterior)
                holes = [normalized(ring) for ring in part.interiors]
                if len(points)<=256 and len(holes)<=128 and all(len(r)<=256 for r in holes):
                    region = {'kind':'garden','points':points,'holes':holes}
                    if surface:
                        region["surface"] = surface
                    regions.append(region)
    return regions[:12]
