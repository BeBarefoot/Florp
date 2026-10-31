"""Local, boundary-supported wall bands for coloured architectural photographs.

Colour proposes a material; it does not establish a wall. Each red band needs
two drawn dark boundaries, tint between them, and lighter paper outside. Work
on individual supported intervals rather than accepting/rejecting a connected
component (which may contain both walls and touching dimension annotations).
Coordinates remain in the original image. No completion across blank spans.
"""

from dataclasses import dataclass
import math

import cv2
import numpy as np


@dataclass(frozen=True)
class Boundary:
    lo: int
    hi: int
    slope: float
    intercept: float

    def at(self, along):
        return self.slope * along + self.intercept


def _sample(raster, along, across, horizontal):
    """Nearest source pixels, without wrapping negative indices at the page edge."""
    along, across = np.broadcast_arrays(along, across)
    x, y = (along, across) if horizontal else (across, along)
    x, y = np.rint(x).astype(int), np.rint(y).astype(int)
    h, w = raster.shape
    inside = (x >= 0) & (x < w) & (y >= 0) & (y < h)
    return raster[y.clip(0, h - 1), x.clip(0, w - 1)], inside


def _smooth(values, size):
    # Edge padding avoids artificial unsupported gaps at the end of a wall.
    radius = size // 2
    return np.convolve(np.pad(values, radius, mode="edge"), np.ones(size) / size, "valid")


