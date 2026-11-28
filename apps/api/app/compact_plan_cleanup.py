"""Remove competing swing fits and fitting-sized enclosed strips on soft scans."""

from collections import Counter
from hashlib import sha256
from statistics import median
import math

import cv2
import numpy as np
from shapely import STRtree
from shapely.geometry import LineString, Point, Polygon
from shapely.ops import unary_union

from .ink_layers import _local_paper
from .neutral_partitions import _fill_support
from .plan_derive import derive, faces
from .plan_model import Node, Wall


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


def _shallow_fittings(model, walls, nodes, protected, door_width):
    """Find thin, three-sided outlines attached to a much thicker wall."""
    removed = set()
    incidence = Counter(node for wall in walls.values() for node in (wall.a, wall.b))
    for face in faces(model):
        ids = {key for _, key in face}
        if len(ids) < 4 or len(ids) != len(face) or ids.intersection(protected):
            continue
        polygon = Polygon([nodes[key] for key, _ in face])
        if not polygon.is_valid or polygon.area > 3 * door_width**2:
            continue
        longest = sorted(ids, key=lambda key: (-walls[key].thickness_px, key))
        backing = walls[longest[0]]
        thin = [walls[key] for key in longest[1:]]
        if backing.thickness_px < 2.5 * max(wall.thickness_px for wall in thin):
            continue
        a, b = nodes[backing.a], nodes[backing.b]
        run = LineString([a, b])
        if run.length < door_width or not run.buffer(0.72 * door_width).covers(polygon):
            continue
        free = {node for wall in thin for node in (wall.a, wall.b)} - {backing.a, backing.b}
        if all(incidence[node] == 2 for node in free):
            removed.update(wall.id for wall in thin)
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
        # An inset can cross itself where a thick wall meets a short
        # fitting edge. Its enclosing rectangle is still well defined.
        box = polygon.minimum_rotated_rectangle
        if box.geom_type != "Polygon" or box.is_empty:
            continue
        corners = list(box.exterior.coords)
        width = min(math.dist(corners[0], corners[1]), math.dist(corners[1], corners[2]))
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
    outlines.update(_shallow_fittings(
        updated, {wall.id: wall for wall in updated.walls}, nodes, protected, typical_width,
    ))
    return _with_geometry(updated, outlines, openings) if outlines else updated


def reconnect_soft_scan_jambs(model, image):
    """Close short, drawn masonry seams at the ends of fitted door hosts."""
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    paper = _local_paper(gray)
    fill = (gray >= 0.45 * paper) & (gray <= 0.90 * paper)
    nodes = {node.id: node for node in model.nodes}
    points = {node.id: np.array([node.x, node.y]) for node in model.nodes}
    walls = {wall.id: wall for wall in model.walls}
    openings = list(model.openings)
    hosts = {op.host_wall_id: op for op in openings
             if op.kind == "door" and op.host_wall_id and op.status != "rejected"}
    degrees = Counter(key for wall in walls.values() for key in (wall.a, wall.b))
    changed = False
    for key, door in hosts.items():
        original = walls[key]
        for start, far in ((original.a, original.b), (original.b, original.a)):
            if degrees[start] != 1 or len(walls) > 9998 or len(nodes) >= 20000:
                continue
            pos, other = points[start], points[far]
            unit = (pos - other) / math.dist(pos, other)
            reach = min(18, 0.4 * door.width_px)
            nearby = []
            for target in walls.values():
                if target.id == key:
                    continue
                line = LineString([points[target.a], points[target.b]])
                anchor = Point(pos)
                if not line.length or line.distance(anchor) > reach:
                    continue
                offset = line.project(anchor)
                if target.id in hosts and 1e-6 < offset < line.length - 1e-6:
                    continue
                hit = np.array(line.interpolate(offset).coords[0])
                delta = hit - pos
                length = math.dist(hit, pos)
                if not 0.75 <= length <= reach or unit @ delta < 0.55 * length:
                    continue
                target_openings = [op for op in openings if op.host_wall_id == target.id]
                if any(op.offset_px < offset < op.offset_px + op.width_px for op in target_openings):
                    continue
                bridge = LineString([pos, hit])
                width = min(target.thickness_px, original.thickness_px)
                if _fill_support(fill, bridge, width) >= 0.85:
                    nearby.append((length, target.id, offset, hit, width, line.length, bridge))
            if not nearby:
                continue
            _, target_id, cut, hit, width, target_length, bridge = min(nearby, key=lambda row: row[:2])
            target = walls[target_id]
            interior = LineString([bridge.interpolate(t, normalized=True) for t in (0.05, 0.95)])
            if any(interior.intersects(LineString([points[w.a], points[w.b]])) for w in walls.values()):
                continue
            token = sha256(f"{start}:{target_id}".encode()).hexdigest()[:20]
            joint = target.a if cut < 1e-6 else target.b if target_length - cut < 1e-6 else None
            if joint is None:
                joint = f"seam-{token}-node"
                nodes[joint] = Node(id=joint, x=float(hit[0]), y=float(hit[1]))
                points[joint] = hit
                split = f"seam-{token}-split"
                walls[target.id] = target.model_copy(update={"b": joint})
                walls[split] = target.model_copy(update={"id": split, "a": joint})
                openings = [
                    op.model_copy(update={"host_wall_id": split, "offset_px": op.offset_px - cut})
                    if op.host_wall_id == target.id and op.offset_px >= cut else op
                    for op in openings
                ]
                degrees[joint] = 2
            seam = f"seam-{token}"
            walls[seam] = Wall(
                id=seam, a=start, b=joint, thickness_px=width, confidence=0.85,
                material=target.material, height_m=target.height_m,
            )
            degrees[start] += 1
            degrees[joint] += 1
            changed = True
    if not changed:
        return model
    updated = model.model_copy(update={
        "walls": list(walls.values()), "nodes": list(nodes.values()), "openings": openings,
    })
    return _with_geometry(updated, set(), openings)


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
