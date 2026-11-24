"""Recover faint masonry only where it reconnects an existing room boundary."""

import math

import cv2
import numpy as np
from shapely import STRtree
from shapely.geometry import LineString, Point, Polygon
from shapely.ops import polygonize, unary_union

from .ink_layers import _local_paper
from .structural_runs import structural_runs


def _fill_support(fill, line, width, *, narrow=False):
    start, end = np.array(line.coords)
    step = (end - start) / line.length
    normal = np.array([-step[1], step[0]])
    centers = start + np.linspace(0.12, 0.88, min(512, max(5, round(line.length))))[:, None] * (end - start)
    offsets = np.arange(-math.ceil(width / 2), math.ceil(width / 2) + 1)
    x, y = np.rint(centers[:, None] + offsets[None, :, None] * normal).astype(int).transpose(2, 0, 1)
    height, width = fill.shape
    valid = (x >= 0) & (x < width) & (y >= 0) & (y < height)
    rows = valid & fill[y.clip(0, height - 1), x.clip(0, width - 1)]
    core = rows[:, 1:] & rows[:, :-1]
    return np.mean(np.any(core if narrow else core[:, 1:] & core[:, :-1], axis=1))


def _line_parts(geometry):
    if geometry.geom_type == "LineString":
        return [geometry]
    return [part for part in getattr(geometry, "geoms", ()) if part.geom_type == "LineString"]


def _bands(fill, originals, thickness):
    # Shorter kernels recover returns and interior partitions discarded by
    # the primary wall pass. Topology and source support gate their use below.
    minimum = max(10, min(32, round(1.2 * thickness)))
    across = max(3, min(8, round(thickness * 0.32)))
    raster = fill.astype(np.uint8)
    horizontal = cv2.morphologyEx(raster, cv2.MORPH_OPEN, np.ones((across, minimum), np.uint8))
    vertical = cv2.morphologyEx(raster, cv2.MORPH_OPEN, np.ones((minimum, across), np.uint8))
    index = STRtree(originals)
    for run in structural_runs(horizontal | vertical, min_length=minimum):
        if not max(4, 0.38 * thickness) <= run.thickness_px <= thickness * 2.4:
            continue
        start, end = (run.start.x, run.start.y), (run.end.x, run.end.y)
        line = LineString([start, end])
        if line.length < max(15, 2.7 * run.thickness_px):
            continue
        axis = 0 if start[1] == end[1] else 1
        cross = 1 - axis
        parallel = []
        for j in index.query(line.buffer(thickness * 0.65)):
            a, b = originals[j].coords
            distance = abs(a[cross] - start[cross])
            overlap = min(end[axis], max(a[axis], b[axis])) - max(start[axis], min(a[axis], b[axis]))
            if a[cross] == b[cross] and distance <= thickness * 0.65 and overlap >= 3:
                parallel.append((overlap, a[cross], originals[j]))
        if parallel:
            lane = max(parallel, key=lambda item: item[0])[1]
            coords = [list(start), list(end)]
            coords[0][cross] = coords[1][cross] = lane
            line = LineString(coords)
            remainder = line.difference(unary_union([item[2] for item in parallel if item[1] == lane]))
            parts = _line_parts(remainder)
        else:
            parts = [line]
        for part in parts:
            if part.length >= minimum and _fill_support(fill, part, run.thickness_px) >= 0.85:
                yield part, run.thickness_px


def _junctions(fill, lines, widths, thickness, apertures):
    index = STRtree(lines)
    holes = STRtree(apertures)
    for i, line in enumerate(lines):
        ends = np.array(line.coords)
        for tip, far in (ends, ends[::-1]):
            anchor = Point(tip)
            reach = min(22, max(7, 1.8 * thickness))
            nearby = index.query(anchor.buffer(reach))
            if any(j != i and lines[j].distance(anchor) < 1e-5 for j in nearby):
                continue
            choices = []
            for j in nearby:
                if i == j:
                    continue
                space = lines[j].distance(anchor)
                if space > reach:
                    continue
                dist = lines[j].project(anchor)
                for offset in (0, -3, 3, -6, 6):
                    target = np.array(lines[j].interpolate(float(np.clip(dist + offset, 0, lines[j].length))).coords[0])
                    if np.dot(target - tip, tip - far) < -1:
                        continue
                    bridge = LineString([tip, target])
                    if bridge.length > reach or bridge.length < 1e-4:
                        continue
                    body = LineString([bridge.interpolate(d, normalized=True) for d in (0.12, 0.88)])
                    if any(body.intersection(apertures[k].buffer(0.35)).length > 0.45
                           for k in holes.query(body.buffer(0.35))):
                        continue
                    width = min(widths[i], widths[j], thickness)
                    support = _fill_support(fill, bridge, width, narrow=True)
                    if support >= 0.8:
                        choices.append((bridge.length, -support, int(j), bridge, width))
            if choices:
                *_, bridge, width = min(choices, key=lambda item: item[:3])
                yield bridge, width


def recover_partitions(image, runs, openings, thickness, envelope):
    if not runs:
        return []
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    saturation = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)[:, :, 1]
    paper = _local_paper(gray)
    fill = (gray >= 105) & (gray <= paper * 0.94) & (saturation < 22)
    originals = [LineString([run.a, run.b]) for run in runs]
    boundary = Polygon([(p.x, p.y) for p in envelope]) if envelope else None
    apertures = [
        LineString([(o.start.x, o.start.y), (o.end.x, o.end.y)]) for o in openings
    ]
    bands = list(_bands(fill, originals, thickness))
    lines = originals + [line for line, _ in bands]
    widths = [r.t for r in runs] + [width for _, width in bands]
    proposals = bands + list(_junctions(fill, lines, widths, thickness, apertures))
    # Don't create a new junction through an aperture. A branch there
    # would split its host and leave part of the opening without a wall.
    protected = STRtree([
        LineString([hole.interpolate(gap) for gap in (3, hole.length - 3)]).buffer(1.5)
        for hole in apertures if hole.length > 6
    ])
    proposals = [
        (line, width) for line, width in proposals
        if (boundary is None or boundary.covers(line))
        and not len(protected.query(line, predicate="intersects"))
    ]
    original = unary_union(originals)
    inferred = unary_union([line for line, _ in proposals])
    # Add only spans contributing to an enclosed face shared with the
    # existing plan. Stray drafting strokes and open chains are discarded.
    faces = [
        face.boundary for face in polygonize(unary_union([original, inferred]))
        if face.area >= max(400, 12 * thickness**2)
        and face.boundary.intersection(original).length >= 0.35 * face.length
    ]
    if not faces:
        return []
    enclosing = unary_union(faces).difference(original)
    result = []
    used = original
    for line, width in proposals:
        # A recovered band can extend past a corner. Keep just the part
        # bounding a room and avoid emitting a second copy of any joint.
        parts = line.intersection(enclosing).difference(used)
        for part in _line_parts(parts):
            if part.length >= 0.5:
                result.append((part, width))
                used = used.union(part)
    return result
