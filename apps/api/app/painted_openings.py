"""Recover reviewable door swings drawn against a continuous painted wall band."""

import cv2
import numpy as np

from .plan_model import Opening, Pt


def painted_swings(model, image):
    # Measured doors on the same drawing give a scale prior without requiring
    # metric calibration. A straight leaf alone is frequent in dimension strings.
    widths = [
        o.width_px
        for o in model.openings
        if o.kind == "door" and o.status == "confirmed" and o.host_wall_id
    ]
    if len(widths) < 2:
        return model
    typical = np.median(widths)
    if not 8 <= typical <= 220:
        return model
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    background = cv2.morphologyEx(gray, cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8))
    dark = cv2.subtract(background, gray)
    nodes = {n.id: n for n in model.nodes}
    arc_ink = cv2.dilate(dark, np.ones((3, 3), np.uint8))
    rows, cols = gray.shape
    angle = np.linspace(0.12, 1.44, 40)
    candidates = []
    for wall in model.walls:
        if wall.source != "extracted" or wall.material != "concrete":
            continue
        a, b = nodes[wall.a], nodes[wall.b]
        start = np.array([a.x, a.y])
        delta = np.array([b.x - a.x, b.y - a.y])
        length = np.linalg.norm(delta)
        if length < typical * 0.72:
            continue
        axis = delta / length
        normal = np.array([-axis[1], axis[0]])
        existing = [
            (o.offset_px, o.offset_px + o.width_px)
            for o in model.openings
            if o.host_wall_id == wall.id and o.status != "rejected"
        ]
        leaves = []
        steps = np.arange(1, round(1.35 * typical) + 1)
        offsets = np.arange(1, round(length))
        for side in (-1, 1):
            face = side * wall.thickness_px / 2
            xy = np.rint(
                start
                + offsets[:, None, None] * axis
                + (face + side * steps[None, :, None]) * normal
            ).astype(int)
            ink = (
                dark[xy[:, :, 1].clip(0, rows - 1), xy[:, :, 0].clip(0, cols - 1)] > 14
            )
            for offset, row in zip(offsets, ink):
                gaps = np.flatnonzero(
                    np.convolve((~row).astype(int), np.ones(3, int), "valid") == 3
                )
                extent = gaps[0] if gaps.size else len(row)
                if (
                    0.67 * typical <= extent <= 1.28 * typical
                    and row[:extent].mean() > 0.82
                ):
                    # Account for hinge mounting on either edge of a thick frame.
                    for inset in (0, 2, 4):
                        leaves.append(
                            (offset, side, face - side * inset, extent + inset)
                        )
        for offset, side, face, radius in leaves:
            for toward in (-1, 1):
                lo, hi = sorted((offset, offset + toward * radius))
                if lo < 0 or hi > length or any(l < hi and r > lo for l, r in existing):
                    continue
                hinge = start + axis * offset + normal * face
                directions = (
                    toward * np.cos(angle)[:, None] * axis
                    + side * np.sin(angle)[:, None] * normal
                )

                def evidence(distance):
                    xy = np.rint(hinge + directions * distance).astype(int)
                    return arc_ink[
                        xy[:, 1].clip(0, rows - 1), xy[:, 0].clip(0, cols - 1)
                    ]

                # The observed arc must be continuous and be distinctly darker
                # than adjacent curves. Dimension grids fail this second check.
                for fitted in np.arange(radius - 3, radius + 3.1, 1):
                    curve = evidence(fitted)
                    if (
                        min(np.mean(group > 14) for group in np.array_split(curve, 4))
                        < 0.8
                    ):
                        continue
                    adjacent = np.maximum(evidence(fitted - 5), evidence(fitted + 5))
                    if np.mean(curve.astype(float) - adjacent > 8) < 0.68:
                        continue
                    candidates.append(
                        (
                            np.mean(curve.astype(float) - adjacent),
                            wall.id,
                            lo,
                            hi,
                            toward,
                            side,
                            start,
                            axis,
                        )
                    )
                    break
    additions = []
    for _, wid, lo, hi, toward, side, start, axis in sorted(
        candidates, key=lambda c: -c[0]
    ):
        if any(
            o.host_wall_id == wid and o.offset_px < hi and o.offset_px + o.width_px > lo
            for o in additions
        ):
            continue
        points = [start + d * axis for d in (lo, hi)]
        additions.append(
            Opening(
                id=f"painted-door-{wid}-{round(lo)}",
                kind="door",
                host_wall_id=wid,
                offset_px=lo,
                width_px=hi - lo,
                span=tuple(Pt(x=p[0], y=p[1]) for p in points),
                swing="left" if side > 0 else "right",
                hinge="start" if toward > 0 else "end",
                status="proposed",
                confidence=0.77,
            )
        )
    return (
        model.model_copy(update={"openings": [*model.openings, *additions]})
        if additions
        else model
    )


