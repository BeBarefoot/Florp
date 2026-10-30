"""Local semantic evaluation → editable source-pixel walls and openings.

No model, upstream implementation, network request, or commercial license is
bundled. The administrator explicitly supplies trusted upstream code/weights.
CubiCasa's published implementation/checkpoint is noncommercial; this adapter
is an evaluation path, not a production license grant.
"""

from __future__ import annotations
import importlib
import sys
from pathlib import Path
import cv2
import numpy as np
from shapely.geometry import LineString
from shapely.ops import unary_union
from .plan_workspace import Document, Segment, Point
from .structural_runs import structural_runs, join_intersections
from .config import settings


def predict(image):
    source = Path(settings.workspace_semantic_source).expanduser().resolve()
    weights = Path(settings.workspace_semantic_weights).expanduser().resolve()
    if (
        not (source / "floortrans/models/hg_furukawa_original.py").is_file()
        or not weights.is_file()
    ):
        raise ValueError(
            "Configured semantic evaluation requires trusted CubiCasa source and local checkpoint"
        )
    import torch

    torch.set_num_threads(8)
    sys.path.insert(0, str(source))
    try:
        cls = importlib.import_module(
            "floortrans.models.hg_furukawa_original"
        ).hg_furukawa_original
    finally:
        sys.path.pop(0)
    device = settings.workspace_semantic_device
    if device not in ("cpu", "mps", "cuda"):
        raise ValueError("Semantic device must be cpu, mps or cuda")
    count = settings.workspace_semantic_rotations
    if count not in (1, 4):
        raise ValueError("Semantic rotations must be 1 or 4")
    model = cls(44)
    model.load_state_dict(
        torch.load(weights, map_location="cpu", weights_only=True)["model_state"]
    )
    model.eval().to(device)
    h, w = image.shape[:2]
    ratio = min(1.0, 768 / max(h, w))
    iw, ih = max(32, round(w * ratio)), max(32, round(h * ratio))
    resized = cv2.resize(cv2.cvtColor(image, cv2.COLOR_BGR2RGB), (iw, ih))
    # Preserve aspect ratio, including nonsquare photographic plans.
    pw, ph = (iw + 31) // 32 * 32, (ih + 31) // 32 * 32
    canvas = np.full((ph, pw, 3), 255, np.uint8)
    canvas[:ih, :iw] = resized
    tensor = (
        torch.from_numpy(canvas.transpose(2, 0, 1).copy()).float()[None].to(device)
        / 127.5
        - 1
    )
    scores = []
    with torch.inference_mode():
        for k in range(count):
            pred = model(torch.rot90(tensor, k, (-2, -1)))[:, 21:]
            scores.append(torch.rot90(pred, -k, (-2, -1)))
        pred = torch.stack(scores).mean(0)
        rooms = pred[:, :12].argmax(1)[0, :ih, :iw].cpu().numpy().astype(np.uint8)
        icons = pred[:, 12:].argmax(1)[0, :ih, :iw].cpu().numpy().astype(np.uint8)
    return (
        cv2.resize(rooms, (w, h), interpolation=cv2.INTER_NEAREST),
        cv2.resize(icons, (w, h), interpolation=cv2.INTER_NEAREST),
    )


def color_evidence(image):
    """Color corroborates semantic geometry; it never creates a wall here."""
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
    red = (
        ((hsv[:, :, 0] < 20) | (hsv[:, :, 0] > 165))
        & (hsv[:, :, 1] > 18)
        & (lab[:, :, 1] > 131)
    )
    blue = (
        (hsv[:, :, 0] > 95)
        & (hsv[:, :, 0] < 140)
        & (hsv[:, :, 1] > 30)
        & (lab[:, :, 2] < 128)
    )
    return red, blue


def sample_profile(mask, wall):
    a = np.array([wall.start.x, wall.start.y])
    v = np.array([wall.end.x - wall.start.x, wall.end.y - wall.start.y])
    length = np.linalg.norm(v)
    u = v / length
    normal = np.array([-u[1], u[0]])
    positions = np.arange(int(np.ceil(length)) + 1)
    offsets = np.linspace(-wall.thickness_px * 0.3, wall.thickness_px * 0.3, 5)
    coords = a + positions[:, None, None] * u + offsets[None, :, None] * normal
    xs = np.rint(coords[:, :, 0]).astype(int).clip(0, mask.shape[1] - 1)
    ys = np.rint(coords[:, :, 1]).astype(int).clip(0, mask.shape[0] - 1)
    return np.mean(mask[ys, xs], axis=1), a, u, length


