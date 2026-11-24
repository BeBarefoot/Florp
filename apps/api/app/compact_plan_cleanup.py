"""Remove competing swing fits and fitting-sized enclosed strips on soft scans."""

from collections import Counter
from statistics import median
import math

import numpy as np
from shapely import STRtree
from shapely.geometry import LineString, Polygon
from shapely.ops import unary_union

from .plan_derive import derive


def _same_aperture(a, b):
    start, end = np.array(a)
    first, last = np.array(b)
    width = np.linalg.norm(end - start)
    other_width = np.linalg.norm(last - first)
    if min(width, other_width) < 1:
        return False
    axis = (end - start) / width
    if abs((last - first) @ axis) < 0.96 * other_width:
        return False
    normal = np.array([-axis[1], axis[0]])
    if max(abs((first - start) @ normal), abs((last - start) @ normal)) > 0.32 * min(width, other_width):
        return False
    lo, hi = sorted(((first - start) @ axis, (last - start) @ axis))
    intersection = min(hi, width) - max(lo, 0)
    return intersection >= 0.74 * min(width, other_width)


def _parallel_outlines(walls, nodes, protected, room_walls, door_width):
    """Find thinner outlines beside better-supported masonry runs."""
    lines = [LineString([nodes[wall.a], nodes[wall.b]]) for wall in walls]
    index = STRtree(lines)
    removed = set()
    for i, (wall, line) in enumerate(zip(walls, lines)):
        if wall.id in protected or wall.id in room_walls or line.length < 2:
            continue
        unit = (nodes[wall.b] - nodes[wall.a]) / line.length
        coverage = []
        for j in index.query(line.buffer(0.45 * door_width)):
            other, candidate = walls[j], lines[j]
            if candidate.length < 2 or wall.thickness_px > 0.64 * other.thickness_px:
                continue
            vector = nodes[other.b] - nodes[other.a]
            if abs(vector @ unit) >= 0.985 * candidate.length:
                coverage.append(candidate.buffer(
                    max(other.thickness_px / 2 + 1, 0.42 * door_width),
                    cap_style="flat",
                ))
        if coverage and line.intersection(unary_union(coverage)).length >= 0.8 * line.length:
            removed.add(wall.id)
    return removed


def clean_compact_plan(model):
    # Arc fitting sometimes produces a second parallel span at the open
    # leaf or far face. Keep the stronger, longer fit and its host.
    doors = [o for o in model.openings if o.kind == "door" and o.host_wall_id]
    if not doors:
        return model
    nodes = {n.id: np.array([n.x, n.y]) for n in model.nodes}
    walls = {w.id: w for w in model.walls}
    kept = []
    duplicates = set()
    for door in sorted(doors, key=lambda o: (-o.confidence, -o.width_px)):
        wall = walls[door.host_wall_id]
        start, end = nodes[wall.a], nodes[wall.b]
        direction = (end - start) / math.dist(start, end)
        ends = start + np.array([[door.offset_px], [door.offset_px + door.width_px]]) * direction
        if any(_same_aperture(ends, other) for other in kept):
            duplicates.add(door.id)
        else:
            kept.append(ends)
    openings = [o for o in model.openings if o.id not in duplicates]
    protected = {o.host_wall_id for o in openings}
    removed = {
        o.host_wall_id for o in doors
        if o.id in duplicates and o.host_wall_id not in protected
    }
    memberships = Counter(key for room in model.rooms for key in room.wall_ids)
    removed = {key for key in removed if not memberships[key]}
    # Cabinets and wall outlines can form small sliver faces on a large
    # blurry scan. Require a narrow empty strip and a shared indoor wall.
    # The installed perimeter stays if there is no room on its other side.
    typical_width = median(o.width_px for o in doors if o.id not in duplicates)
    for room in model.rooms:
        if room.area_px2 >= 3 * typical_width**2 or protected.intersection(room.wall_ids):
            continue
        polygon = Polygon([(p.x, p.y) for p in room.polygon])
        if not polygon.is_valid or polygon.is_empty:
            continue
        box = list(polygon.minimum_rotated_rectangle.exterior.coords)
        width = min(math.dist(box[0], box[1]), math.dist(box[1], box[2]))
        if width < 0.85 * typical_width:
            boundary = set(room.wall_ids)
            # Peel the fitting into its largest adjacent space. Removing
            # both sides of the strip would also erase a real partition
            # when a cabinet is drawn back-to-back with that partition.
            for adjacent in sorted(model.rooms, key=lambda other: -other.area_px2):
                shared = boundary.intersection(adjacent.wall_ids)
                if shared and adjacent.area_px2 >= 4 * room.area_px2:
                    removed.update(shared)
                    break
    if not removed and not duplicates:
        updated = model
    else:
        updated = _with_geometry(model, removed, openings)

    room_walls = {
        key for room in updated.rooms if room.area_px2 >= typical_width**2
        for key in room.wall_ids
    }
    outlines = _parallel_outlines(updated.walls, nodes, protected, room_walls, typical_width)
    return _with_geometry(updated, outlines, openings) if outlines else updated


def _with_geometry(model, removed, openings):
    walls = [wall for wall in model.walls if wall.id not in removed]
    used = {node for wall in walls for node in (wall.a, wall.b)}
    updated = derive(model.model_copy(update={
        "walls": walls,
        "nodes": [node for node in model.nodes if node.id in used],
        "openings": openings,
    }))
    observed = {"pruned_fragments", "merged_duplicates", "open_passage"}
    updated.findings.extend(finding for finding in model.findings if finding.category in observed)
    return updated
