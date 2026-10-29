from __future__ import annotations

import math
import cv2
import numpy as np
from shapely import make_valid
from shapely.geometry import Polygon, MultiPolygon, GeometryCollection
from shapely.ops import unary_union
from .preprocess import transform_points
from .schema import Options, ExtractionError


def polygons(geometry):
    if isinstance(geometry, Polygon):
        return [geometry] if not geometry.is_empty else []
    if isinstance(geometry, (MultiPolygon, GeometryCollection)):
        return [p for g in geometry.geoms for p in polygons(g)]
    return []


def polygonal(geometry):
    return unary_union(polygons(make_valid(geometry)))


def wall_masks(image, words, scale, transform, options: Options):
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
    red = cv2.inRange(
        hsv, (0, options.red_saturation_min, 40), (12, 255, 255)
    ) | cv2.inRange(hsv, (165, options.red_saturation_min, 40), (179, 255, 255))
    blue = cv2.inRange(hsv, (100, options.blue_saturation_min, 40), (135, 255, 255))
    # Lab opponent channels reject yellow/green and nearly neutral shadows.
    red[lab[:, :, 1] < 135] = 0
    # Faded red hatch evidence uses Lab chroma, but only near strong red seeds.
    # This cannot recover absent color in monochrome photocopies.
    weak_red = cv2.inRange(hsv, (0, 12, 40), (18, 255, 255)) | cv2.inRange(
        hsv, (165, 12, 40), (179, 255, 255)
    )
    weak_red[lab[:, :, 1] < 131] = 0
    near_seed = cv2.dilate(red, np.ones((7, 7), np.uint8))
    red |= weak_red & near_seed
    blue[lab[:, :, 2] > 125] = 0
    roi = np.full(image.shape[:2], 255, np.uint8)
    if options.architecture_roi:
        pts = transform_points(options.architecture_roi, transform)
        if (
            not Polygon(pts).is_valid
            or Polygon(pts).area < 1
            or np.any(pts < 0)
            or np.any(pts[:, 0] > image.shape[1] - 1)
            or np.any(pts[:, 1] > image.shape[0] - 1)
        ):
            raise ExtractionError(
                "invalid_roi",
                "Architecture ROI must be a simple polygon inside the rectified document",
            )
        roi[:] = 0
        cv2.fillPoly(roi, [np.rint(pts).astype(np.int32)], 255)
    red &= roi
    blue &= roi
    # Protect strong straight wall evidence when an OCR box crosses a wall.
    # Erasing an entire text rectangle would cut real walls at overlapping text.
    text = np.zeros_like(red)
    for word in words:
        x1, y1, x2, y2 = (int(round(v)) for v in word["box"])
        text[max(0, y1) : y2 + 1, max(0, x1) : x2 + 1] = 255
    protected = []
    cleaned = []
    for mask in (red, blue):
        length = max(15, min(101, int(round(35 * scale))))
        straight = cv2.morphologyEx(
            mask, cv2.MORPH_OPEN, np.ones((1, length), np.uint8)
        ) | cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((length, 1), np.uint8))
        erase = (text > 0) & (straight == 0)
        mask = mask.copy()
        mask[erase] = 0
        # Kernel capped in physical space so low-resolution doors are not closed
        # by a fixed 7px x two-iteration close. No repeat closing expansion.
        size = min(options.close_kernel_px, max(1, int(math.floor(6 * scale))))
        if size % 2 == 0:
            size -= 1
        kernel = np.ones((size, size), np.uint8)
        fused = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
        thickness = max(2, int(math.ceil(options.min_thickness_cm * scale)))
        # Axis openings are *unioned*, never intersected/sequentially applied.
        horizontal = cv2.morphologyEx(fused, cv2.MORPH_OPEN, np.ones((1, 15), np.uint8))
        vertical = cv2.morphologyEx(fused, cv2.MORPH_OPEN, np.ones((15, 1), np.uint8))
        support = horizontal | vertical
        count, labels, stats, _ = cv2.connectedComponentsWithStats(fused, 8)
        keep = np.zeros(count, dtype=np.uint8)
        min_area = max(4, options.min_component_cm2 * scale * scale)
        distance = cv2.distanceTransform(fused, cv2.DIST_L2, 3)
        maxima = np.zeros(count)
        np.maximum.at(maxima, labels.ravel(), distance.ravel())
        supported = np.bincount(
            labels.ravel(), weights=(support > 0).ravel(), minlength=count
        )
        for i in range(1, count):
            area = stats[i, cv2.CC_STAT_AREA]
            # Preserve thick diagonal structure even without Manhattan support.
            width, height = stats[i, cv2.CC_STAT_WIDTH], stats[i, cv2.CC_STAT_HEIGHT]
            elongated = max(width, height) / max(1, min(width, height)) >= 2.4
            dense = area / (width * height) >= 0.6
            if (
                area >= min_area
                and maxima[i] * 2 >= thickness
                and (elongated or dense or supported[i] >= area * 0.65)
                and (supported[i] >= area * 0.25 or maxima[i] * 2 >= 2 * thickness)
            ):
                keep[i] = 255
        cleaned.append(keep[labels])
        protected.append(int(np.count_nonzero((text > 0) & (straight > 0))))
    return *cleaned, {
        "ocr_overlap_protected_pixels": sum(protected),
        "morphological_kernel_px": size,
        "noise_min_area_working_px2": min_area,
    }