def _prune(runs):
    """Remove raster stair-step fragments already covered by larger strips."""
    result = []
    covered = None
    for o in sorted(
        runs,
        key=lambda o: -np.hypot(o.end.x - o.start.x, o.end.y - o.start.y)
        * o.thickness_px,
    ):
        shape = LineString([(o.start.x, o.start.y), (o.end.x, o.end.y)]).buffer(
            o.thickness_px / 2, cap_style=2
        )
        if (
            covered is not None
            and shape.intersection(covered).area >= shape.area * 0.88
        ):
            continue
        result.append(o)
        covered = shape if covered is None else unary_union([covered, shape])
    return result


def _materials(walls, red, blue):
    result = []
    for wall in walls:
        r, a, u, length = sample_profile(red, wall)
        b, _, _, _ = sample_profile(blue, wall)
        known = np.flatnonzero(r + b > 0.2)
        if not len(known):
            result.append(wall)
            continue
        fraction = np.interp(np.arange(len(r)), known, b[known] / (r[known] + b[known]))
        concrete = cv2.medianBlur((fraction > 0.5).astype(np.uint8)[None], 9)[0] > 0
        edges = np.r_[
            0, np.flatnonzero(concrete[1:] != concrete[:-1]) + 1, len(concrete) - 1
        ]
        for lo, hi in zip(edges[:-1], edges[1:]):
            if hi - lo < 3:
                continue
            o = wall.model_copy(deep=True)
            p, q = a + u * lo, a + u * min(length, hi)
            o.start, o.end = Point(x=p[0], y=p[1]), Point(x=q[0], y=q[1])
            o.id = f"wall-{len(result)}"
            o.material = "concrete" if concrete[lo] else "block"
            o.uncertain = True
            result.append(o)
    return result


def _refine_thickness(walls, evidence):
    """Median source cross-sections avoid thickness inflation at L/T joints."""
    mask = cv2.morphologyEx(
        evidence.astype(np.uint8), cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8)
    )
    for wall in walls:
        a = np.array([wall.start.x, wall.start.y])
        v = np.array([wall.end.x - wall.start.x, wall.end.y - wall.start.y])
        length = np.linalg.norm(v)
        u = v / length
        normal = np.array([-u[1], u[0]])
        radius = max(6, round(wall.thickness_px * 1.5))
        samples = []
        inset = min(length / 4, wall.thickness_px)
        for t in np.linspace(inset, length - inset, 31):
            offsets = np.arange(-radius, radius + 1)
            pts = np.rint(a + t * u + offsets[:, None] * normal).astype(int)
            valid = (
                (pts[:, 0] >= 0)
                & (pts[:, 0] < mask.shape[1])
                & (pts[:, 1] >= 0)
                & (pts[:, 1] < mask.shape[0])
            )
            values = np.zeros(len(pts), np.uint8)
            values[valid] = mask[pts[valid, 1], pts[valid, 0]]
            edges = np.diff(np.r_[0, values, 0].astype(int))
            bands = [
                (lo, hi - 1)
                for lo, hi in zip(
                    np.flatnonzero(edges == 1), np.flatnonzero(edges == -1)
                )
                if 2 <= hi - lo <= wall.thickness_px * 1.3
            ]
            if bands:
                lo, hi = min(
                    bands, key=lambda band: abs((band[0] + band[1]) / 2 - radius)
                )
                shift = (lo + hi) / 2 - radius
                if abs(shift) <= wall.thickness_px / 2:
                    samples.append((hi - lo + 1, shift))
        if len(samples) >= 5:
            wall.thickness_px = float(np.median(np.asarray(samples)[:, 0]))
    return walls


