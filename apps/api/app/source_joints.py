"""Recover supported missing wall flanks in an existing editable plan."""
import math
import cv2
import numpy as np
from shapely.geometry import LineString
from .plan_model import PlanModel
from .wall_alignment import align_walls


def close_source_joints(model: PlanModel, image, *, recover_missing=False) -> PlanModel:
    from .ink_layers import wall_strips

    if image.shape[:2] != (model.image_transform.height, model.image_transform.width):
        raise ValueError("Source dimensions changed")
    strips = wall_strips(image)
    # Dark plans already use their full wall mask. Do not turn furniture
    # strokes into authorization for a new structural connection.
    if strips.structural_colour is None or strips.boundary_mask is None:
        return align_walls(model)
    colour = cv2.morphologyEx(
        strips.structural_colour.astype(np.uint8), cv2.MORPH_OPEN, np.ones((3, 3), np.uint8)
    ) > 0
    # The extraction mask may include morphological bridges over doorways.
    # Only original tint and locally paired boundaries authorize an extension.
    source = colour
    model = align_walls(model)
    nodes = {n.id: n.model_copy(deep=True) for n in model.nodes}
    walls = {w.id: w for w in model.walls}
    incident = {n: [] for n in nodes}
    for w in walls.values():
        incident[w.a].append(w)
        incident[w.b].append(w)

    def xy(n):
        return (n.x, n.y)

    opening_paths = []
    for o in model.openings:
        if o.status == "rejected":
            continue
        host = walls.get(o.host_wall_id)
        if host:
            a, b = nodes[host.a], nodes[host.b]
            length = math.dist(xy(a), xy(b))
            if length < 1e-6:
                continue
            ux, uy = (b.x - a.x) / length, (b.y - a.y) / length
            span = [(a.x + ux * d, a.y + uy * d) for d in (o.offset_px, o.offset_px + o.width_px)]
        elif o.span:
            span = [xy(p) for p in o.span]
        else:
            continue
        opening_paths.append((o.host_wall_id, LineString(span)))

    for key in sorted(nodes):
        linked = incident[key]
        if len(linked) != 1:
            continue
        wall = linked[0]
        if wall.source != "extracted":
            continue
        p = nodes[key]
        far = nodes[wall.b if key == wall.a else wall.a]
        dx, dy = p.x - far.x, p.y - far.y
        horizontal = abs(dy) < 1e-5
        if not horizontal and abs(dx) >= 1e-5:
            continue
        along, cross = ("x", "y") if horizontal else ("y", "x")
        sign = 1 if getattr(p, along) > getattr(far, along) else -1
        choices = []
        for other in walls.values():
            if other.id == wall.id:
                continue
            a, b = nodes[other.a], nodes[other.b]
            lane = getattr(p, cross)
            if abs(getattr(a, along) - getattr(b, along)) < 1e-5:
                # A perpendicular wall crossing this lane.
                low, high = sorted((getattr(a, cross), getattr(b, cross)))
                if not low - other.thickness_px / 2 <= lane <= high + other.thickness_px / 2:
                    continue
                destination = getattr(a, along)
            elif (abs(getattr(a, cross) - getattr(b, cross)) < 1e-5
                  and abs(getattr(a, cross) - lane) <= min(4.5, 0.5 * max(wall.thickness_px, other.thickness_px))):
                # Facing collinear fragments of the same run. Never bridge
                # overlapping parallel walls or jump across a nearer one.
                distances = [(getattr(n, along) - getattr(p, along)) * sign for n in (a, b)]
                if min(distances) <= 0:
                    continue
                destination = getattr((a, b)[distances.index(min(distances))], along)
            else:
                continue
            distance = (destination - getattr(p, along)) * sign
            if 1e-5 < distance <= min(4 * wall.thickness_px, 0.08 * max(image.shape[:2])):
                choices.append((distance, other.id, destination))
        if not choices:
            continue
        distance, _, target = min(choices)
        q = p.model_copy(update={along: target})
        path = LineString([xy(p), xy(q)])
        # Any recorded aperture vetoes a repair. Trim endpoint tolerance so
        # simply abutting the jamb of a hosted opening is allowed.
        inner = LineString([path.interpolate(min(1, distance / 4)), path.interpolate(max(distance - 1, 3 * distance / 4))])
        if any(inner.distance(aperture) < max(1.5, wall.thickness_px / 4)
               for host_id, aperture in opening_paths if host_id != wall.id):
            continue
        # Jamb outlines can sit a pixel outside the coloured fill. Test the
        # interior of the seam; recorded apertures were checked above.
        count = max(4, math.ceil(inner.length))
        first, last = inner.coords
        xs = np.linspace(first[0], last[0], count)
        ys = np.linspace(first[1], last[1], count)
        # Require a band of source material, not a single dimension stroke.
        radius = max(1, min(4, int(wall.thickness_px / 3)))
        samples = []
        h, w = source.shape
        for offset in range(-radius, radius + 1):
            xi = np.rint(xs + (0 if horizontal else offset)).astype(int)
            yi = np.rint(ys + (offset if horizontal else 0)).astype(int)
            valid = (xi >= 0) & (xi < w) & (yi >= 0) & (yi < h)
            samples.append(valid & source[yi.clip(0, h - 1), xi.clip(0, w - 1)])
        evidence = np.stack(samples).sum(axis=0) >= 3
        if evidence.mean() < 0.9 or any(chunk.mean() < 0.75 for chunk in np.array_split(evidence, 4)):
            continue
        # Keep any hosted opening at its original image-space position.
        delta = distance if wall.a == key else 0
        if delta:
            model = model.model_copy(update={"openings": [
                o.model_copy(update={"offset_px": o.offset_px + delta}) if o.host_wall_id == wall.id else o
                for o in model.openings
            ]})
        nodes[key] = q

    # Move only free ends. Normal alignment then creates shared corner/T nodes,
    # keeping the repair in the same graph used by all exports.
    repaired = model.model_copy(update={"nodes": list(nodes.values())})
    repaired = align_walls(repaired)
    if recover_missing:
        from .capped_returns import detect_returns, restore_returns

        from .photo_door_repairs import repair_photo_doors

        repaired = repair_photo_doors(restore_returns(repaired, detect_returns(image, strips)), strips)
    return repaired
