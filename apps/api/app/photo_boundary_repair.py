"""Reconnect short, source-backed breaks in photographed wall bands."""
from collections import defaultdict
import math

import cv2
import numpy as np
from shapely import STRtree
from shapely.geometry import LineString, Point, Polygon

from .plan_derive import derive
from .plan_model import Wall


def recover_photo_boundaries(model, image, strips, *, junctions=False):
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
    degree_limit = 3 if junctions else 1
    free = sorted(key for key, linked in incident.items()
                  if 1 <= len(linked) <= degree_limit and all(w.source == "extracted" for w in linked))
    limit = .08 * max(width, height)
    locations = [Point(nodes[key]) for key in free]
    free_index = STRtree(locations)
    pairs = ((a, free[j]) for i, a in enumerate(free)
             for j in sorted(free_index.query(locations[i], predicate="dwithin", distance=limit))
             if j > i)
    for a, b in pairs:
        start, end = nodes[a], nodes[b]
        delta = end - start
        distance = np.linalg.norm(delta)
        if distance < 5:
            continue

        def continuation(key, outward):
            for wall in incident[key]:
                far = nodes[wall.b if wall.a == key else wall.a]
                direction = nodes[key] - far
                if direction @ outward >= .98 * np.linalg.norm(direction) * distance:
                    return wall
            return None

        first, second = continuation(a, delta), continuation(b, -delta)
        if first is None or second is None or first.id == second.id:
            continue
        junction = len(incident[a]) > 1 or len(incident[b]) > 1
        thickness = min(first.thickness_px, second.thickness_px)
        if distance > min((10 if junction else 5) * thickness, limit):
            continue
        if not junction and first.material != second.material:
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
        if junction:
            # Closing between existing junctions requires original masonry across
            # the entire gap. A jamb, a leader or a single rail is insufficient.
            tint = strips.structural_colour[y, x].sum(axis=0) >= max(3, thickness * .35)
            # At a cropped page edge the outer wall face can lie outside
            # the raster. Look for a continuous straight face and an
            # independently paired band in the middle of the missing run.
            axial = abs(along[0]) > .996 or abs(along[1]) > .996
            horizontal = abs(along[0]) > abs(along[1])
            lanes = y if horizontal else x
            lane = round((start[1]+end[1])/2 if horizontal else (start[0]+end[0])/2)
            axis = x if horizontal else y
            edge = min(lane,(height if horizontal else width)-1-lane)
            face = any(strips.ink[np.full_like(axis[0], i),axis[0]].mean() > .97
                       if horizontal else strips.ink[axis[0],np.full_like(axis[0], i)].mean() > .97
                       for i in np.unique(lanes))
            cropped = (axial and edge < thickness and face and
                       strips.boundary_mask[y,x].any(axis=0).mean() >= .35 and band_share >= .60)
            consistent_band |= cropped
            if not cropped and any(chunk.mean() < .85 for chunk in np.array_split(tint, 4)):
                continue
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


def extend_glazed_returns(model, image):
    """Follow parallel frame rails beyond a terminal masonry pier on a site facade."""
    nodes = {n.id: n for n in model.nodes}
    incident = defaultdict(list)
    for wall in model.walls:
        incident[wall.a].append(wall)
        incident[wall.b].append(wall)
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY).astype(float)
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    edited = {}
    hosts = {o.host_wall_id for o in model.openings}
    footprint = (
        Polygon([(p.x, p.y) for p in model.envelope]) if model.envelope else None
    )
    for key, walls in incident.items():
        if len(walls) != 1 or walls[0].id in hosts:
            continue
        wall = walls[0]
        other = wall.b if wall.a == key else wall.a
        if len(incident[other]) < 2:
            continue
        p, q = nodes[key], nodes[other]
        vertical = abs(p.x - q.x) < 0.1
        if not vertical and abs(p.y - q.y) > 0.1:
            continue
        width = wall.thickness_px
        if width < 5 or math.hypot(p.x - q.x, p.y - q.y) > 4 * width:
            continue
        pos, lane = (p.y, p.x) if vertical else (p.x, p.y)
        sign = 1 if pos > (q.y if vertical else q.x) else -1
        along = np.rint(pos + sign * np.arange(1, round(12 * width) + 1)).astype(int)
        across = np.arange(round(lane - width), round(lane + width) + 1)
        raster = gray if vertical else gray.T
        along = along[(along >= 0) & (along < raster.shape[0])]
        if (
            along.size < 3 * width
            or across.min() < 0
            or across.max() >= raster.shape[1]
        ):
            continue
        patch = raster[np.ix_(along, across)]
        # Both dark rails must stand out from the lighter space between them.
        count = max(5, round(width))
        profile = np.median(patch[:count], axis=0)
        best = None
        for i in range(1, len(across) - 4):
            for j in range(i + 4, len(across) - 1):
                if (
                    not 0.45 * width <= j - i <= 1.45 * width
                    or abs((across[i] + across[j]) / 2 - lane) > width * 0.35
                ):
                    continue
                contrast = profile[i + 1 : j].max() - max(profile[i], profile[j])
                if best is None or contrast > best[0]:
                    best = (contrast, i, j)
        if best is None or best[0] < 24:
            continue
        _, i, j = best
        middle = patch[:, i + 1 : j].max(axis=1)
        rails = (
            middle
            - np.maximum(
                patch[:, i - 1 : i + 2].min(axis=1), patch[:, j - 1 : j + 2].min(axis=1)
            )
            > 18
        )
        saturation = (hsv[:, :, 1] if vertical else hsv[:, :, 1].T)[
            np.ix_(along, across[i : j + 1])
        ]
        rails &= np.median(saturation, axis=1) < 60
        failures = np.flatnonzero(
            np.convolve((~rails).astype(int), np.ones(5, int), "valid") >= 4
        )
        length = int(failures[0]) if failures.size else len(along)
        if length < 2 * width or rails[:length].mean() < 0.82:
            continue
        endpoint = p.model_copy(
            update={("y" if vertical else "x"): float(along[length - 1])}
        )
        line = LineString([(p.x, p.y), (endpoint.x, endpoint.y)])
        if footprint is not None and not footprint.covers(line):
            continue
        if any(
            line.intersects(
                LineString([(nodes[w.a].x, nodes[w.a].y), (nodes[w.b].x, nodes[w.b].y)])
            )
            for w in model.walls
            if w.id != wall.id
        ):
            continue
        edited[key] = endpoint
    return (
        derive(
            model.model_copy(
                update={"nodes": [edited.get(n.id, n) for n in model.nodes]}
            )
        )
        if edited
        else model
    )
