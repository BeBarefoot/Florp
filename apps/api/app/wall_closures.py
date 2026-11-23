"""Second-pass search for a faint fourth side of an open room."""

from collections import defaultdict, deque
import math

import cv2
import numpy as np
from shapely import STRtree
from shapely.geometry import LineString

from .plan_model import ClosureEvidence, Finding, Pt


def candidates(model):
    pos = {n.id: np.array([n.x, n.y]) for n in model.nodes}
    links = defaultdict(dict)
    obstacles = []
    for wall in model.walls:
        links[wall.a][wall.b] = links[wall.b][wall.a] = wall.thickness_px
        obstacles.append(LineString([pos[wall.a], pos[wall.b]]))
    wall_lines = {wall.id: line for wall, line in zip(model.walls, obstacles)}
    apertures = []
    for opening in model.openings:
        if opening.status == "rejected":
            continue
        host = wall_lines.get(opening.host_wall_id)
        if host is not None:
            apertures.append(
                LineString(
                    [
                        host.interpolate(d)
                        for d in (
                            opening.offset_px,
                            opening.offset_px + opening.width_px,
                        )
                    ]
                )
            )
        elif opening.span:
            apertures.append(LineString([(p.x, p.y) for p in opening.span]))
    openings_index = STRtree(apertures)
    # Hosted openings sometimes split a single side into several graph edges.
    # Simplify the search graph only; keep the saved nodes and hosts intact.
    queue = deque(links)
    while queue:
        n = queue.popleft()
        if n not in links or len(links[n]) != 2:
            continue
        p, q = links[n]
        u, v = pos[p] - pos[n], pos[q] - pos[n]
        if q in links[p] or u @ v >= -0.999 * np.linalg.norm(u) * np.linalg.norm(v):
            continue
        weight = (links[n][p] + links[n][q]) / 2
        del links[p][n], links[q][n], links[n]
        links[p][q] = links[q][p] = weight
        queue.extend((p, q))
    index = STRtree(obstacles)
    seen = set()
    for a, ends in links.items():
        if len(ends) > 4:
            continue
        for b in ends:
            if len(links[b]) > 4:
                continue
            for c in links[b]:
                if c == a or len(links[c]) > 4:
                    continue
                for d in links[c]:
                    if d in (a, b) or d in ends or d <= a or (a, d) in seen:
                        continue
                    start, end = pos[a], pos[d]
                    base = pos[c] - pos[b]
                    length = np.linalg.norm(base)
                    width = np.median([ends[b], links[b][c], links[c][d]])
                    if length < max(12, 3 * width):
                        continue
                    unit = base / length
                    normal = np.array([-unit[1], unit[0]])
                    sides = [start - pos[b], end - pos[c]]
                    depths = [s @ normal for s in sides]
                    if depths[0] * depths[1] <= 0 or min(map(abs, depths)) < 2 * width:
                        continue
                    if any(abs(s @ unit) > 0.35 * np.linalg.norm(s) for s in sides):
                        continue
                    # A partition may meet the middle of a longer wall (T joint).
                    # Use the shorter return's depth, preserving near-aligned ends.
                    if abs(depths[0] - depths[1]) > width * 0.5:
                        if abs(depths[0]) < abs(depths[1]):
                            end = pos[c] + sides[1] * (depths[0] / depths[1])
                        else:
                            start = pos[b] + sides[0] * (depths[1] / depths[0])
                    chord = end - start
                    span_length = np.linalg.norm(chord)
                    if span_length < max(12, 3 * width):
                        continue
                    unit = chord / span_length
                    normal = np.array([-unit[1], unit[0]])
                    interior = LineString([start + unit, end - unit])
                    if len(index.query(interior, predicate="intersects")):
                        continue
                    if len(
                        openings_index.query(
                            LineString([start, end]).buffer(width / 2),
                            predicate="intersects",
                        )
                    ):
                        continue
                    seen.add((a, d))
                    yield a, d, start, end, normal, width


def search_closures(model, image):
    model.findings = [f for f in model.findings if f.category != "suggested_closure"]
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    for a, d, start, end, normal, width in candidates(model):
        key = f"suggested_closure:{a}:{d}"
        if key in model.dismissed_findings:
            continue
        # Probe across the possible wall. Compare against paper on BOTH sides,
        # and measure a continuous filled band rather than a single pencil line.
        radius = min(96, max(7, math.ceil(width * 1.7)))
        offsets = np.arange(-radius, radius + 1)
        count = min(1024, max(16, math.ceil(np.linalg.norm(end - start))))
        centers = start + np.linspace(0.05, 0.95, count)[:, None] * (end - start)
        sample = np.rint(centers[:, None, :] + offsets[None, :, None] * normal).astype(
            int
        )
        x, y = sample[:, :, 0], sample[:, :, 1]
        if (
            x.min() < 0
            or y.min() < 0
            or x.max() >= gray.shape[1]
            or y.max() >= gray.shape[0]
        ):
            continue
        values = gray[y, x].astype(float)
        paper = np.minimum(values[:, :3].mean(1), values[:, -3:].mean(1))
        ink = values <= paper[:, None] - 10
        left = np.argmin(ink[:, radius::-1], axis=1)
        right = np.argmin(ink[:, radius:], axis=1)
        widths = left + right - 1
        supported = (widths >= max(3, width * 0.25)) & (widths < radius * 1.6)
        if (
            supported.mean() < 0.94
            or np.convolve((~supported).astype(int), [1, 1, 1], mode="valid").max() == 3
        ):
            continue
        p, q = Pt(x=start[0], y=start[1]), Pt(x=end[0], y=end[1])
        model.findings.append(
            Finding(
                id=key,
                category="suggested_closure",
                target_ids=[a, d],
                anchor=Pt(x=(p.x + q.x) / 2, y=(p.y + q.y) / 2),
                message="Possible missing wall along a faint band",
                closure=ClosureEvidence(
                    start=p, end=q, thickness_px=float(np.median(widths[supported]))
                ),
            )
        )
        if sum(f.category == "suggested_closure" for f in model.findings) >= 30:
            break
    return model


def current_closures(model):
    prior = {
        tuple(f.target_ids): f
        for f in model.findings
        if f.category == "suggested_closure" and f.closure
    }
    if prior:
        for a, d, p, q, _, _ in candidates(model):
            f = prior.get((a, d))
            if (
                f
                and (f.closure.start.x, f.closure.start.y) == tuple(p)
                and (f.closure.end.x, f.closure.end.y) == tuple(q)
            ):
                yield f
