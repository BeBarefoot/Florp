"""Isolated local extraction; no scale prerequisite, no generated geometry.

Pipeline: ink_layers (wall strips vs thin ink) -> envelope (main building) ->
structural runs on the clipped strips -> ink-supported extension -> gap-first
openings (detector boxes only adjust confidence).
"""

import argparse
import json
import math
from pathlib import Path
import cv2, numpy as np
from .plan_workspace import Document, Segment, Point
from .deterministic_blueprint.preprocess import decode


def _remeasure(objects, strip_mask, classes):
    """Thickness from the strip's own local width along each run, not from scan-band extents."""
    for o in objects:
        # structural_runs returns axial segments here. Scan both faces across
        # the interior of the run; intersections near its ends inflate widths.
        horizontal = o.start.y == o.end.y
        axis, cross = ("x", "y") if horizontal else ("y", "x")
        mask = strip_mask.T if horizontal else strip_mask
        lane = round(getattr(o.start, cross))
        along = np.linspace(getattr(o.start, axis), getattr(o.end, axis), 21)[3:-3]
        radius = min(512, max(12, math.ceil(2 * max(max(classes), o.thickness_px))))
        lo, hi = max(0, lane - radius), min(mask.shape[1], lane + radius + 1)
        widths, centers = [], []
        for sample in np.rint(along).astype(int).clip(0, mask.shape[0] - 1):
            occupied = mask[sample, lo:hi] > 0
            if not occupied[lane - lo]:
                continue
            left = np.flatnonzero(~occupied[: lane - lo])
            right = np.flatnonzero(~occupied[lane - lo + 1 :])
            if (not left.size and lo > 0) or (not right.size and hi < mask.shape[1]):
                continue
            a = lo + left[-1] + 1 if left.size else lo
            b = lane + right[0] if right.size else hi - 1
            widths.append(b - a + 1)
            centers.append((a + b) / 2)
        if len(widths) >= len(along) // 2 + 1:
            o.thickness_px = float(np.clip(np.median(widths), 1, 1000))
            center = float(np.median(centers))
            setattr(o.start, cross, center)
            setattr(o.end, cross, center)


def _trim_photo_edge_leaders(objects, supported, wall_width):
    """Clip thin unsupported leaders that run from the page edge into a wall."""
    h, w = supported.shape
    for run in objects:
        if run.kind != "wall" or run.id.startswith("gap-host-") or run.thickness_px > max(2, 0.4 * wall_width):
            continue
        a, b = run.start, run.end
        vertical = abs(a.x - b.x) < 0.01
        if not vertical and abs(a.y - b.y) >= 0.01:
            continue
        axis, cross = ("y", "x") if vertical else ("x", "y")
        size = h if vertical else w
        lane = getattr(a, cross)
        if not 0 <= round(lane) < (w if vertical else h):
            continue
        for edge, inside in ((a, b), (b, a)):
            start, stop = getattr(edge, axis), getattr(inside, axis)
            if min(start, size - 1 - start) > 2:
                continue
            sign = 1 if stop > start else -1
            joints = []
            for other in objects:
                if other is run or other.kind != "wall" or other.thickness_px < 2 * run.thickness_px:
                    continue
                p, q = other.start, other.end
                if abs(getattr(p, axis) - getattr(q, axis)) > 0.1:
                    continue
                l, r = sorted((getattr(p, cross), getattr(q, cross)))
                hit = getattr(p, axis)
                pad = max(2, 0.65 * other.thickness_px) if other.id.startswith("gap-host-") else 2
                if l - pad <= lane <= r + pad and 2 * wall_width < sign * (hit - start) < abs(stop - start) - 2:
                    joints.append(hit)
            for hit in sorted(joints, key=lambda v: abs(v - start)):
                along = np.arange(max(0, math.ceil(min(start, hit))), min(size, math.floor(max(start, hit))))
                if not along.size:
                    continue
                across = np.arange(max(0, round(lane) - 2), min(w if vertical else h, round(lane) + 3))
                if vertical:
                    patch = supported[np.ix_(along, across)]
                else:
                    patch = supported[np.ix_(across, along)]
                if float(patch.mean()) < 0.08:
                    setattr(edge, axis, hit)
                    break