def contours_to_polygons(mask):
    contours, hierarchy = cv2.findContours(
        mask, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE
    )
    if hierarchy is None:
        return GeometryCollection()
    if sum(len(c) for c in contours) > 200000 or len(contours) > 20000:
        raise ExtractionError(
            "geometry_too_complex",
            "Mask has excessive contours; crop to architecture or improve color thresholds",
        )
    result = []
    links = hierarchy[0]
    for i, cnt in enumerate(contours):
        if links[i, 3] != -1 or len(cnt) < 3:
            continue
        holes = []
        child = int(links[i, 2])
        while child != -1:
            if len(contours[child]) >= 3:
                holes.append(contours[child].reshape(-1, 2))
            child = int(links[child, 0])
        poly = Polygon(cnt.reshape(-1, 2), holes)
        result.extend(polygons(make_valid(poly)))
    return unary_union(result)


def snap_ring(coords, tolerance_deg, max_displacement):
    """Solve shared x/y constraints simultaneously, including closing edge.

    Unlike a sequential integer assignment, this preserves closure and doesn't
    silently undo a previous edge constraint. Reject excessive movement later.
    """
    pts = np.asarray(coords, dtype=float)[:-1]
    n = len(pts)
    if n < 3:
        return coords
    parents = [list(range(n)), list(range(n))]

    def find(p, x):
        while p[x] != x:
            p[x] = p[p[x]]
            x = p[x]
        return x

    def join(axis, a, b):
        p = parents[axis]
        p[find(p, a)] = find(p, b)

    for i in range(n):
        j = (i + 1) % n
        dx, dy = pts[j] - pts[i]
        angle = abs(math.degrees(math.atan2(dy, dx))) % 180
        if min(angle, 180 - angle) <= tolerance_deg:
            join(1, i, j)
        elif abs(angle - 90) <= tolerance_deg:
            join(0, i, j)
    out = pts.copy()
    for axis in range(2):
        groups = {}
        for i in range(n):
            groups.setdefault(find(parents[axis], i), []).append(i)
        for members in groups.values():
            out[members, axis] = np.mean(pts[members, axis])
    if np.max(np.linalg.norm(out - pts, axis=1)) > max_displacement:
        return coords
    return np.vstack([out, out[0]])


