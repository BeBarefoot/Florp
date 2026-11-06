"""Local CV detection of turning stairs from rails, regular treads and winders."""

from dataclasses import dataclass
from itertools import combinations

import cv2
import numpy as np

from .plan_model import Pt, Stair


@dataclass(frozen=True)
class Flight:
    horizontal: bool
    cross: tuple[float, float]
    bars: tuple[float, ...]
    pitch: float
    score: float

    @property
    def width(self):
        return self.cross[1] - self.cross[0]

    @property
    def ends(self):
        return self.bars[0], self.bars[-1]


def _runs(indices):
    return np.split(indices, np.flatnonzero(np.diff(indices) > 1) + 1)


def _flights(mask, size, horizontal):
    raster = mask.T.copy() if horizontal else mask
    bars = cv2.morphologyEx(raster, cv2.MORPH_CLOSE, np.ones((1, 5), np.uint8)) > 0
    rails = cv2.morphologyEx(raster, cv2.MORPH_CLOSE, np.ones((5, 1), np.uint8))
    min_rail = max(12, round(size * 0.105))
    rails = cv2.morphologyEx(rails, cv2.MORPH_OPEN, np.ones((min_rail, 1), np.uint8))
    spans = [
        (x, int(run[0]), int(run[-1]))
        for x in range(rails.shape[1]) for run in _runs(np.flatnonzero(rails[:, x]))
        if len(run) >= min_rail
    ]
    tracks = []
    for x, a, b in sorted(spans, key=lambda v: (v[1] - v[2], v)):
        if not any(abs(x - c) <= 3 and min(b, hi) - max(a, lo) > 0.75 * (b - a)
                   for c, lo, hi in tracks):
            tracks.append((x, a, b))
        if len(tracks) >= 190:
            break
    candidates = []
    for (x, a, b), (z, c, d) in combinations(sorted(tracks), 2):
        width = z - x
        lo, hi = max(a, c), min(b, d)
        if not size * 0.08 <= width <= size * 0.2 or hi - lo < size * 0.07:
            continue
        origin = max(0, lo - 2)
        coverage = bars[origin:hi + 3, x + 3:z - 2].mean(axis=1)
        lines = [float(np.mean(run) + origin) for run in _runs(np.flatnonzero(coverage > 0.76))
                 if 0 < len(run) <= size * 0.025]
        best = None
        for i, first in enumerate(lines):
            for j in range(i + 1, len(lines)):
                pitch = lines[j] - first
                if pitch > size * 0.055:
                    break
                if pitch < size * 0.021 or not 2.4 <= width / pitch <= 6.5:
                    continue
                picks = [first, lines[j]]
                for y in lines[j + 1:]:
                    n, last = round((y - first) / pitch), round((picks[-1] - first) / pitch)
                    if n - last > 2:
                        break
                    if n > last and abs(y - (first + n * pitch)) <= 0.19 * pitch:
                        picks.append(y)
                missed = round((picks[-1] - first) / pitch) + 1 - len(picks)
                if len(picks) < 4 or missed > 1:
                    continue
                score = len(picks) - 0.65 * missed - 0.95 * abs(width / pitch - 3.9)
                if best is None or score > best.score:
                    best = Flight(horizontal, (x, z), tuple(picks), pitch, score)
        if best:
            candidates.append(best)
    return sorted(candidates, key=lambda f: -f.score)[:65]


@dataclass(frozen=True)
class Corner:
    exit: int
    entry: int
    inside: tuple[float, float]
    outside: tuple[float, float]
    score: float


def _corner(a, b, ink, diagonals):
    if a.horizontal == b.horizontal or not 0.76 <= a.width / b.width <= 1.31:
        return None
    if not 0.79 <= a.pitch / b.pitch <= 1.27:
        return None
    x, y = (b, a) if a.horizontal else (a, b)
    # x is the vertical flight, so its rails are at constant x.
    best = None
    for ix, xv in enumerate(x.cross):
        for iy, yv in enumerate(y.cross):
            ex = min((0, 1), key=lambda j: abs(x.ends[j] - yv))
            ey = min((0, 1), key=lambda j: abs(y.ends[j] - xv))
            dx, dy = abs(y.ends[ey] - xv), abs(x.ends[ex] - yv)
            if max(dx, dy) > 0.52 * min(x.pitch, y.pitch):
                continue
            if (x.ends[1 - ex] - yv) * (y.cross[1 - iy] - yv) >= 0:
                continue
            if (y.ends[1 - ey] - xv) * (x.cross[1 - ix] - xv) >= 0:
                continue
            outer = (x.cross[1 - ix], y.cross[1 - iy])
            # A dimension string may light up diagonal samples by chance.
            # Require a straight observed segment along the winder diagonal.
            start = np.array((xv, yv))
            delta = np.array(outer) - start
            length = np.linalg.norm(delta)
            direction = delta / length
            points = diagonals - start
            along = points @ direction
            off = np.abs(points @ np.array((-direction[1], direction[0])))
            overlap = np.minimum(along.max(axis=1), length) - np.maximum(along.min(axis=1), 0)
            if not np.any((off.max(axis=1) <= max(3, 0.055 * length)) & (overlap >= 0.30 * length)):
                continue
            t = np.linspace(0.12, 0.88, 28)
            px = np.rint(xv + t * (outer[0] - xv)).astype(int)
            py = np.rint(yv + t * (outer[1] - yv)).astype(int)
            support = ink[py, px].mean()
            if support < 0.67:
                continue
            score = float(support) - (dx + dy) / (x.pitch + y.pitch)
            e, f = (ey, ex) if a.horizontal else (ex, ey)
            if best is None or score > best.score:
                best = Corner(e, f, (xv, yv), outer, score)
    return best


