"""Recover an attached open-air balcony from its drawn double-line boundary."""

from hashlib import sha256
import math

import cv2
import numpy as np
from shapely.geometry import LineString, Polygon

from .ink_layers import _local_paper
from .plan_derive import derive
from .plan_model import Node, Pt, Wall
from .wall_alignment import _join_tees


def _spans(row, length):
    cuts = np.diff(np.r_[False, row, False].astype(np.int8))
    return [
        (int(lo), int(hi - 1))
        for lo, hi in zip(np.flatnonzero(cuts == 1), np.flatnonzero(cuts == -1))
        if hi - lo >= length
    ]


def _side(ink, edge, facade, at, step, width):
    """A continuous outside rail with a second rail or infill toward the deck."""
    slab = ink[edge + 2:facade]
    choices = []
    for x in range(max(0, at - 3), min(ink.shape[1], at + 4)):
        rail = slab[:, x]
        if rail.mean() < 0.86 or min(part.mean() for part in np.array_split(rail, 3)) < 0.8:
            continue
        for span in range(2, width + 2):
            inside = x + span * step
            if 0 <= inside < ink.shape[1]:
                inner = slab[:, inside].mean()
                if inner >= 0.43:
                    choices.append((float(rail.mean() + 0.4 * inner), x, span))
    return max(choices, default=None)


def _outline(ink, facade, span, wall_width):
    # Search on the outward side of the facade. Besides the remote pair,
    # both returns must run back to the facade and bracket the existing door.
    low, high = span
    door_width = high - low
    nearest = facade - max(3, round(wall_width / 2))
    depth_min = max(14, round(0.7 * door_width))
    depth_max = min(round(5 * door_width), facade)
    first = max(0, facade - depth_max)
    last = nearest - depth_min
    if last <= first:
        return None
    crop_left = max(0, math.floor(low - 4 * door_width))
    crop_right = min(ink.shape[1], math.ceil(high + 4 * door_width))
    scan = cv2.morphologyEx(
        ink[first:last, crop_left:crop_right].astype(np.uint8),
        cv2.MORPH_CLOSE, np.ones((1, 3), np.uint8),
    )
    min_length = max(16, round(1.2 * door_width))
    rows = [_spans(row, min_length) for row in scan]
    max_gap = max(3, min(12, round(wall_width * 0.65)))
    choices = []
    for y, spans in enumerate(rows):
        for a, b in spans:
            a, b = a + crop_left, b + crop_left
            if not (a + 3 < low < high < b - 3):
                continue
            if b - a > 8 * door_width or b - a < 0.65 * (facade - first - y):
                continue
            for gap in range(2, min(max_gap + 1, len(rows) - y)):
                if not any(
                    abs(c + crop_left - a) <= gap + 3
                    and abs(d + crop_left - b) <= gap + 3
                    for c, d in rows[y + gap]
                ):
                    continue
                edge = first + y
                # An outer rail has paper on its outside and a contrasting
                # strip between the two rail cores. Thick walls fail this check.
                if edge < 2 or ink[edge - 2:edge, a + 6:b - 5].mean() > 0.15:
                    continue
                if ink[edge + 1:edge + gap, a + 6:b - 5].mean() > 0.55:
                    continue
                left = _side(ink, edge, nearest, a, 1, gap)
                right = _side(ink, edge, nearest, b, -1, gap)
                if left is not None and right is not None:
                    _, x, t_left = left
                    _, z, t_right = right
                    choices.append((
                        left[0] + right[0], -edge,
                        (x + t_left / 2, z - t_right / 2, edge + gap / 2, t_left, gap, t_right),
                    ))
    return max(choices, default=(None, None, None))[2]


