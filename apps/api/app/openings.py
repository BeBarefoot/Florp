"""Gap-first openings.

Real openings are *gaps in the wall strips*. Every gap is enumerated first and
then classified from the pixels inside it (window rails, door arc and leaf,
overhead-door dashes). A detector box can only raise or lower the confidence of
a gap that already exists; it never places an opening by itself, and the span
is always the gap, never the box.
"""

from __future__ import annotations
import math
from dataclasses import dataclass, field
import cv2
import numpy as np
from .plan_workspace import Segment, Point
from .ink_layers import _local_paper

YOLO_AGREE = 0.15
YOLO_DISAGREE = 0.20


@dataclass
class Box:
    category: str
    x1: float
    y1: float
    x2: float
    y2: float
    confidence: float = 0.5


@dataclass
class Gap:
    horizontal: bool
    cross: float  # centreline coordinate across the wall
    lo: float  # along-axis interval (px)
    hi: float
    t: float  # wall thickness


@dataclass
class Result:
    objects: list = field(default_factory=list)
    passages: list = field(default_factory=list)  # centres of plain gaps
    gaps: list = field(default_factory=list)  # (Gap, kind|None, confidence)


def _axis(o):
    dx, dy = abs(o.end.x - o.start.x), abs(o.end.y - o.start.y)
    if dx >= dy and dy <= 0.2 * dx + 1:
        return True
    if dy > dx and dx <= 0.2 * dy + 1:
        return False
    return None


def _pieces(walls):
    """Union collinear wall intervals per orientation and centreline."""
    out = []
    for horizontal in (True, False):
        items = []
        for w in walls:
            if _axis(w) is not horizontal:
                continue
            a, c = (w.start.x, w.end.x), (w.start.y, w.end.y)
            if not horizontal:
                a, c = (w.start.y, w.end.y), (w.start.x, w.end.x)
            items.append((sum(c) / 2, min(a), max(a), w.thickness_px))
        items.sort()
        clusters = []
        for cross, lo, hi, t in items:
            for cl in clusters:
                if abs(cross - cl["cross"]) <= max(t, cl["t"]) / 2 + 1.5:
                    cl["items"].append((lo, hi, t))
                    cl["cross"] = sum(
                        [cl["cross"] * (len(cl["items"]) - 1), cross]
                    ) / len(cl["items"])
                    cl["t"] = max(cl["t"], t)
                    break
            else:
                clusters.append({"cross": cross, "t": t, "items": [(lo, hi, t)]})
        for cl in clusters:
            merged = []
            for lo, hi, t in sorted(cl["items"]):
                if merged and lo <= merged[-1][1] + 0.5:
                    merged[-1][1] = max(merged[-1][1], hi)
                    merged[-1][2] = max(merged[-1][2], t)
                else:
                    merged.append([lo, hi, t])
            out.append((horizontal, cl["cross"], merged))
    return out


def enumerate_gaps(walls, size, min_factor=2.2, max_factor=32.0):
    """Collinear intervals between strips, plus wall ends that stop short of a perpendicular wall."""
    h, w = size
    pieces = _pieces(walls)
    gaps, seen = [], set()

    def add(g):
        key = (g.horizontal, round(g.cross / 3), round(g.lo / 3), round(g.hi / 3))
        if key not in seen:
            seen.add(key)
            gaps.append(g)

    def limit(t):
        return min(max_factor * t, 0.35 * max(h, w))

    for horizontal, cross, merged in pieces:
        for (lo1, hi1, t1), (lo2, hi2, t2) in zip(merged, merged[1:]):
            t = max(t1, t2)
            if min_factor * t <= lo2 - hi1 <= limit(t):
                add(Gap(horizontal, cross, hi1, lo2, t))
    # A wall end that stops short of a perpendicular wall, or of a wall's end.
    for horizontal, cross, merged in pieces:
        perp = [p for p in pieces if p[0] != horizontal]
        for i, (lo, hi, t) in enumerate(merged):
            for end, direction in ((lo, -1), (hi, 1)):
                nxt = (
                    merged[i + direction] if 0 <= i + direction < len(merged) else None
                )
                if nxt and abs((nxt[1] if direction < 0 else nxt[0]) - end) <= limit(t):
                    continue  # handled as a collinear gap
                best = None
                for _, pcross, pm in perp:
                    if (pcross - end) * direction < 0 or abs(pcross - end) > limit(
                        t
                    ) + t:
                        continue
                    pt = max(x[2] for x in pm)
                    if not any(a - t <= cross <= b + t for a, b, _ in pm):
                        continue
                    face = pcross - direction * pt / 2
                    dist = abs(face - end)
                    if best is None or dist < best[0]:
                        best = (dist, face)
                if best and best[0] >= min_factor * t:
                    a, b = sorted((end, best[1]))
                    add(Gap(horizontal, cross, a, b, t))
    return gaps