def from_labels(image, rooms, icons):
    h, w = image.shape[:2]
    if rooms.shape != (h, w) or icons.shape != (h, w):
        raise ValueError("Semantic labels must match source dimensions")
    mask = (rooms == 2).astype(np.uint8) * 255
    runs = _prune(structural_runs(mask, min_length=max(12, min(w, h) // 40)))
    red, blue = color_evidence(image)
    evidence = red | blue
    # Colored plans can corroborate or reject fixture-like semantic fragments.
    # Monochrome plans retain semantic hypotheses rather than deleting all walls.
    colored = np.count_nonzero(evidence) / (w * h) > 0.005
    if colored:
        runs = [o for o in runs if np.mean(sample_profile(evidence, o)[0]) >= 0.10]
    for i, o in enumerate(runs):
        o.id = f"axis-{i}"
    walls = join_intersections(runs)
    openings = []
    union = ((icons == 1) | (icons == 2)).astype(np.uint8)
    count, labels, stats, centers = cv2.connectedComponentsWithStats(union)
    for k in range(1, count):
        x, y, bw, bh, area = stats[k]
        # Cropped-edge labels cannot establish a physical opening.
        if area < 8 or min(x, y, w - x - bw, h - y - bh) < 3:
            continue
        pixels = icons[labels == k]
        kind = (
            "window" if np.count_nonzero(pixels == 1) >= max(5, area * 0.2) else "door"
        )
        center = centers[k]
        candidates = []
        for wall in walls:
            profile, a, u, length = sample_profile(evidence, wall)
            t = np.dot(center - a, u)
            distance = np.linalg.norm(center - a - u * np.clip(t, 0, length))
            if distance <= max(10, wall.thickness_px * 1.5):
                candidates.append((distance, wall, profile, a, u, length, t))
        if not candidates:
            continue
        _, wall, profile, a, u, length, t = min(candidates, key=lambda c: c[0])
        span = bw if abs(u[0]) > abs(u[1]) else bh
        if span < max(8, wall.thickness_px * 0.75):
            continue
        lo, hi = max(0, t - span / 2), min(length, t + span / 2)
        if colored:
            gap = np.convolve(profile, np.ones(3) / 3, "same") < 0.18
            edges = np.diff(np.r_[False, gap, False].astype(np.int8))
            choices = []
            for start, end in zip(
                np.flatnonzero(edges == 1), np.flatnonzero(edges == -1)
            ):
                overlap = min(end, t + span / 2) - max(start, t - span / 2)
                if 5 <= end - start <= span * 2 + 15 and overlap > span * 0.3:
                    choices.append((overlap, start, end - 1))
            if choices:
                _, lo, hi = max(choices)
        if hi - lo < 5:
            continue
        p, q = a + u * lo, a + u * hi
        openings.append(
            Segment(
                id=f"opening-{len(openings)}",
                kind=kind,
                start=Point(x=p[0], y=p[1]),
                end=Point(x=q[0], y=q[1]),
                host_id=wall.id,
                thickness_px=wall.thickness_px,
                uncertain=True,
                height_m=2.1 if kind == "door" else 1.2,
                sill_m=0 if kind == "door" else 0.9,
            )
        )
    # Split material changes only after opening fitting, then retain all physical
    # spans by intersecting them with their material-specific host intervals.
    split_walls = _materials(walls, red, blue)
    if colored:
        split_walls = _prune(_refine_thickness(split_walls, evidence))
    split_openings = []
    for opening in openings:
        original = next(o for o in walls if o.id == opening.host_id)
        for wall in split_walls:
            hostline = LineString(
                [(wall.start.x, wall.start.y), (wall.end.x, wall.end.y)]
            )
            original_line = LineString(
                [(original.start.x, original.start.y), (original.end.x, original.end.y)]
            )
            if hostline.difference(original_line.buffer(0.01)).length > 0.01:
                continue
            cut = hostline.intersection(
                LineString(
                    [(opening.start.x, opening.start.y), (opening.end.x, opening.end.y)]
                )
            )
            if cut.geom_type != "LineString" or cut.length < 2:
                continue
            o = opening.model_copy(deep=True)
            o.id = f"opening-{len(split_openings)}"
            o.host_id = wall.id
            o.thickness_px = wall.thickness_px
            o.material = wall.material
            o.start = Point(x=cut.coords[0][0], y=cut.coords[0][1])
            o.end = Point(x=cut.coords[-1][0], y=cut.coords[-1][1])
            split_openings.append(o)
    notes = [
        "Local CubiCasa semantic evaluation (published upstream license: CC BY-NC 4.0). Outputs require review; not a commercial release approval.",
        "Flat, uniformly scaled source assumed. Set one known measurement for metric dimensions. Heights use editable defaults.",
    ]
    if any(
        min(
            o.start.x,
            o.end.x,
            o.start.y,
            o.end.y,
            w - o.start.x,
            w - o.end.x,
            h - o.start.y,
            h - o.end.y,
        )
        < o.thickness_px
        for o in split_walls
    ):
        notes.append(
            "Architecture reaches the image edge: cropped structure and openings cannot be recovered from this source."
        )
    return Document(
        width=w, height=h, objects=split_walls + split_openings, warnings=notes
    )


def build(image):
    return from_labels(image, *predict(image))
