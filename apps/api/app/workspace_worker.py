"""Isolated local extraction; no scale prerequisite, no generated geometry.

Pipeline: ink_layers (wall strips vs thin ink) -> envelope (main building) ->
structural runs on the clipped strips -> ink-supported extension -> gap-first
openings (detector boxes only adjust confidence).
"""

import json
import sys
from pathlib import Path
import cv2, numpy as np
from .plan_workspace import Document, Segment, Point
from .deterministic_blueprint.preprocess import decode


def _remeasure(objects, strip_mask, classes):
    """Thickness from the strip's own local width along each run, not from scan-band extents."""
    h, w = strip_mask.shape
    dt = cv2.distanceTransform((strip_mask > 0).astype(np.uint8), cv2.DIST_L2, 3)
    cap = 1.6 * max(classes)
    for o in objects:
        xs = np.rint(np.linspace(o.start.x, o.end.x, 25)).astype(int).clip(0, w - 1)
        ys = np.rint(np.linspace(o.start.y, o.end.y, 25)).astype(int).clip(0, h - 1)
        vals = 2 * dt[ys, xs]
        vals = vals[vals > 0]
        if vals.size:
            o.thickness_px = float(np.clip(np.median(vals), 1, cap))


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


def build(path, roi=None):
    image = decode(Path(path).read_bytes())
    h, w = image.shape[:2]
    from .config import settings

    if settings.workspace_semantic_source or settings.workspace_semantic_weights:
        from .semantic_workspace import build as semantic_build

        return semantic_build(image)
    from .ink_layers import wall_strips
    from .envelope import building_envelope, mask_from_polygon
    from .structural_runs import structural_runs, join_intersections
    from .plan_reconstruct import extend_dangling
    from . import openings as gap_openings

    notes = []
    strips = wall_strips(image)
    stats = strips.stats
    w_wall = float(stats["w_wall"])
    if roi:
        polygon = [(float(x), float(y)) for x, y in roi]
        env_mask = mask_from_polygon(polygon, image.shape)
    else:
        if stats.get("coloured_walls"):
            # A mask inferred from incomplete hatch is not a building outline.
            # Its inward notches crop the very walls/openings being recovered
            # and later masquerade as a user-editable authoritative boundary.
            # Only an explicit user ROI may clip coloured-plan extraction.
            polygon, env_mask = None, np.ones((h, w), dtype=bool)
        else:
            polygon, env_mask = building_envelope(strips.mask, w_wall)
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
    if polygon is not None and not roi:
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
    if strips.ink is not None:
        # On coloured plans, raw ink also includes dimension leaders and
        # furniture. It cannot justify extending a structural wall.
        extension_ink = (mask > 0) if (strips.red.any() or strips.blue.any()) else strips.ink | (mask > 0)
        extend_dangling(objects, extension_ink & env_mask)
    boxes, detector_ok = _detector_boxes(path, w, h)
    if not detector_ok:
        notes.append(
            "Local detector unavailable; openings come from wall gaps only and need review against the original. Add missing openings with two clicks."
        )
    found = gap_openings.detect(
        image, [o for o in objects if o.kind == "wall"], strips, boxes, exterior_zone
    )
    objects.extend(found.objects)
    return Document(
        width=w,
        height=h,
        objects=objects,
        envelope=[Point(x=x, y=y) for x, y in polygon] if polygon else None,
        passages=[Point(x=x, y=y) for x, y in found.passages[:500]],
        warnings=notes
        + ["Flat, uniformly scaled source assumed. Heights use editable defaults."],
    )


if __name__ == "__main__":
    cv2.setNumThreads(8)
    roi = json.loads(Path(sys.argv[3]).read_text()) if len(sys.argv) > 3 else None
    Path(sys.argv[2]).write_text(build(sys.argv[1], roi).model_dump_json())