def _line_ink(image, strips):
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    paper = _local_paper(gray).astype(np.float32)
    line = gray < 0.8 * paper
    if strips.ink is not None:
        line |= strips.ink
    grown = (
        cv2.dilate(
            (strips.red | strips.blue | strips.dark).astype(np.uint8),
            np.ones((3, 3), np.uint8),
        )
        > 0
    )
    return line & ~grown


def _rails(line, gap: Gap):
    """Full-length parallel lines inside the gap band (window glass)."""
    half = int(math.ceil(gap.t / 2 + 1.5))
    lo, hi = int(gap.lo) + 1, int(gap.hi) - 1
    c = int(round(gap.cross))
    h, w = line.shape
    if hi - lo < 4:
        return 0, 0.0
    # Sample parallel rails at small slopes: a photographed window can drift
    # several pixels over its span and never occupy 75% of one raster row.
    along = np.arange(max(0, lo), min(w if gap.horizontal else h, hi))
    if along.size < 4:
        return 0, 0.0
    offsets = np.arange(-half, half + 1)[:, None]
    position = np.linspace(-0.5, 0.5, along.size)[None, :]
    best = (0, 0.0)
    drift = min(8.0, 0.05 * along.size)
    for shift in np.linspace(-drift, drift, 9):
        across = np.rint(c + offsets + shift * position).astype(int)
        axis = np.broadcast_to(along, across.shape)
        xs, ys = (axis, across) if gap.horizontal else (across, axis)
        valid = (xs >= 0) & (xs < w) & (ys >= 0) & (ys < h)
        samples = np.zeros(valid.shape, bool)
        samples[valid] = line[ys[valid], xs[valid]]
        prof = samples.mean(axis=1)
        rails = np.flatnonzero(prof >= 0.75)
        if not len(rails):
            continue
        groups = np.split(rails, np.flatnonzero(np.diff(rails) > 1) + 1)
        centres = [g.mean() for g in groups]
        distinct = [centres[0]]
        for x in centres[1:]:
            if x - distinct[-1] >= 2:
                distinct.append(x)
        candidate = (len(distinct), float(min(prof[rails])))
        if candidate > best:
            best = candidate
    return best