def _attach(model, points, widths):
    coords = {(n.x, n.y): n for n in model.nodes}
    if len(model.nodes) > 19996 or len(model.walls) > 9995:
        return model
    key = "balcony-" + sha256(repr(points).encode()).hexdigest()[:16]
    if any(w.id.startswith(key) for w in model.walls):
        return model
    nodes = list(model.nodes)
    ends = []
    for i, (x, y) in enumerate(points):
        node = coords.get((x, y))
        if node is None:
            node = Node(id=f"{key}-{i}", x=x, y=y)
            nodes.append(node)
        ends.append(node.id)
    # Height is an editable parapet default. The scan supplies the plan
    # footprint and thickness, and carries no vertical dimension.
    walls = [
        Wall(id=f"{key}-edge-{i}", a=a, b=b, thickness_px=width, height_m=1.05, exterior=True)
        for i, (a, b, width) in enumerate(zip(ends, ends[1:], widths))
    ]
    updated = _join_tees(model.model_copy(update={"nodes": nodes, "walls": model.walls + walls}))
    # Keep extraction-only observations that are unavailable to derivation.
    observed = {"pruned_fragments", "merged_duplicates", "open_passage"}
    updated = derive(updated)
    updated.findings.extend(f for f in model.findings if f.category in observed)
    boundary = {w.id for w in walls}
    for room in updated.rooms:
        if boundary <= set(room.wall_ids):
            room.label, room.room_type = "Balcony", "balcony"
            break
    else:
        return model
    # Keep the editor outline consistent with the newly recovered boundary.
    if updated.envelope:
        old = Polygon([(p.x, p.y) for p in updated.envelope])
        combined = old.union(Polygon(points))
        if combined.geom_type == "Polygon" and len(combined.exterior.coords) <= 65:
            updated.envelope = [Pt(x=x, y=y) for x, y in list(combined.exterior.coords)[:-1]]
    return updated


def recover_balconies(model, image):
    if not model.rooms:
        return model
    by_wall = {w.id: w for w in model.walls}
    nodes = {n.id: n for n in model.nodes}
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    strokes = gray < 0.84 * _local_paper(gray)
    for door in model.openings:
        if door.kind != "door" or door.status == "rejected":
            continue
        wall = by_wall.get(door.host_wall_id)
        if wall is None or door.width_px < 10:
            continue
        a, b = nodes[wall.a], nodes[wall.b]
        if a.y == b.y:
            raster, axis, lane = strokes, "x", a.y
            cross = "y"
        elif a.x == b.x:
            raster, axis, lane = strokes.T, "y", a.x
            cross = "x"
        else:
            continue
        start, end = getattr(a, axis), getattr(b, axis)
        if start == end:
            continue
        direction = math.copysign(1, end - start)
        span = sorted(start + direction * offset for offset in (door.offset_px, door.offset_px + door.width_px))
        bounds = [getattr(n, cross) for n in model.nodes]
        reverse = abs(max(bounds) - lane) < abs(min(bounds) - lane)
        if min(abs(lane - min(bounds)), abs(lane - max(bounds))) > wall.thickness_px:
            continue
        far_edge = raster.shape[0] - 1
        facade = round(far_edge - lane if reverse else lane)
        found = _outline(raster[::-1] if reverse else raster, facade, span, wall.thickness_px)
        if found is None:
            continue
        left, right, edge, t_left, t_outer, t_right = found
        # Snap a return to an established joint when it agrees with the
        # source within one rail thickness.
        anchors = [getattr(n, axis) for n in nodes.values() if abs(getattr(n, cross) - lane) < 1e-6]
        left_joint = min(anchors, key=lambda x: abs(x - left))
        right_joint = min(anchors, key=lambda x: abs(x - right))
        left = left_joint if abs(left_joint - left) <= 3 else left
        right = right_joint if abs(right_joint - right) <= 3 else right
        edge = far_edge - edge if reverse else edge
        coordinates = [(left, lane), (left, edge), (right, edge), (right, lane)]
        if axis == "y":
            coordinates = [(c, x) for x, c in coordinates]
        # Ignore an outline over walls the extractor has already recovered.
        interior = Polygon(coordinates).buffer(-2)
        if any(interior.intersects(LineString([(nodes[w.a].x, nodes[w.a].y), (nodes[w.b].x, nodes[w.b].y)]))
               for w in model.walls):
            continue
        updated = _attach(model, coordinates, (t_left, t_outer, t_right))
        if updated is not model:
            return updated
    return model
