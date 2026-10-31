"""Find the main building footprint so site context (terraces, gardens, neighbours) is ignored."""

from __future__ import annotations
import cv2
import numpy as np


def _polygon(mask: np.ndarray, eps: float):
    cs, _ = cv2.findContours(mask.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not cs:
        return None
    c = max(cs, key=cv2.contourArea)
    approx = cv2.approxPolyDP(c, eps, True).reshape(-1, 2)
    return [(float(x), float(y)) for x, y in approx] if len(approx) >= 3 else None


def building_envelope(strips: np.ndarray, w_wall: float):
    """Return ``(polygon | None, mask)`` for the largest closed building region.

    ``strips`` is the wall-strip mask. It is closed with a kernel about the size of
    the widest opening (a garage door, ~20 wall thicknesses), the largest filled region wins, and it is grown by two
    wall thicknesses. A region that encloses no room-sized hole is not a building.
    """
    h, w = strips.shape
    full = np.ones((h, w), np.uint8)
    if not strips.any():
        return None, full.astype(bool)
    k = int(max(5, min(20 * w_wall, min(h, w) / 4)))
    k += (k + 1) % 2
    closed = cv2.morphologyEx((strips > 0).astype(np.uint8), cv2.MORPH_CLOSE, np.ones((k, k), np.uint8))
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
    if best is None:
        return None, full.astype(bool)
    g = int(max(3, 2 * w_wall))
    grown = cv2.dilate(best, np.ones((2 * g + 1, 2 * g + 1), np.uint8))
    return _polygon(grown, max(2.0, w_wall)), grown.astype(bool)


def mask_from_polygon(polygon, shape) -> np.ndarray:
    m = np.zeros(shape[:2], np.uint8)
    cv2.fillPoly(m, [np.rint(np.asarray(polygon)).astype(np.int32)], 1)
    return m.astype(bool)