def _door(line_dil, gap: Gap):
    """Quarter-circle arc centred on one gap end, plus a leaf line. Returns best candidate or None."""
    h, w = line_dil.shape
    g = gap.hi - gap.lo
    best = None
    for hinge_at_lo in (True, False):
        for side in (-1, 1):
            hinge = gap.lo if hinge_at_lo else gap.hi
            toward = 1 if hinge_at_lo else -1
            for r in (0.85 * g, 0.95 * g, g, 1.08 * g):
                for opening_angle in (45, 60, 90):
                    angles = np.radians(
                        np.linspace(0.12 * opening_angle, 0.88 * opening_angle, 19)
                    )
                    a = hinge + toward * r * np.cos(angles)
                    c = gap.cross + side * r * np.sin(angles)
                    xs, ys = (a, c) if gap.horizontal else (c, a)
                    xi, yi = np.rint(xs).astype(int), np.rint(ys).astype(int)
                    ok = (xi >= 0) & (xi < w) & (yi >= 0) & (yi < h)
                    if ok.sum() < 0.8 * len(angles):
                        continue
                    arc = float(line_dil[yi[ok], xi[ok]].mean())
                    theta = math.radians(opening_angle)
                    steps = np.linspace(gap.t / 2 + 1, 0.95 * r, max(4, int(r)))
                    la = hinge + toward * steps * math.cos(theta)
                    lc = gap.cross + side * steps * math.sin(theta)
                    lx, ly = (la, lc) if gap.horizontal else (lc, la)
                    lxi, lyi = np.rint(lx).astype(int), np.rint(ly).astype(int)
                    lok = (lxi >= 0) & (lxi < w) & (lyi >= 0) & (lyi < h)
                    leaf = (
                        float(line_dil[lyi[lok], lxi[lok]].mean()) if lok.any() else 0.0
                    )
                    score = arc + 0.25 * leaf
                    if (
                        arc >= 0.8
                        and leaf >= 0.75
                        and (best is None or score > best[0])
                    ):
                        best = (score, arc, leaf, hinge_at_lo, side)
    return best


def _dashes(line, gap: Gap):
    """Sparse thin ink along an overhead-door gap: present but not a continuous rail."""
    half = int(math.ceil(gap.t * 1.5))
    lo, hi = int(gap.lo), int(gap.hi)
    c = int(round(gap.cross))
    h, w = line.shape
    if gap.horizontal:
        band = line[max(0, c - half) : c + half + 1, max(0, lo) : min(w, hi)]
    else:
        band = line[max(0, lo) : min(h, hi), max(0, c - half) : c + half + 1]
    if not gap.horizontal:
        band = band.T
    if not band.size:
        return 0.0
    best = 0.0
    for row in band:
        edges = np.diff(np.r_[False, row, False].astype(np.int8))
        intervals = [
            (a, b)
            for a, b in zip(np.flatnonzero(edges == 1), np.flatnonzero(edges == -1))
            if 2 <= b - a <= 0.35 * len(row)
        ]
        if len(intervals) < 3:
            continue
        gaps = [b[0] - a[1] for a, b in zip(intervals, intervals[1:])]
        lengths = [b - a for a, b in intervals]
        coverage = sum(lengths) / len(row)
        if (
            0.12 <= coverage <= 0.8
            and np.mean(gaps) > 1
            and np.std(gaps) / np.mean(gaps) < 0.6
            and np.std(lengths) / np.mean(lengths) < 0.6
        ):
            best = max(best, coverage)
    return best


def _on_exterior(exterior, gap: Gap):
    if exterior is None:
        return False  # an overhead door needs a known outer wall
    a = (gap.lo + gap.hi) / 2
    x, y = (a, gap.cross) if gap.horizontal else (gap.cross, a)
    h, w = exterior.shape
    return bool(exterior[min(h - 1, max(0, int(y))), min(w - 1, max(0, int(x)))])


def _yolo(gap: Gap, boxes):
    """Boxes whose area contains the gap centre (expanded by a wall thickness)."""
    cx, cy = (
        ((gap.lo + gap.hi) / 2, gap.cross)
        if gap.horizontal
        else (gap.cross, (gap.lo + gap.hi) / 2)
    )
    m = gap.t
    hits = [
        b
        for b in boxes
        if b.category in ("door", "window")
        and b.x1 - m <= cx <= b.x2 + m
        and b.y1 - m <= cy <= b.y2 + m
    ]
    if not hits:
        return None
    return max(hits, key=lambda b: b.confidence)


