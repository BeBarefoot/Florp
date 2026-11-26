"""Recognize furnishings on the source raster before a metric scale is confirmed."""

import cv2
import numpy as np
from shapely.geometry import Point, Polygon

from .drafting_symbols import _edges, _match_score, _tolerant
from .fixture_detection import for_plan
from .plan_model import Pt, RoomSymbol


def _wc_stencil(width):
    height = round(width * 1.7)
    shape = np.zeros((height, width), np.uint8)
    x = width // 2
    radius = x - 2
    bowl = radius + 2
    cv2.ellipse(shape, (x, bowl), (radius, radius), 0, 180, 360, 255, 1)
    for edge in (x - radius, x + radius):
        cv2.line(shape, (edge, bowl), (edge, height - 2), 255, 1)
    for y in (height - 3, height - 7):
        cv2.line(shape, (x - radius, y), (x + radius, y), 255, 1)
    return shape


def _wall_mounted_toilet(gray, polygon, width):
    vertices = np.float32(polygon.exterior.coords)
    x, y, w, h = cv2.boundingRect(vertices)
    pad = round(width / 2)
    x0, y0 = max(0, x - pad), max(0, y - pad)
    patch = gray[y0 : y + h + pad, x0 : x + w + pad]
    if min(patch.shape) < 16:
        return None
    ink = [_tolerant(e) for e in _edges(cv2.createCLAHE(2.0, (4, 4)).apply(patch))]
    choices = []
    for bw in sorted(
        {round(width * ratio) for ratio in (0.81, 0.93, 1.05, 1.17, 1.29)}
    ):
        if bw < 9:
            continue
        template = _wc_stencil(bw)
        for turns, direction in enumerate(((0, 1), (1, 0), (0, -1), (-1, 0))):
            rotated = np.rot90(template, turns)
            rh, rw = rotated.shape
            if rh > patch.shape[0] or rw > patch.shape[1]:
                continue
            channels = [
                (i, e, _tolerant(e))
                for i, e in enumerate(_edges(rotated))
                if e.sum() > 3
            ]
            score = _match_score(ink, channels)
            for _ in range(8):
                _, peak, _, (dx, dy) = cv2.minMaxLoc(score)
                if peak < 0.54:
                    break
                px, py = x0 + dx + rw / 2, y0 + dy + rh / 2
                ox, oy = np.array(direction) * template.shape[0] * 0.42
                if (
                    polygon.contains(Point(px, py))
                    and polygon.boundary.distance(Point(px + ox, py + oy)) <= bw * 0.53
                ):
                    choices.append((peak, px, py, bw, turns))
                radius = max(3, bw // 3)
                score[
                    max(0, dy - radius) : dy + radius + 1,
                    max(0, dx - radius) : dx + radius + 1,
                ] = -1
    for peak, px, py, bw, turns in sorted(choices, reverse=True):
        if peak < 0.575:
            break
        if any(
            other >= 0.54
            and sw != bw
            and angle == turns
            and np.hypot(sx - px, sy - py) < bw * 0.34
            for other, sx, sy, sw, angle in choices
        ):
            return RoomSymbol(
                kind="toilet",
                position=Pt(x=px, y=py),
                width_px=bw,
                depth_px=round(bw * 1.7),
                rotation=(180, 90, 0, -90)[turns],
            )
    return None


def residential_fixtures(image, model, symbols):
    """Use room context to reject spurious matches and retain measured footprints."""
    rooms = [
        (r, Polygon([(p.x, p.y) for p in r.polygon]))
        for r in model.rooms
        if r.room_type not in ("balcony", "garage", "corridor", "kitchen")
    ]
    if not rooms:
        return []
    widths = [
        o.width_px
        for o in model.openings
        if o.kind == "door" and o.status != "rejected" and o.width_px >= 12
    ]
    if not widths and not model.scale.meters_per_pixel:
        return []
    # Used exclusively to size the source-image templates. The output is
    # in pixels, and the plan's calibration stays unset until verified.
    mpp = model.scale.meters_per_pixel or round(0.75 / float(np.median(widths)), 3)
    if not 0.004 <= mpp <= 0.065:
        return []
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    found = []
    wet = set()
    for room, polygon in rooms:
        if (
            polygon.area * mpp**2 > 10 and room.room_type != "bathroom"
        ) or room.room_type == "bedroom":
            continue
        wc = _wall_mounted_toilet(gray, polygon, 0.38 / mpp)
        if wc:
            found.append(wc)
            wet.add(room.id)
    hits = for_plan(
        gray, model, mpp=mpp, kinds={"bed", "wardrobe", "bathtub", "shower", "toilet"}
    )
    hosts = [
        (
            hit,
            next(
                (
                    (room, polygon)
                    for room, polygon in rooms
                    if polygon.contains(Point(hit.x, hit.y))
                ),
                None,
            ),
        )
        for hit in hits
    ]
    # A wall-to-wall bathtub can be crossed by dimensions or plumbing text.
    # Require the short ends and a long side to align with the room boundary.
    tub_rooms = set()
    for hit, host in hosts:
        if hit.kind != "bathtub" or hit.score < 0.40 or host is None:
            continue
        room, polygon = host
        if (
            room.id in tub_rooms
            or room.room_type == "bedroom"
            or polygon.area * mpp**2 > 10
        ):
            continue
        vertical = hit.rotation % 180 == 0
        axis, lateral = ((0, 1), (1, 0)) if vertical else ((1, 0), (0, 1))
        center = np.array([hit.x, hit.y])
        ends = [
            Point(center + np.array(axis) * sign * hit.depth / (2 * mpp))
            for sign in (-1, 1)
        ]
        sides = [
            Point(center + np.array(lateral) * sign * hit.width / (2 * mpp))
            for sign in (-1, 1)
        ]
        if max(polygon.boundary.distance(p) for p in ends) * mpp > 0.22:
            continue
        if min(polygon.boundary.distance(p) for p in sides) * mpp > 0.18:
            continue
        nearby_toilet = any(
            other.kind == "toilet"
            and other.score >= 0.43
            and other_host
            and other_host[0].id == room.id
            and 0.55 < np.hypot(other.x - hit.x, other.y - hit.y) * mpp < 2
            for other, other_host in hosts
        )
        if room.id in wet or nearby_toilet:
            tub_rooms.add(room.id)
            wet.add(room.id)
            found.append(
                RoomSymbol(
                    kind="bathtub",
                    position=Pt(x=hit.x, y=hit.y),
                    width_px=hit.width / mpp,
                    depth_px=hit.depth / mpp,
                    rotation=hit.rotation
                    if hit.rotation <= 180
                    else hit.rotation - 360,
                )
            )
    bed_rooms = set()
    for hit, host in sorted(hosts, key=lambda pair: -pair[0].score):
        if not host or hit.kind == "bathtub":
            continue
        room, polygon = host
        bathroom = room.id in wet or room.room_type == "bathroom"
        if hit.kind == "bed":
            if (
                bathroom
                or room.id in bed_rooms
                or hit.score < 0.49
                or polygon.area * mpp**2 > 28
            ):
                continue
            bed_rooms.add(room.id)
        elif hit.kind == "wardrobe":
            if bathroom or hit.score < 0.41:
                continue
        elif not bathroom or hit.score < {"toilet": 0.55, "shower": 0.51}[hit.kind]:
            continue
        if hit.kind == "toilet" and any(
            s.kind == "toilet" and polygon.contains(Point(s.position.x, s.position.y))
            for s in found
        ):
            continue
        width, depth = hit.width / mpp, hit.depth / mpp
        if any(
            np.hypot(s.position.x - hit.x, s.position.y - hit.y)
            < min(width, depth) * 0.65
            for s in [*symbols, *found]
        ):
            continue
        found.append(
            RoomSymbol(
                kind=hit.kind,
                position=Pt(x=hit.x, y=hit.y),
                width_px=width,
                depth_px=depth,
                rotation=hit.rotation if hit.rotation <= 180 else hit.rotation - 360,
            )
        )
    return found