def clean_geometry(mask, scale, options: Options):
    raw = contours_to_polygons(mask)
    epsilon = options.simplify_cm * scale
    result = []
    rejected = 0
    for poly in polygons(raw):
        simplified = poly.simplify(epsilon, preserve_topology=True)
        snapped = Polygon(
            snap_ring(simplified.exterior.coords, options.snap_degrees, epsilon),
            [
                snap_ring(r.coords, options.snap_degrees, epsilon)
                for r in simplified.interiors
            ],
        )
        # Never "repair" a bad snap with buffer(0), which can remove holes/parts.
        if (
            snapped.is_valid
            and len(snapped.interiors) == len(simplified.interiors)
            and snapped.hausdorff_distance(poly) <= epsilon + 1e-6
            and abs(snapped.area - simplified.area) <= max(1, simplified.area * 0.1)
        ):
            result.append(snapped)
        else:
            result.append(simplified)
            rejected += 1
    return unary_union(result), rejected


def classify(red, blue, shape, scale, options: Options):
    combined = unary_union([red, blue])
    if combined.is_empty:
        raise ExtractionError(
            "no_wall_evidence",
            "No supported red/blue wall footprints. Grayscale/faded plans require a different extractor or adjusted color thresholds",
        )
    # Perimeter inference is deliberately separate from the exported wall mask.
    occupancy = np.zeros(shape, np.uint8)
    for poly in polygons(combined):
        layer = np.zeros(shape, np.uint8)
        cv2.fillPoly(layer, [np.rint(poly.exterior.coords).astype(np.int32)], 255)
        for hole in poly.interiors:
            cv2.fillPoly(layer, [np.rint(hole.coords).astype(np.int32)], 0)
        occupancy |= layer
    gap = min(511, min(shape) - 1, max(1, int(round(options.envelope_gap_cm * scale))))
    if gap % 2 == 0:
        gap += 1
    # Pad so morphology never uses the image edge as an invented wall.
    pad = gap + 2
    padded = cv2.copyMakeBorder(
        occupancy, pad, pad, pad, pad, cv2.BORDER_CONSTANT, value=0
    )
    closed = cv2.morphologyEx(
        padded, cv2.MORPH_CLOSE, np.ones((1, gap), np.uint8)
    ) | cv2.morphologyEx(padded, cv2.MORPH_CLOSE, np.ones((gap, 1), np.uint8))
    inferred = contours_to_polygons(closed)
    from shapely.affinity import translate

    candidates = [
        translate(Polygon(p.exterior), xoff=-pad, yoff=-pad)
        for p in polygons(inferred)
        if p.interiors
    ]
    envelope = unary_union(candidates)
    # Must contain essentially all structural evidence, not just one room.
    valid = not envelope.is_empty and combined.difference(
        envelope.buffer(2)
    ).area <= max(10, combined.area * 0.01)
    if not valid:
        if options.mode == "outer_walls":
            raise ExtractionError(
                "exterior_ambiguous",
                "No reliable enclosing perimeter; outer-only output would invent an outline. Supply a complete uncropped plan/architecture ROI",
            )
        return {
            "LAYER_WALLS_EXTERIOR": GeometryCollection(),
            "LAYER_WALLS_INTERIOR": GeometryCollection(),
            "LAYER_MAMAD_CONCRETE": blue,
            "LAYER_WALLS_UNCLASSIFIED": red,
        }, {
            "status": "unresolved",
            "warning": "exterior_ambiguous: block walls exported as unclassified; no convex hull or boundary invented",
        }
    band = envelope.boundary.buffer(options.exterior_band_cm * scale, join_style=2)
    exterior = polygonal(red.intersection(band))
    interior = polygonal(red.difference(exterior))
    selected_blue = (
        polygonal(blue.intersection(band)) if options.mode == "outer_walls" else blue
    )
    return {
        "LAYER_WALLS_EXTERIOR": exterior,
        "LAYER_WALLS_INTERIOR": interior
        if options.mode == "all_walls"
        else GeometryCollection(),
        "LAYER_MAMAD_CONCRETE": selected_blue,
    }, {
        "status": "inferred_verify",
        "classification_bridge_max_cm": options.envelope_gap_cm,
        "warning": "Exterior labels use a provisional closed-envelope band; inferred bridges are never exported as walls",
    }