def _segment(gap: Gap, kind, confidence, index, door=None):
    def pt(a, c):
        return Point(x=a, y=c) if gap.horizontal else Point(x=c, y=a)

    lo, hi = gap.lo, gap.hi
    start, end = (lo, hi)
    leaf = None
    if door:
        _, _, _, hinge_at_lo, side = door
        if not hinge_at_lo:
            start, end = hi, lo
        lx, ly = (0.0, float(side)) if gap.horizontal else (float(side), 0.0)
        leaf = Point(x=lx, y=ly)
    host = Segment(
        id=f"gap-host-{index}",
        start=pt(lo, gap.cross),
        end=pt(hi, gap.cross),
        thickness_px=gap.t,
        uncertain=False,
    )
    opening = Segment(
        id=f"opening-{index}",
        kind=kind,
        start=pt(start, gap.cross),
        end=pt(end, gap.cross),
        thickness_px=gap.t,
        host_id=host.id,
        uncertain=True,
        confidence=float(min(0.99, max(0.05, confidence))),
        height_m={"door": 2.1, "window": 1.2, "garage": 2.1}[kind],
        sill_m=0.9 if kind == "window" else 0,
        leaf=leaf,
    )
    return [host, opening]


def detect(image, walls, strips, boxes=(), exterior=None) -> Result:
    """Classify every wall gap; ``walls`` are axis-aligned wall Segments."""
    result = Result()
    h, w = image.shape[:2]
    gaps = enumerate_gaps(walls, (h, w))
    line = _line_ink(image, strips)
    line_dil = cv2.dilate(line.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0
    index = 0
    for gap in gaps:
        width = gap.hi - gap.lo
        colour = strips.structural_colour
        if colour is not None:
            # A break in a faint wall mask is not a doorway. If the original
            # structural colour continues through the middle of the gap,
            # leave it unresolved rather than fitting an arc to nearby text.
            along = np.linspace(gap.lo + 0.15 * width, gap.hi - 0.15 * width, max(8, round(width)))
            offsets = np.linspace(-0.3 * gap.t, 0.3 * gap.t, 5)[:, None]
            axis = np.broadcast_to(along, (5, along.size))
            cross = np.broadcast_to(gap.cross + offsets, axis.shape)
            xs, ys = (axis, cross) if gap.horizontal else (cross, axis)
            xi, yi = np.rint(xs).astype(int), np.rint(ys).astype(int)
            valid = (xi >= 0) & (xi < w) & (yi >= 0) & (yi < h)
            evidence = np.zeros(valid.shape, bool)
            evidence[valid] = colour[yi[valid], xi[valid]]
            if np.mean(evidence.mean(axis=0) >= 0.4) > 0.5:
                continue
        kind, conf, door = None, 0.0, None
        rails, rail_min = _rails(line, gap)
        if rails >= 2:
            kind = "window"
            conf = 0.62 + (0.12 if rails >= 3 else 0) + (0.12 if rail_min >= 0.9 else 0)
        else:
            # Thin partitions can host ordinary doors much wider than nine
            # times their thickness. Require arc/leaf evidence, not that ratio.
            door = _door(line_dil, gap) if width <= 20 * gap.t else None
            if door:
                kind = "door"
                conf = 0.5 + 0.3 * min(1.0, door[1]) + (0.1 if door[2] >= 0.6 else 0)
            elif (
                width >= 8 * gap.t
                and _on_exterior(exterior, gap)
                and _dashes(line, gap) > 0
            ):
                # Repeated overhead-door dashes corroborate a wide outer gap.
                # A blank gap alone does not establish a garage opening.
                kind, conf = "garage", 0.4 + (
                    0.1 if 0.03 <= _dashes(line, gap) <= 0.8 else 0
                )
        box = _yolo(gap, boxes)
        if kind:
            if box:
                conf += YOLO_AGREE if box.category == kind else -YOLO_DISAGREE
        if not kind:
            result.passages.append(
                (
                    ((gap.lo + gap.hi) / 2, gap.cross)
                    if gap.horizontal
                    else (gap.cross, (gap.lo + gap.hi) / 2)
                )
            )
            result.gaps.append((gap, None, 0.0))
            continue
        if kind == "garage":
            conf = min(conf, 0.7)
        result.gaps.append((gap, kind, conf))
        result.objects.extend(_segment(gap, kind, conf, index, door))
        index += 1
    return result
