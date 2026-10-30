"""Isolated local extraction; no scale prerequisite, no generated geometry."""

import sys
from pathlib import Path
import cv2, numpy as np
from .plan_workspace import Document, Segment, Point
from .deterministic_blueprint.preprocess import decode
from .deterministic_blueprint.geometry import wall_masks
from .deterministic_blueprint.schema import Options
from .deterministic_blueprint.calibration import recognize
from .mask_topology import region_wall_lines


def build(path):
    image = decode(Path(path).read_bytes())
    h, w = image.shape[:2]
    options = Options(ocr_timeout_s=1)
    words, notes = recognize(image, options)
    red, blue, _ = wall_masks(image, words, 1.0, np.eye(3), options)
    mask = red | blue
    lines = region_wall_lines(mask, min_length=max(12, min(w, h) // 35)).lines
    from .deterministic_blueprint.geometry import clean_geometry, classify

    try:
        rg, _ = clean_geometry(red, 1.0, options)
        bg, _ = clean_geometry(blue, 1.0, options)
        layers, classification = classify(rg, bg, mask.shape, 1.0, options)
    except Exception:
        layers = {}
    if not lines:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        ink = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)[1]
        mask = cv2.morphologyEx(ink, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
        lines = region_wall_lines(mask, min_length=max(30, min(w, h) // 10)).lines
        notes.append("Monochrome fallback: review structural runs against the source.")
    has_color = bool(red.any() or blue.any())
    objects = []
    for i, l in enumerate(lines):
        x, y = int((l.x1 + l.x2) / 2), int((l.y1 + l.y2) / 2)
        horizontal = abs(l.x2 - l.x1) > abs(l.y2 - l.y1)
        thickness = 1
        for sign in (-1, 1):
            for d in range(1, 50):
                xx = x if horizontal else x + sign * d
                yy = y + sign * d if horizontal else y
                if not (0 <= xx < w and 0 <= yy < h) or not mask[yy, xx]:
                    break
                thickness += 1
        objects.append(
            Segment(
                id=f"wall-{i}",
                start=Point(x=l.x1, y=l.y1),
                end=Point(x=l.x2, y=l.y2),
                thickness_px=max(3, thickness),
                uncertain=not has_color,
                material="concrete" if blue[y, x] else "block",
                exterior=(
                    layers["LAYER_WALLS_EXTERIOR"].distance(
                        __import__("shapely").geometry.Point(x, y)
                    )
                    < max(3, thickness)
                    if layers and not layers.get("LAYER_WALLS_EXTERIOR").is_empty
                    else None
                ),
            )
        )
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
    # Only connect nearby perpendicular/collinear endpoints; large blank gaps stay open.
    for i, a in enumerate(objects):
        for b in objects[i + 1 :]:
            for p in (a.start, a.end):
                for q in (b.start, b.end):
                    if np.hypot(p.x - q.x, p.y - q.y) <= max(
                        4, min(a.thickness_px, b.thickness_px)
                    ):
                        x = (p.x + q.x) / 2
                        y = (p.y + q.y) / 2
                        p.x = q.x = x
                        p.y = q.y = y
    try:
        from .pretrained_detector import detect_objects

        result = detect_objects(Path(path), w, h)
        for box in result.boxes:
            if box.category not in ("door", "window"):
                continue
            center = np.array([(box.x1 + box.x2) / 2, (box.y1 + box.y2) / 2])
            matches = []
            for wall in objects:
                if wall.kind != "wall":
                    continue
                start = np.array([wall.start.x, wall.start.y])
                v = np.array([wall.end.x - wall.start.x, wall.end.y - wall.start.y])
                length = np.linalg.norm(v)
                t = np.clip(np.dot(center - start, v) / length**2, 0, 1)
                distance = np.linalg.norm(center - start - t * v)
                if distance < max(box.x2 - box.x1, box.y2 - box.y1):
                    matches.append((distance, wall, start, v, length, t))
            if not matches:
                continue
            _, wall, start, v, length, t = min(matches, key=lambda m: m[0])
            span = (
                box.x2 - box.x1 if abs(v[0]) > abs(v[1]) else box.y2 - box.y1
            ) / length
            a = start + max(0, t - span / 2) * v
            b = start + min(1, t + span / 2) * v
            if np.linalg.norm(b - a) < 2:
                continue
            objects.append(
                Segment(
                    id=f"opening-{len(objects)}",
                    kind=box.category,
                    start=Point(x=a[0], y=a[1]),
                    end=Point(x=b[0], y=b[1]),
                    host_id=wall.id,
                    thickness_px=wall.thickness_px,
                    uncertain=True,
                    height_m=2.1 if box.category == "door" else 1.2,
                    sill_m=0 if box.category == "door" else 0.9,
                )
            )
    except Exception:
        notes.append(
            "Local detector unavailable; deterministic gap/rail/arc proposals require review against the original. Add missing openings with two clicks."
        )
    from .cv_openings import propose

    if not any(o.kind != "wall" for o in objects):
        objects.extend(propose(image, objects))
    return Document(
        width=w,
        height=h,
        objects=objects,
        warnings=notes
        + ["Flat, uniformly scaled source assumed. Heights use editable defaults."],
    )


if __name__ == "__main__":
    cv2.setNumThreads(8)
    Path(sys.argv[2]).write_text(build(sys.argv[1]).model_dump_json())