def remove_dimension_hosts(model, image, strips):
    """Discard a synthetic door host supported only by a through-going dimension line."""
    from .plan_derive import derive

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY).astype(np.int16)
    nodes = {n.id: n for n in model.nodes}
    walls = {w.id: w for w in model.walls}
    remove = set()
    for opening in model.openings:
        wall = walls.get(opening.host_wall_id)
        if opening.kind != "door" or not wall or wall.source != "extracted":
            continue
        if sum(o.host_wall_id == wall.id for o in model.openings) != 1:
            continue
        a, b = nodes[wall.a], nodes[wall.b]
        horizontal = abs(a.y - b.y) < 1
        if not horizontal and abs(a.x - b.x) > 1:
            continue
        start, end = (a.x, b.x) if horizontal else (a.y, b.y)
        width = opening.width_px
        if width < 12 or abs(end - start) > 1.35 * width:
            continue
        raster = gray if horizontal else gray.T
        tint = strips.structural_colour if horizontal else strips.structural_colour.T
        lane = round((a.y + b.y) / 2 if horizontal else (a.x + b.x) / 2)
        jamb = start + np.sign(end - start) * opening.offset_px
        lo, hi = sorted([round(jamb), round(jamb + np.sign(end - start) * width)])
        reach = round(width * 0.9)
        if (
            lo < reach
            or hi + reach >= raster.shape[1]
            or not 6 <= lane < raster.shape[0] - 6
        ):
            continue
        if tint[lane - 3 : lane + 4, lo:hi].mean() > 0.16:
            continue
        radius = min(7, max(2, round(wall.thickness_px * .4)), lane-3, len(raster)-4-lane)
        for row in range(lane - radius, lane + radius + 1):
            contrast = (raster[row - 3] + raster[row + 3]) / 2 - raster[row]
            runs = [
                contrast[lo - reach : lo - 5],
                contrast[lo + 3 : hi - 3],
                contrast[hi + 5 : hi + reach],
            ]
            if all(np.mean(segment > 11) > 0.8 for segment in runs):
                remove.add(wall.id)
                break
    if not remove:
        return model
    walls = [w for w in model.walls if w.id not in remove]
    used = {key for w in walls for key in (w.a, w.b)}
    return derive(
        model.model_copy(
            update={
                "walls": walls,
                "nodes": [n for n in model.nodes if n.id in used],
                "openings": [o for o in model.openings if o.host_wall_id not in remove],
            }
        )
    )


def remove_clipped_site_artifacts(model):
    """Reject openings traced from furniture inside the recovered site layout."""
    from shapely.geometry import LineString, Polygon
    from .plan_derive import derive

    nodes = {n.id: (n.x, n.y) for n in model.nodes}
    walls = {wall.id: wall for wall in model.walls}
    paths = {
        wall.id: LineString((nodes[wall.a], nodes[wall.b])) for wall in model.walls
    }
    room_edges = {key for room in model.rooms for key in room.wall_ids}
    rooms = [Polygon([(p.x, p.y) for p in room.polygon]) for room in model.rooms]
    cars = [
        s for s in model.room_symbols if s.kind == "car" and s.width_px and s.depth_px
    ]
    rejected, remove_walls = set(), set()
    for opening in model.openings:
        if not opening.span or opening.host_wall_id not in walls:
            continue
        host = walls[opening.host_wall_id]
        span = LineString([(p.x, p.y) for p in opening.span])
        middle = span.interpolate(0.5, normalized=True)
        if host.id not in room_edges:
            furnishing_window = opening.kind == "window" and any(
                r.contains(middle) for r in rooms
            )
            crosses_car = any(
                (
                    (middle.x - car.position.x) * np.cos(np.deg2rad(car.rotation))
                    + (middle.y - car.position.y) * np.sin(np.deg2rad(car.rotation))
                )
                ** 2
                / (0.45 * car.width_px) ** 2
                + (
                    (middle.y - car.position.y) * np.cos(np.deg2rad(car.rotation))
                    - (middle.x - car.position.x) * np.sin(np.deg2rad(car.rotation))
                )
                ** 2
                / (0.45 * car.depth_px) ** 2
                < 1
                for car in cars
            )
            if furnishing_window or crosses_car:
                rejected.add(opening.id)
                remove_walls.add(host.id)
                continue
        if opening.kind == "door" and host.thickness_px < 0.22 * opening.width_px:
            # An immediately parallel wall throughout the swing span is
            # evidence of a traced cabinet line or duplicate wall face.
            tolerance = 1.8 * host.thickness_px
            if any(
                key != host.id
                and span.distance(line) > 0.35 * host.thickness_px
                and line.buffer(tolerance).covers(span)
                for key, line in paths.items()
            ):
                rejected.add(opening.id)
    if not rejected:
        return model
    openings = [o for o in model.openings if o.id not in rejected]
    remove_walls.difference_update(o.host_wall_id for o in openings)
    remaining = [w for w in model.walls if w.id not in remove_walls]
    used = {key for wall in remaining for key in (wall.a, wall.b)}
    return derive(
        model.model_copy(
            update={
                "walls": remaining,
                "openings": openings,
                "nodes": [n for n in model.nodes if n.id in used],
            }
        )
    )