def _detector_boxes(path, w, h):
    from .openings import Box

    try:
        from .pretrained_detector import detect_objects

        result = detect_objects(Path(path), w, h)
        return [
            Box(b.category, b.x1, b.y1, b.x2, b.y2, float(b.confidence))
            for b in result.boxes
            if b.category in ("door", "window")
        ], True
    except Exception:
        return [], False


def recover_notched_crop(polygon, region, structural_ink, wall_width):
    """Keep long source-supported faces lost inside an inferred crop's notches."""
    hull = cv2.convexHull(np.rint(polygon).astype(np.int32)).reshape(-1, 2)
    filled = np.zeros(region.shape, np.uint8)
    cv2.fillPoly(filled, [hull], 1)
    missing = ((filled > 0) & ~region & structural_ink).astype(np.uint8)
    length = max(12, round(4*wall_width))
    for size in ((1,length), (length,1)):
        if cv2.morphologyEx(missing, cv2.MORPH_OPEN, np.ones(size,np.uint8)).any():
            return [tuple(map(float,p)) for p in hull], filled.astype(bool) | region
    return polygon, region


def dimension_framed_crop(strips, image):
    """Locate a facade between two outboard dashed dimension lines on a coloured sheet."""
    if strips.boundary_mask is None or not strips.blue.any():
        return None
    h, w = image.shape[:2]
    dash = strips.rejected.get("dimension_dashes")
    if dash is None:
        return None
    cols = np.flatnonzero(dash.sum(axis=0) > 0.35 * h)
    if not len(cols):
        return None
    clusters = np.split(cols, np.flatnonzero(np.diff(cols) > 2) + 1)
    if len(clusters) != 2:
        return None
    left, right = int(clusters[0][-1]) + 1, int(clusters[1][0])
    if right - left < 0.35 * w or not strips.blue[:, left:right].any():
        return None
    ink = (strips.boundary_mask | strips.blue)[:, left:right].astype(np.uint8)
    # Long horizontal material runs distinguish facades from lettering.
    bands = cv2.morphologyEx(
        ink,
        cv2.MORPH_OPEN,
        np.ones((2, max(12, round(0.025 * (right - left)))), np.uint8),
    )
    rows = np.flatnonzero(bands.sum(axis=1) > 0.09 * (right - left))
    if not rows.size or np.ptp(rows) < 0.4 * h:
        return None
    groups = np.split(rows, np.flatnonzero(np.diff(rows) > 4) + 1)
    if len(groups) < 3:
        return None
    # Short piers at the end of a glazed facade can be much shorter than
    # the long bands that locate its rows. Include solid tint on those rows.
    facade = strips.structural_colour[:, left:right].astype(np.uint8)
    ends = cv2.morphologyEx(facade, cv2.MORPH_OPEN, np.ones((4, 8), np.uint8))
    xs = np.flatnonzero((bands[rows] | ends[rows]).any(axis=0))
    pad = max(3, round(0.55 * strips.stats["w_wall"]))
    x1, x2 = (
        max(left, left + int(xs.min()) - pad),
        min(right, left + int(xs.max()) + pad),
    )
    y1, y2 = max(0, int(rows.min()) - pad), min(h - 1, int(rows.max()) + pad)
    return [(x1, y1), (x2, y1), (x2, y2), (x1, y2)]