def _polygons(chain, links, first_entry):
    result = []
    for i, flight in enumerate(chain):
        entry = first_entry if i == 0 else links[i - 1].entry
        values = list(flight.bars if entry == 0 else reversed(flight.bars))
        axis = 0 if flight.horizontal else 1
        if i:
            values[0] = links[i - 1].inside[axis]
        if i < len(links):
            values[-1] = links[i].inside[axis]
        for a, b in zip(values, values[1:]):
            count = max(1, round(abs(b - a) / flight.pitch))
            positions = np.linspace(a, b, count + 1)
            for u, v in zip(positions, positions[1:]):
                lo, hi = flight.cross
                result.append([(u, lo), (v, lo), (v, hi), (u, hi)] if flight.horizontal
                              else [(lo, u), (hi, u), (hi, v), (lo, v)])
        if i < len(links):
            ix, iy = links[i].inside
            ox, oy = links[i].outside
            p, q = ((ix, oy), (ox, iy)) if flight.horizontal else ((ox, iy), (ix, oy))
            result.extend([[(ix, iy), p, (ox, oy)], [(ix, iy), (ox, oy), q]])
    return [[Pt(x=float(x), y=float(y)) for x, y in polygon] for polygon in result]


def detect_stairs(image, envelope=None):
    """Require a regular flight on each side of a visible diagonal turn."""
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    # Bound the pixel search on large scans; return geometry in source pixels.
    scale = min(1, 900 / min(gray.shape), 2400 / max(gray.shape))
    if scale < 1:
        gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    size = min(gray.shape)
    if size < 160:
        return []
    mask = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_MEAN_C,
                                 cv2.THRESH_BINARY_INV, max(15, round(size * 0.055) | 1), 9)
    ink = cv2.dilate(mask, np.ones((5, 5), np.uint8)) > 0
    lines = cv2.createLineSegmentDetector().detect(gray)[0]
    if lines is None:
        return []
    diagonals = lines.reshape(-1, 2, 2)
    diagonals = diagonals[(np.abs(diagonals[:, 1] - diagonals[:, 0]) >= 0.031 * size).all(axis=1)]
    if not len(diagonals):
        return []
    flights = _flights(mask, size, False) + _flights(mask, size, True)
    connections = {i: [] for i in range(len(flights))}
    for i, j in combinations(range(len(flights)), 2):
        if (c := _corner(flights[i], flights[j], ink, diagonals)) is not None:
            connections[i].append((j, c))
            connections[j].append((i, Corner(c.entry, c.exit, c.inside, c.outside, c.score)))
    chains = []
    for i, a in enumerate(flights):
        for j, ab in connections[i]:
            if i < j:
                chains.append((a.score + flights[j].score + 2 * ab.score, (i, j), (ab,)))
            for k, bc in connections[j]:
                if i < k and ab.entry != bc.exit and flights[i].horizontal == flights[k].horizontal:
                    chains.append((a.score + flights[j].score + flights[k].score + 2 * (ab.score + bc.score),
                                   (i, j, k), (ab, bc)))
    out, boxes = [], []
    for _, ids, links in sorted(chains, key=lambda chain: -chain[0]):
        treads = _polygons([flights[i] for i in ids], links, 1 - links[0].exit)
        if len(treads) > 80:
            continue
        coords = [(p.x, p.y) for tread in treads for p in tread]
        x0, y0, x1, y1 = min(p[0] for p in coords), min(p[1] for p in coords), max(p[0] for p in coords), max(p[1] for p in coords)
        area = (x1 - x0) * (y1 - y0)
        if not area or any(max(0, min(x1, d) - max(x0, a)) * max(0, min(y1, e) - max(y0, b))
                           > 0.4 * min(area, (d - a) * (e - b)) for a, b, d, e in boxes):
            continue
        if envelope is not None and any(
            cv2.pointPolygonTest(envelope, (float(x / scale), float(y / scale)), False) < 0
            for x, y in coords
        ):
            continue
        boxes.append((x0, y0, x1, y1))
        out.append(Stair(id=f"stair-{len(out)}", treads=[
            [Pt(x=p.x / scale, y=p.y / scale) for p in tread] for tread in treads
        ], layout="u" if len(ids) == 3 else "l"))
        if len(out) == 12:
            break
    return out
