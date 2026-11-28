"""Recover right-angle swings from faint neutral linework near structural walls."""

import math

import cv2
import numpy as np

from .ink_layers import _local_paper


def _samples(raster, points):
    x, y = np.moveaxis(np.rint(points).astype(np.int32), -1, 0)
    height, width = raster.shape
    return (
        (x >= 0) & (x < width) & (y >= 0) & (y < height)
        & raster[y.clip(0, height - 1), x.clip(0, width - 1)]
    )


def filter_soft_scan_swings(image, walls, items):
    """Separate architectural door swings from leaves and fixture arcs."""
    from shapely import STRtree
    from shapely.geometry import LineString, Point

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    paper = _local_paper(gray)
    fill = (gray >= 0.77 * paper) & (gray <= 0.92 * paper)
    lines = [LineString([(w.start.x, w.start.y), (w.end.x, w.end.y)]) for w in walls]
    index = STRtree(lines)
    removed = set()
    for item in items:
        if item.kind != "door" or not item.boundary_supported or item.leaf is None:
            continue
        start = np.array([item.start.x, item.start.y])
        end = np.array([item.end.x, item.end.y])
        width = math.dist(start, end)
        if width < 16:
            continue
        axis = (end - start) / width
        normal = np.array([-axis[1], axis[0]])
        depth = width * np.linspace(0.10, 0.36, 12)[:, None, None] * axis
        shoulder = width * np.linspace(-0.14, 0.14, 11)[None, :, None] * normal
        first = _samples(fill, start - depth + shoulder).mean()
        second = _samples(fill, end + depth + shoulder).mean()
        backed = min(first, second) >= 0.18
        if backed and min(abs(axis)) > 0.25:
            # Diagonal bathroom fixtures can have the same drawn arc as a
            # door. Require a structural run at each jamb, not a thin panel.
            reach = 0.37 * width
            for tip in (start, end):
                point = Point(tip)
                backed &= any(
                    walls[j].thickness_px >= 0.18 * width
                    and lines[j].length >= 0.70 * width
                    and lines[j].distance(point) <= reach
                    for j in index.query(point.buffer(reach))
                )
        if not backed:
            removed.update((item.id, item.host_id))
    return [item for item in items if item.id not in removed]