def build(path, roi=None, *, plan_id=None):
    image = decode(Path(path).read_bytes())
    h, w = image.shape[:2]
    from .config import settings
    from .plan_reconstruct import extend_dangling, reconstruct

    if settings.workspace_semantic_source or settings.workspace_semantic_weights:
        from .semantic_workspace import build as semantic_build

        doc = semantic_build(image)
        return reconstruct(doc, plan_id) if plan_id is not None else doc
    from .ink_layers import wall_strips
    from .envelope import building_envelope, mask_from_polygon
    from .structural_runs import structural_runs, join_intersections
    from . import openings as gap_openings

    notes = []
    strips = wall_strips(image)
    stats = strips.stats
    w_wall = float(stats["w_wall"])
    framed = None
    if roi:
        polygon = [(float(x), float(y)) for x, y in roi]
        env_mask = mask_from_polygon(polygon, image.shape)
    else:
        polygon, env_mask = building_envelope(strips.mask, w_wall)
        if polygon and stats.get("coloured_walls") and strips.boundary_mask is not None:
            polygon, env_mask = recover_notched_crop(polygon, env_mask, strips.boundary_mask | strips.blue, w_wall)
        framed = dimension_framed_crop(strips, image)
        if framed:
            polygon = framed
            env_mask = mask_from_polygon(polygon,image.shape)
    outside = strips.mask.astype(bool) & ~env_mask
    if outside.any():
        n, _, st, _ = cv2.connectedComponentsWithStats(outside.astype(np.uint8), connectivity=8)
        long = int(sum(max(s[2], s[3]) >= 4 * w_wall for s in st[1:]))
        if long:
            notes.append(f"{long} marks outside the building ignored.")
    for name in ("red", "blue", "dark"):
        setattr(strips, name, getattr(strips, name) & env_mask)
    mask = strips.mask
    red, blue = strips.red | strips.dark, strips.blue
    monochrome = False
    if not np.any(mask):
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        ink = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)[1]
        mask = cv2.morphologyEx(ink, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
        mask[~env_mask] = 0
        monochrome = True
        notes.append("No wall strips found; monochrome fallback: review structural runs against the source.")
    classes = stats["classes"]
    coloured = bool(strips.red.any() or strips.blue.any())
    objects = structural_runs(
        mask,
        min_length=max(7, round(0.8 * min(classes))) if coloured else max(7, int(1.4 * min(classes))),
        pier_factor=1.0 if coloured else 1.4,
    )
    _remeasure(objects, mask, classes)
    exterior_zone = None
    if polygon is not None and not roi and not framed:
        k = int(8 * w_wall) | 1
        exterior_zone = cv2.erode(env_mask.astype(np.uint8), np.ones((k, k), np.uint8)) == 0
    for i, o in enumerate(objects):
        o.id = f"wall-{i}"
        o.uncertain = monochrome
        xs = np.rint(np.linspace(o.start.x, o.end.x, 25)).astype(int).clip(0, w - 1)
        ys = np.rint(np.linspace(o.start.y, o.end.y, 25)).astype(int).clip(0, h - 1)
        o.material = "concrete" if np.mean(blue[ys, xs] > 0) > 0.5 else "block"
        if strips.boundary_mask is not None:
            o.boundary_supported = bool(np.mean(strips.boundary_mask[ys, xs]) >= 0.8)
        if exterior_zone is not None:
            o.exterior = bool(exterior_zone[int(ys[12]), int(xs[12])])
    # Preserve isolated genuine diagonal runs rather than forcing Manhattan axes.
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    for contour in sorted(contours, key=cv2.contourArea, reverse=True)[:1000]:
        if len(contour) < 3:
            continue
        (_, _), (bw, bh), _ = cv2.minAreaRect(contour)
        long, short = max(bw, bh), min(bw, bh)
        if (
            short < 2
            or long < 20
            or long / max(short, 1) < 4
            or cv2.contourArea(contour) < long * short * 0.45
        ):
            continue
        vx, vy, x0, y0 = map(
            float, cv2.fitLine(contour, cv2.DIST_L2, 0, 0.01, 0.01).reshape(-1)
        )
        angle = abs(np.degrees(np.arctan2(vy, vx))) % 90
        if min(angle, 90 - angle) < 8:
            continue
        pts = contour.reshape(-1, 2)
        projection = (pts[:, 0] - x0) * vx + (pts[:, 1] - y0) * vy
        ends = [
            Point(
                x=float(np.clip(x0 + t * vx, 0, w - 1)),
                y=float(np.clip(y0 + t * vy, 0, h - 1)),
            )
            for t in (projection.min(), projection.max())
        ]
        objects.append(
            Segment(
                id=f"diagonal-{len(objects)}",
                start=ends[0],
                end=ends[1],
                thickness_px=float(short),
                uncertain=True,
            )
        )
    objects = join_intersections(objects, image.shape)
    if strips.boundary_mask is not None:
        _trim_photo_edge_leaders(objects, strips.boundary_mask | strips.blue, w_wall)
    solid = None
    if strips.ink is not None:
        # On coloured plans, raw ink also includes dimension leaders and
        # furniture. It cannot justify extending a structural wall.
        extension_ink = (mask > 0) if (strips.red.any() or strips.blue.any()) else strips.ink | (mask > 0)
        material_ink = None
        if strips.boundary_mask is not None and strips.structural_colour is not None:
            # Only a band of original material can recover an extension
            # lost to a broken outline; neutral ink and thin strokes cannot.
            solid = cv2.morphologyEx(
                strips.structural_colour.astype(np.uint8), cv2.MORPH_OPEN, np.ones((3, 3), np.uint8)
            ) > 0
            material_ink = (extension_ink | solid) & env_mask
        extend_dangling(objects, extension_ink & env_mask, material_ink=material_ink)
    boxes, detector_ok = _detector_boxes(path, w, h)
    if not detector_ok:
        notes.append(
            "Local detector unavailable; openings come from wall gaps only and need review against the original. Add missing openings with two clicks."
        )
    found = gap_openings.detect(
        image, [o for o in objects if o.kind == "wall"], strips, boxes, exterior_zone, framed_site=bool(framed)
    )
    # Photo void probes extend past the ends of walls. A crop must constrain
    # the inferred aperture and its generated host as well as the masonry.
    if polygon:

        def inside(point):
            x, y = round(point.x), round(point.y)
            return 0 <= x < w and 0 <= y < h and env_mask[y, x]

        found.objects = [o for o in found.objects if inside(o.start) and inside(o.end)]
    objects.extend(found.objects)
    if solid is not None:
        # A detected swing provides the missing jamb, but the adjoining
        # masonry can still be absent from the strip mask. Extend only the
        # host wall, not the opening, across an uninterrupted material band.
        door_flanks = {
            o.host_id: 1.25 * math.hypot(o.end.x - o.start.x, o.end.y - o.start.y)
            for o in found.objects
            if o.kind == "door" and o.boundary_supported and o.host_id
            and (o.confidence or 0) >= 0.85
        }
        if door_flanks:
            extend_dangling(objects, solid & env_mask, cover=0.9, reach_by_wall=door_flanks)
    if strips.boundary_mask is not None:
        # A glazed facade may have no surviving raw horizontal run at its
        # corner. Its verified opening host can now identify the junction.
        _trim_photo_edge_leaders(objects, strips.boundary_mask | strips.blue, w_wall)
    from .capped_returns import detect_returns
    from .stair_detection import detect_stairs

    stairs = detect_stairs(image, np.asarray(polygon, dtype=np.float32) if roi else None)

    doc = Document(
        width=w,
        height=h,
        objects=objects,
        envelope=[Point(x=x, y=y) for x, y in polygon] if polygon else None,
        passages=[Point(x=x, y=y) for x, y in found.passages[:500]],
        wall_returns=detect_returns(image, strips),
        stairs=stairs,
        photo_wall_evidence=strips.boundary_mask is not None,
        warnings=notes
        + ["Flat, uniformly scaled source assumed. Heights use editable defaults."],
    )

    return reconstruct(doc, plan_id, strips=strips, image=image) if plan_id is not None else doc


if __name__ == "__main__":
    cv2.setNumThreads(8)
    parser = argparse.ArgumentParser()
    parser.add_argument("path", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("roi", type=Path, nargs="?")
    parser.add_argument("--plan-id")
    args = parser.parse_args()
    roi = json.loads(args.roi.read_text()) if args.roi else None
    args.output.write_text(build(args.path, roi, plan_id=args.plan_id).model_dump_json())
