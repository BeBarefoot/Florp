"""Find the main building footprint so site context (terraces, gardens, neighbours) is ignored."""

from __future__ import annotations
import cv2
import numpy as np
from shapely.geometry import Polygon


def validate_polygon(polygon, shape):
    h, w = shape[:2]
    points = np.asarray(polygon, dtype=float)
    if points.ndim != 2 or points.shape[1] != 2 or not 3 <= len(points) <= 64:
        raise ValueError("Building outline needs 3–64 corners")
    if (
        not np.isfinite(points).all()
        or not (
            (points[:, 0] >= 0)
            & (points[:, 0] <= w)
            & (points[:, 1] >= 0)
            & (points[:, 1] <= h)
        ).all()
    ):
        raise ValueError("Building outline must stay inside the source image")
    geometry = Polygon(points)
    if not geometry.is_valid or geometry.area < 4:
        raise ValueError(
            "Building outline must be a non-crossing polygon with positive area"
        )


def _polygon(mask: np.ndarray, eps: float):
    cs, _ = cv2.findContours(
        mask.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
    )
    if not cs:
        return None
    c = max(cs, key=cv2.contourArea)
    approx = cv2.approxPolyDP(c, eps, True).reshape(-1, 2)
    while len(approx) > 64:
        eps *= 1.5
        approx = cv2.approxPolyDP(c, eps, True).reshape(-1, 2)
    return [(float(x), float(y)) for x, y in approx] if len(approx) >= 3 else None


def _dominant_bounds(strips, w_wall):
    """Conservative crop from repeated long bands and attached side walls.

    Short isolated posts or numeric strokes cannot establish the crop. Side
    walls may extend past the long roof/floor bands (for example beside a row
    of windows); keep them when they have longitudinal and junction support.
    """
    h, w = strips.shape
    binary = (strips > 0).astype(np.uint8)
    size = max(3, round(w_wall))
    core = cv2.morphologyEx(binary, cv2.MORPH_OPEN, np.ones((size, size), np.uint8))
    minimum = max(20, 3 * w_wall)
    seed_length = max(minimum, 0.08 * w)
    rows = []
    for y, row in enumerate(core):
        edges = np.diff(np.r_[False, row > 0, False].astype(np.int8))
        intervals = [
            (int(a), int(b))
            for a, b in zip(np.flatnonzero(edges == 1), np.flatnonzero(edges == -1))
            if b - a >= minimum
        ]
        seeds = [(a, b) for a, b in intervals if b - a >= seed_length]
        if seeds and sum(b - a for a, b in intervals) >= 0.18 * w:
            rows.append((y, seeds))
    if not rows or rows[-1][0] - rows[0][0] < max(6 * w_wall, 0.15 * h):
        return None
    groups = 1 + sum(b[0] - a[0] > max(2, w_wall) for a, b in zip(rows, rows[1:]))
    if groups < 2:
        return None
    x1 = min(a for _, intervals in rows for a, b in intervals)
    x2 = max(b for _, intervals in rows for a, b in intervals)
    y1, y2 = rows[0][0], rows[-1][0]
    if (x2 - x1) * (y2 - y1) < 0.05 * h * w:
        return None
    horizontal = cv2.morphologyEx(
        binary, cv2.MORPH_OPEN, np.ones((1, int(minimum)), np.uint8)
    )
    reach = max(10 * w_wall, 0.05 * w)
    left, right = max(0, int(x1 - reach)), min(w, int(x2 + reach) + 1)
    for x in range(left, right):
        values = binary[y1 : y2 + 1, x] > 0
        edges = np.diff(np.r_[False, values, False].astype(np.int8))
        support = sum(
            b - a
            for a, b in zip(np.flatnonzero(edges == 1), np.flatnonzero(edges == -1))
            if b - a >= 3 * w_wall
        )
        if support >= 0.18 * (y2 - y1) and horizontal[y1 : y2 + 1, x].any():
            x1 = min(x1, x)
            x2 = max(x2, x)
    pad = max(4, 2 * w_wall)
    return (
        max(0, round(x1 - pad)),
        max(0, round(y1 - pad)),
        min(w - 1, round(x2 + pad)),
        min(h - 1, round(y2 + pad)),
    )


def building_envelope(strips: np.ndarray, w_wall: float):
    """Return ``(polygon | None, mask)`` for the largest closed building region.

    ``strips`` is the wall-strip mask. It is closed with a kernel about the size of
    the widest opening (a garage door, ~20 wall thicknesses), the largest filled region wins, and it is grown by two
    wall thicknesses. Open layouts can instead use repeated orthogonal band support.
    """
    h, w = strips.shape
    full = np.ones((h, w), np.uint8)
    if not strips.any():
        return None, full.astype(bool)
    k = int(max(5, min(20 * w_wall, min(h, w) / 4)))
    k += (k + 1) % 2
    closed = cv2.morphologyEx(
        (strips > 0).astype(np.uint8), cv2.MORPH_CLOSE, np.ones((k, k), np.uint8)
    )
    n, labels, st, _ = cv2.connectedComponentsWithStats(closed, connectivity=8)
    best, best_area = None, 0
    min_hole = (6 * w_wall) ** 2
    for i in range(1, n):
        comp = (labels == i).astype(np.uint8)
        cs, hier = cv2.findContours(comp, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
        outer = max((c for c, hh in zip(cs, hier[0]) if hh[3] < 0), key=cv2.contourArea)
        filled = np.zeros_like(comp)
        cv2.drawContours(filled, [outer], -1, 1, -1)
        holes = int(filled.sum() - comp.sum())
        area = int(filled.sum())
        if holes < min_hole:
            continue
        if area > best_area:
            best, best_area = filled, area
    bounds = _dominant_bounds(strips, w_wall)
    if bounds is not None:
        x1, y1, x2, y2 = bounds
        region = np.zeros((h, w), bool)
        region[y1 : y2 + 1, x1 : x2 + 1] = True
        # Site leaders can attach to the closed component. Constrain the crop
        # by the repeated architectural bands, rather than accepting their tips.
        if best is None:
            return [(x1, y1), (x2, y1), (x2, y2), (x1, y2)], region
        occupied = np.argwhere(best > 0)
        by1, bx1 = occupied.min(axis=0)
        by2, bx2 = occupied.max(axis=0)
        if bx1 < x1 or bx2 > x2 or by1 < y1 or by2 > y2:
            return [(x1, y1), (x2, y1), (x2, y2), (x1, y2)], region
    if best is None:
        return None, full.astype(bool)
    g = int(max(3, 2 * w_wall))
    grown = cv2.dilate(best, np.ones((2 * g + 1, 2 * g + 1), np.uint8))
    return _polygon(grown, max(2.0, w_wall)), grown.astype(bool)


def mask_from_polygon(polygon, shape) -> np.ndarray:
    validate_polygon(polygon, shape)
    m = np.zeros(shape[:2], np.uint8)
    cv2.fillPoly(m, [np.rint(np.asarray(polygon)).astype(np.int32)], 1)
    return m.astype(bool)