def swing_candidates(gray, walls):
    # Bound the sweep search on large scans. Geometry is returned in source
    # coordinates, and the gap-first detector still sees the full resolution.
    scale = min(1, 520 / max(gray.shape))
    if scale < 1:
        gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    gray = gray.astype(np.float32)
    paper = _local_paper(gray.astype(np.uint8)).astype(np.float32)
    local = cv2.GaussianBlur(gray, (0, 0), 2)
    strokes = (gray < local - 10) & (gray < 0.94 * paper)
    ink = cv2.dilate(strokes.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0
    clear = gray > 0.94 * paper
    fill = (gray >= 0.77 * paper) & (gray <= 0.92 * paper)
    anchors = np.zeros(gray.shape, np.uint8)
    # Tiny fixture strokes should not anchor a door. Paint only established
    # wall runs and use distance to them to limit the search around jambs.
    for wall in walls:
        start = np.array([wall.start.x, wall.start.y]) * scale
        end = np.array([wall.end.x, wall.end.y]) * scale
        if math.dist(start, end) >= max(32, 3 * wall.thickness_px * scale):
            cv2.line(anchors, tuple(np.rint(start).astype(int)), tuple(np.rint(end).astype(int)), 1)
            # A smudged band may end before its jamb in the vector pass.
            # Follow actual infill beyond the fitted tip to nearby returns.
            unit = (end - start) / math.dist(start, end)
            normal = np.array([-unit[1], unit[0]])
            reach = min(24, round(wall.thickness_px * scale * 3))
            for tip, outward in ((start, -unit), (end, unit)):
                if reach < 3:
                    continue
                positions = tip + np.arange(1, reach + 1)[:, None] * outward
                across = positions[:, None] + np.arange(-4, 5)[None, :, None] * normal
                supported = _samples(fill, across).sum(axis=1) >= 3
                # Stop at the first sustained loss of wall material.
                gaps = np.flatnonzero(
                    np.convolve((~supported).astype(int), np.ones(3, int), "valid") == 3
                )
                stop = gaps[0] if len(gaps) else reach
                if stop >= 3:
                    cv2.line(anchors, tuple(np.rint(tip).astype(int)), tuple(np.rint(positions[stop - 1]).astype(int)), 1)
    if not anchors.any():
        return []
    distance = cv2.distanceTransform(1 - anchors, cv2.DIST_L2, cv2.DIST_MASK_PRECISE)
    largest = min(64, round(0.12 * max(gray.shape)))
    points = np.argwhere(ink & (distance <= largest * 1.65))[:, ::-1]
    candidates = []
    angle = np.deg2rad(np.linspace(8, 84, 24))
    cos_angle, sin_angle = np.cos(angle)[:, None], np.sin(angle)[:, None]
    leaf_steps = np.linspace(0.15, 0.92, 18)[:, None]
    quick_steps = leaf_steps[1::4]
    # Drafted doors here typically open perpendicular to their closed span,
    # including the two diagonal directions common around a hall.
    for degrees in range(0, 360, 45):
        theta = math.radians(degrees)
        axis = np.array([math.cos(theta), math.sin(theta)])
        for sign in (-1, 1):
            leaf = sign * np.array([-axis[1], axis[0]])
            sweep = cos_angle * axis + sin_angle * leaf
            interior = np.array([
                0.25 * axis + 0.25 * leaf, 0.45 * axis + 0.25 * leaf,
                0.25 * axis + 0.45 * leaf, 0.56 * axis + 0.46 * leaf,
                0.45 * axis + 0.56 * leaf,
            ])
            shoulders = np.array([a * axis + b * leaf for a in (2, 4, 6, 8) for b in (-5, -3, -1, 1, 3, 5)])
            throat = np.linspace(0.24, 0.83, 5)[:, None] * axis
            for radius in range(max(16, round(0.047 * max(gray.shape))), largest + 1, 2):
                ends = points + radius * axis
                near_wall = distance <= 0.50 * radius
                anchored = _samples(near_wall, points) | _samples(near_wall, ends)
                starts = points[anchored]
                if not len(starts):
                    continue
                quick = _samples(ink, starts[:, None] + radius * quick_steps * leaf)
                starts = starts[quick.sum(axis=1) >= len(quick_steps) - 1]
                leaf_support = _samples(ink, starts[:, None] + radius * leaf_steps * leaf).mean(axis=1)
                starts = starts[leaf_support >= 0.88]
                if not len(starts):
                    continue
                origins = starts[:, None]
                clear_sweep = _samples(clear, origins + radius * interior).mean(axis=1) >= 0.8
                # Some plans draw the threshold across the closed span. Check
                # its paper clearance separately from the swing.
                throat_points = origins + radius * throat
                clear_throat = _samples(clear, throat_points).mean(axis=1) >= 0.6
                wall_core = distance <= 0.22 * radius
                clear_throat &= _samples(wall_core, throat_points).mean(axis=1) <= 0.6
                starts = starts[clear_sweep & clear_throat]
                if not len(starts):
                    continue
                origins = starts[:, None]
                hits = _samples(ink, origins + radius * sweep)
                continuous = hits.reshape(-1, 4, 6).mean(axis=2).min(axis=1) >= 0.83
                starts, hits = starts[continuous], hits[continuous]
                if not len(starts):
                    continue
                origins = starts[:, None]
                inner = _samples(ink, origins + (radius - 3) * sweep).mean(axis=1)
                outer = _samples(ink, origins + (radius + 3) * sweep).mean(axis=1)
                contrast = hits.mean(axis=1) - (inner + outer) / 2
                first, second = origins - shoulders, origins + radius * axis + shoulders
                first_fill = _samples(fill, first).mean(axis=1)
                second_fill = _samples(fill, second).mean(axis=1)
                valid = (contrast >= 0.62) & (first_fill >= 0.16) & (second_fill >= 0.16)
                valid &= (_samples(ink, first).mean(axis=1) >= 0.25) & (_samples(ink, second).mean(axis=1) >= 0.25)
                scores = hits.mean(axis=1) + 0.5 * contrast + 0.25 * (first_fill + second_fill)
                candidates.extend(
                    (float(score), start / scale, (start + radius * axis) / scale, leaf)
                    for score, start in zip(scores[valid], starts[valid])
                )
    return sorted(candidates, key=lambda candidate: candidate[0], reverse=True)