def bounded_red_bands(gray, paper, red, delta, wall_width):
    """Return wall bands, boundary separations, and unsupported red bar pixels.

    Hough supplies *boundary proposals*, not wall centrelines. Test the actual
    sloping profiles on both sides of every candidate. Red dimension bars have
    no darker enclosing outlines; room/furniture lines have no red interior.
    Large garden fills fail the outside-paper/tint comparison.
    """
    h, w = gray.shape
    relative = np.clip(gray.astype(np.float32) / np.maximum(paper, 1), 0, 1)
    normalized = np.rint(relative * 255).astype(np.uint8)
    edges = cv2.Canny(normalized, 25, 65)
    minimum = max(8, round(0.006 * max(h, w)))
    raw = cv2.HoughLinesP(
        edges, 1, np.pi / 360,
        threshold=max(6, minimum // 2), minLineLength=minimum, maxLineGap=2,
    )
    result = np.zeros((h, w), np.uint8)
    annotations = np.zeros((h, w), np.uint8)
    widths = []
    if raw is None:
        return result.astype(bool), widths, annotations.astype(bool)
    groups = {True: [], False: []}
    slope_limit = math.tan(math.radians(4))
    for x1, y1, x2, y2 in np.asarray(raw).reshape(-1, 4):
        dx, dy = x2 - x1, y2 - y1
        if abs(dx) >= minimum and abs(dy) <= max(1, abs(dx) * slope_limit):
            horizontal = True
            a, b, c, d = int(x1), int(x2), int(y1), int(y2)
        elif abs(dy) >= minimum and abs(dx) <= max(1, abs(dy) * slope_limit):
            horizontal = False
            a, b, c, d = int(y1), int(y2), int(x1), int(x2)
        else:
            continue
        slope = (d - c) / (b - a)
        groups[horizontal].append(Boundary(min(a, b), max(a, b), slope, c - slope * a))

    # Thickness is only an upper bound for pairing, not an opening kernel that
    # erases thin partitions. Both 3px partitions and thicker exterior bands
    # can coexist in the same photograph.
    maximum = max(6.0, min(2 * wall_width + 4, 0.065 * min(h, w)))
    for horizontal, proposals in groups.items():
        # Prefer long evidence if the image has many text/furniture edges.
        proposals = sorted(set(proposals), key=lambda p: (-(p.hi - p.lo), p.lo, p.intercept, p.slope))[:1000]
        for i, first in enumerate(proposals):
            for second in proposals[i + 1:]:
                lo, hi = max(first.lo, second.lo), min(first.hi, second.hi)
                if hi - lo < minimum:
                    continue
                d0, d1 = second.at(lo) - first.at(lo), second.at(hi) - first.at(hi)
                if d0 < 0 and d1 < 0:
                    lower, upper = second, first
                    d0, d1 = -d0, -d1
                elif d0 > 0 and d1 > 0:
                    lower, upper = first, second
                else:
                    continue
                if min(d0, d1) < 2.5 or max(d0, d1) > maximum:
                    continue
                if abs(d0 - d1) > max(2, 0.1 * (d0 + d1)):
                    continue  # crossing furniture edges, not parallel wall faces
                along = np.arange(lo, hi + 1)
                a, b = lower.at(along), upper.at(along)
                thickness = b - a
                middle = a[None, :] + thickness[None, :] * np.array([0.3, 0.5, 0.7])[:, None]
                interior, _ = _sample(relative, along, middle, horizontal)
                tint, _ = _sample(delta, along, middle, horizontal)
                coloured, _ = _sample(red, along, middle, horizontal)
                # Canny may mark either side of an outline stroke. Locate its
                # dark core within one pixel rather than requiring a fixed row.
                edge_a, _ = _sample(relative, along, a + np.array([-1, 0, 1])[:, None], horizontal)
                edge_b, _ = _sample(relative, along, b + np.array([-1, 0, 1])[:, None], horizontal)
                outside = np.stack((a - 3, b + 3))
                exterior, valid = _sample(relative, along, outside, horizontal)
                outside_tint, _ = _sample(delta, along, outside, horizontal)
                outside_count = np.maximum(1, valid.sum(axis=0))
                outside_tint = (outside_tint * valid).sum(axis=0) / outside_count
                edge_a, edge_b = edge_a.min(axis=0), edge_b.min(axis=0)
                centre = interior.max(axis=0)
                # Solid red labels/bars are as dark inside as at their edges.
                # Hatched/filled walls are enclosed by darker outline strokes.
                bounded = (
                    (edge_a < centre - 0.025) & (edge_b < centre - 0.025)
                    & (edge_a < 0.94) & (edge_b < 0.94)
                )
                size = min(7, max(3, round(float(np.median(thickness))) | 1))
                # Explicit negative evidence for solid red dimension strokes:
                # the centre and both edges have the same darkness. Absence
                # of a recovered wall alone is never grounds for deletion.
                bar = (
                    (_smooth(coloured.mean(axis=0), size) >= 0.8)
                    & (_smooth(tint.mean(axis=0) - outside_tint, size) >= 3)
                    & (_smooth(np.abs(edge_a - centre), size) < 0.02)
                    & (_smooth(np.abs(edge_b - centre), size) < 0.02)
                    & valid.any(axis=0)
                )
                changes = np.diff(np.r_[False, bar, False].astype(np.int8))
                for start, end in zip(np.flatnonzero(changes == 1), np.flatnonzero(changes == -1)):
                    if end - start < max(10, 3 * float(np.median(thickness[start:end]))):
                        continue
                    u, v = start, end - 1
                    points = np.array([
                        [along[u], a[u]], [along[v], a[v]],
                        [along[v], b[v]], [along[u], b[u]],
                    ])
                    if not horizontal:
                        points = points[:, ::-1]
                    cv2.fillConvexPoly(annotations, np.rint(points).astype(np.int32), 1)
                support = (
                    (_smooth(bounded.astype(float), size) >= 0.55)
                    & (_smooth(coloured.mean(axis=0), size) >= 0.12)
                    & (_smooth(tint.mean(axis=0), size) >= 1.0)
                    & (_smooth(tint.mean(axis=0) - outside_tint, size) >= 0.5)
                    & (_smooth(((exterior > np.stack((edge_a, edge_b)) + 0.02) & valid).sum(axis=0) / outside_count, size) >= 0.65)
                    & valid.any(axis=0)
                )
                # Smoothing assesses hatch texture; it must not extend a run
                # into an actual colourless window/door span at its ends.
                changes = np.diff(np.r_[False, support, False].astype(np.int8))
                for start, end in zip(np.flatnonzero(changes == 1), np.flatnonzero(changes == -1)):
                    local = np.flatnonzero(coloured[:, start:end].any(axis=0))
                    if not local.size:
                        continue
                    stop = start + int(local[-1]) + 1
                    start += int(local[0])
                    end = stop
                    width = float(np.median(thickness[start:end]))
                    if end - start < max(5, 1.25 * width):
                        continue
                    u, v = start, end - 1
                    points = np.array([
                        [along[u], a[u]], [along[v], a[v]],
                        [along[v], b[v]], [along[u], b[u]],
                    ])
                    if not horizontal:
                        points = points[:, ::-1]
                    cv2.fillConvexPoly(result, np.rint(points).astype(np.int32), 1)
                    widths.append(width)
    return result > 0, widths, (annotations > 0) & (result == 0)
