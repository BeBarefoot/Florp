"""Reconnect short, source-backed breaks in photographed wall bands."""
from collections import defaultdict

import cv2
import numpy as np
from shapely import STRtree
from shapely.geometry import LineString, Point, Polygon

from .plan_derive import derive
from .plan_model import Wall


def recover_photo_boundaries(model, image, strips):
    if (not strips.stats.get("coloured_walls") or strips.boundary_mask is None
            or strips.structural_colour is None or strips.ink is None):
        return model

    nodes = {n.id: np.array([n.x, n.y]) for n in model.nodes}
    incident = defaultdict(list)
    paths = {}
    for wall in model.walls:
        incident[wall.a].append(wall)
        incident[wall.b].append(wall)
        paths[wall.id] = LineString([nodes[wall.a], nodes[wall.b]])
    structures = STRtree(list(paths.values()))
    apertures = []
    window_hosts = defaultdict(list)
    for opening in model.openings:
        if opening.status == "rejected":
            continue
        host = paths.get(opening.host_wall_id)
        if host is not None:
            aperture = LineString([host.interpolate(opening.offset_px),
                                   host.interpolate(opening.offset_px + opening.width_px)])
            apertures.append(aperture)
            if opening.kind == "window":
                window_hosts[opening.host_wall_id].append(aperture)
        elif opening.span:
            apertures.append(LineString([(p.x, p.y) for p in opening.span]))
    openings = STRtree(apertures)
    decoration = cv2.inRange(cv2.cvtColor(image, cv2.COLOR_BGR2HSV), (18, 55, 90), (42, 255, 255)) > 0
    # Work with solid band evidence, and keep thin ink separate for the
    # stronger contextual test at a decoration crossing a facade.
    material = (strips.mask > 0) | (strips.structural_colour > 0)
    height, width = material.shape
    envelope = Polygon([(p.x, p.y) for p in model.envelope]) if model.envelope else None

    candidates = []
    free = sorted(key for key, linked in incident.items()
                  if len(linked) == 1 and linked[0].source == "extracted")
    limit = .08 * max(width, height)
    locations = [Point(nodes[key]) for key in free]
    free_index = STRtree(locations)
    pairs = ((a, free[j]) for i, a in enumerate(free)
             for j in sorted(free_index.query(locations[i], predicate="dwithin", distance=limit))
             if j > i)
    for a, b in pairs:
        first, second = incident[a][0], incident[b][0]
        if first.id == second.id or first.material != second.material:
            continue
        start, end = nodes[a], nodes[b]
        delta = end - start
        distance = np.linalg.norm(delta)
        thickness = min(first.thickness_px, second.thickness_px)
        if not 5 <= distance <= min(5 * thickness, limit):
            continue
        along = delta / distance
        normal = np.array([-along[1], along[0]])
        first_far = nodes[first.b if first.a == a else first.a]
        second_far = nodes[second.b if second.a == b else second.a]
        directions = [start - first_far, second_far - end]
        if any(v @ along < .98 * np.linalg.norm(v) or np.linalg.norm(v) < thickness for v in directions):
            continue
        # Ignore contacts at the two jambs; never join across an actual
        # opening or a third wall in the middle of the span.
        interior = LineString([start + 2 * along, end - 2 * along])
        if envelope is not None and not envelope.covers(interior):
            continue
        if len(structures.query(interior, predicate="intersects")) or len(openings.query(interior, predicate="intersects")):
            continue
        samples = start + np.linspace(.02, .98, int(np.ceil(distance)))[:, None] * delta
        offsets = np.arange(-int(thickness / 2), int(thickness / 2) + 1)
        x, y = np.rint(samples[None, :, :] + offsets[:, None, None] * normal).astype(int).transpose(2, 0, 1)
        x, y = x.clip(0, width - 1), y.clip(0, height - 1)
        ink_length = strips.ink[y, x].mean(axis=1).max()
        band_share = (material[y, x].sum(axis=0) >= max(3, thickness * .25)).mean()
        consistent_band = band_share >= .6 and ink_length >= .8
        # A decorative fill can hide masonry tint between two windows.
        # It takes a continuous drawn rail PLUS paired source window hosts
        # to infer the short wall between them.
        decorated_facade = (
            all(any(at.distance(aperture) <= thickness / 2 for aperture in window_hosts[wall.id])
                for wall, at in ((first, Point(start)), (second, Point(end))))
            and decoration[y, x].mean() >= .5 and ink_length >= .85
        )
        if consistent_band or decorated_facade:
            candidates.append((distance, Wall(
                id=f"photo-join-{a}-{b}", a=a, b=b,
                thickness_px=thickness, material=first.material, confidence=.85,
            )))

    joins, used, new_paths = [], set(), []
    for _, wall in sorted(candidates, key=lambda item: (item[0], item[1].id)):
        if wall.a in used or wall.b in used:
            continue
        line = LineString([nodes[wall.a], nodes[wall.b]])
        if any(line.intersects(other) for other in new_paths):
            continue
        joins.append(wall)
        used.update((wall.a, wall.b))
        new_paths.append(line)
    if not joins:
        return model
    recovered = derive(model.model_copy(update={"walls": [*model.walls, *joins]}))
    room_edges = {key for room in recovered.rooms
                  if Polygon([(p.x, p.y) for p in room.polygon]).is_valid
                  for key in room.wall_ids}
    useful = [wall for wall in joins if wall.id in room_edges]
    if not useful:
        return model
    if useful != joins:
        return derive(model.model_copy(update={"walls": [*model.walls, *useful]}))
    return recovered
