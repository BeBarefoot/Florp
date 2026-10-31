"""Separate wall strips from thin ink without a calibrated scale.

Walls are *bands*: solid dark fill, solid colour, or pale hatch bounded by
outlines. Dimension lines, text, beams and furniture are *strokes*: much
thinner than any wall. Widths are therefore estimated from the drawing itself
(stroke-width histogram) and every threshold is relative to them.
"""

from __future__ import annotations
from dataclasses import dataclass, field
import cv2
import numpy as np


@dataclass
class Strips:
    red: np.ndarray
    blue: np.ndarray
    dark: np.ndarray
    thin: np.ndarray
    stats: dict
    rejected: dict = field(default_factory=dict)
    ink: np.ndarray | None = None

    @property
    def mask(self):
        return (self.red | self.blue | self.dark).astype(np.uint8) * 255


def estimate_widths(ink: np.ndarray) -> dict:
    """Wall thickness classes and thin-line width from the opening-area curve.

    Opening the ink with a k x k square removes everything thinner than k. The
    area removed between k and k+1 is therefore a histogram of stroke widths
    weighted by area, so wall classes show up as its peaks.
    """
    h, w = ink.shape
    f = min(1.0, 1600 / max(h, w))
    small = (
        cv2.resize(ink.astype(np.uint8), None, fx=f, fy=f, interpolation=cv2.INTER_AREA)
        > 0
        if f < 1
        else ink
    )
    small = small.astype(np.uint8)
    kmax = max(8, min(48, int(0.05 * max(small.shape))))
    area = [int(small.sum())]
    for k in range(2, kmax + 1):
        area.append(
            int(
                cv2.morphologyEx(small, cv2.MORPH_OPEN, np.ones((k, k), np.uint8)).sum()
            )
        )
        if area[-1] == 0:
            break
    drops = np.array([area[i] - area[i + 1] for i in range(len(area) - 1)], float)
    if drops.size < 4 or area[0] == 0:
        return {"w_line": 1.0, "w_wall": 4.0, "classes": [4.0]}
    # drops[i] is the area of strokes whose width is i + 1 (opened away at k = i + 2).
    widths = np.arange(1, len(drops) + 1, dtype=float)
    lo = 3  # strokes of 1-2px are lines/text by definition
    cand = drops.copy()
    cand[: lo - 1] = 0
    if cand.max() <= 0:
        return {"w_line": 1.0, "w_wall": 4.0, "classes": [4.0]}
    smooth = np.convolve(cand, [0.25, 0.5, 0.25], "same")
    peaks = [
        i
        for i in range(len(smooth))
        if smooth[i] >= 0.12 * smooth.max()
        and smooth[i] >= smooth[i - 1]
        and smooth[i] >= (smooth[i + 1] if i + 1 < len(smooth) else 0)
    ]
    peaks.sort(key=lambda i: -smooth[i])
    classes = []
    for i in peaks:
        if all(abs(widths[i] - k) > 1.5 for k in classes):
            classes.append(float(widths[i]))
        if len(classes) == 3:
            break
    classes.sort()
    main = widths[int(np.argmax(smooth))]
    below = drops[: max(1, int(0.6 * min(classes)))]
    w_line = float(widths[int(np.argmax(below))]) if below.size else 1.0
    inv = 1.0 / f
    return {
        "w_line": w_line * inv,
        "w_wall": float(main) * inv,
        "classes": [c * inv for c in classes],
    }


def hatch_period(mask: np.ndarray, default: float = 6.0) -> float:
    """Dominant spacing of a repeating pattern, from the autocorrelation of its densest window."""
    if not mask.any():
        return default
    size = 256
    integral = cv2.integral(mask.astype(np.uint8))
    h, w = mask.shape
    best, where = -1, (0, 0)
    for y in range(0, max(1, h - size), size // 2):
        for x in range(0, max(1, w - size), size // 2):
            y2, x2 = min(h, y + size), min(w, x + size)
            s = integral[y2, x2] - integral[y, x2] - integral[y2, x] + integral[y, x]
            if s > best:
                best, where = s, (y, x)
    y, x = where
    patch = mask[y : y + size, x : x + size].astype(np.float32)
    patch -= patch.mean()
    if not patch.any():
        return default
    f = np.fft.rfft2(patch)
    ac = np.fft.irfft2(f * np.conj(f), s=patch.shape)
    ac /= ac[0, 0] or 1
    lags = []
    for angle in (45, 135):
        step = np.array([np.cos(np.radians(angle)), np.sin(np.radians(angle))])
        prof = []
        for r in range(1, 24):
            dx, dy = step * r
            prof.append(
                ac[int(round(dy)) % patch.shape[0], int(round(dx)) % patch.shape[1]]
            )
        prof = np.array(prof)
        for i in range(1, len(prof) - 1):
            if prof[i] > prof[i - 1] and prof[i] >= prof[i + 1] and prof[i] > 0.1:
                lags.append(i + 1)
                break
    return float(min(lags)) if lags else default


def _local_paper(gray: np.ndarray) -> np.ndarray:
    """Per-pixel paper brightness: a yellow or grey room fill is paper, not ink."""
    h, w = gray.shape
    scale = min(1.0, 600 / max(h, w))
    small = (
        cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
        if scale < 1
        else gray
    )
    k = max(15, int(round(min(small.shape) / 12)) | 1)
    paper = cv2.dilate(small, np.ones((5, 5), np.uint8))  # ignore thin dark lines
    paper = cv2.medianBlur(paper, k if k % 2 else k + 1)
    return (
        cv2.resize(paper, (w, h), interpolation=cv2.INTER_LINEAR)
        if scale < 1
        else paper
    )


def _components(mask):
    n, labels, st, _ = cv2.connectedComponentsWithStats(
        mask.astype(np.uint8), connectivity=8
    )
    return n, labels, st


def _pale_bands(outlines, colour, delta, classes, period):
    """Recover faint hatch only between two long, drawn parallel boundaries.

    Colour support is evaluated locally along each pair. A window or blank gap
    interrupts that support, so this cannot manufacture a wall across it.
    """
    h, w = outlines.shape
    result = np.zeros((h, w), np.uint8)
    minimum = max(24, int(4 * min(classes)))
    raw = cv2.HoughLinesP(
        outlines.astype(np.uint8) * 255,
        1,
        np.pi / 180,
        threshold=max(12, minimum // 2),
        minLineLength=minimum,
        maxLineGap=3,
    )
    if raw is None:
        return result.astype(bool)
    # OpenCV bindings may return (N, 1, 4) or (N, 4). Normalize before
    # limiting the line count; indexing [:, 0] turns the latter into scalars.
    raw = np.asarray(raw).reshape(-1, 4)
    groups = {True: [], False: []}
    for x1, y1, x2, y2 in raw[:1200]:
        dx, dy = abs(x2 - x1), abs(y2 - y1)
        if dy <= 1 and dx >= minimum:
            groups[True].append(((y1 + y2) / 2, min(x1, x2), max(x1, x2)))
        elif dx <= 1 and dy >= minimum:
            groups[False].append(((x1 + x2) / 2, min(y1, y2), max(y1, y2)))
    max_width = max(8, 1.35 * max(classes))
    kernel = np.ones(max(3, min(15, round(1.5 * period))))
    kernel /= kernel.sum()
    for horizontal, lines in groups.items():
        lines = sorted(set(lines))
        for i, (c, lo, hi) in enumerate(lines):
            for c2, lo2, hi2 in lines[i + 1 :]:
                thickness = c2 - c
                if thickness > max_width:
                    break
                if thickness < 3:
                    continue
                start, end = max(lo, lo2), min(hi, hi2)
                if end - start < minimum:
                    continue
                a, b = int(round(c)), int(round(c2))
                candidate = (
                    colour[a + 1 : b, start : end + 1]
                    if horizontal
                    else colour[start : end + 1, a + 1 : b].T
                )
                da = (
                    delta[a + 1 : b, start : end + 1]
                    if horizontal
                    else delta[start : end + 1, a + 1 : b].T
                )
                if not candidate.size:
                    continue
                profile = np.convolve(candidate.mean(axis=0), kernel, "same")
                tint = np.convolve(np.maximum(da, 0).mean(axis=0), kernel, "same")
                valid = (profile >= 0.18) & (tint >= 1.2)
                if valid.mean() < 0.55:
                    continue
                edges = np.diff(np.r_[False, valid, False].astype(np.int8))
                for u, v in zip(
                    np.flatnonzero(edges == 1), np.flatnonzero(edges == -1)
                ):
                    if v - u < minimum / 2:
                        continue
                    p, q = (
                        ((start + u, a), (start + v - 1, b))
                        if horizontal
                        else ((a, start + u), (b, start + v - 1))
                    )
                    cv2.rectangle(result, tuple(map(int, p)), tuple(map(int, q)), 1, -1)
    return result > 0


def wall_strips(image: np.ndarray) -> Strips:
    h, w = image.shape[:2]
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    lab_u8 = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
    lab = lab_u8.astype(np.int16)
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    paper = _local_paper(gray)
    # Remove the paper's local colour cast before looking for pale hatch.
    # A single fixed LAB threshold loses faded partitions in photographed plans.
    scale = min(1.0, 600 / max(h, w))
    small = (
        cv2.resize(lab_u8, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
        if scale < 1
        else lab_u8
    )
    kernel = max(15, int(min(small.shape[:2]) / 12) | 1)
    background = np.dstack([cv2.medianBlur(small[:, :, c], kernel) for c in (1, 2)])
    background = cv2.resize(background, (w, h), interpolation=cv2.INTER_LINEAR).astype(
        np.int16
    )
    da = lab[:, :, 1] - background[:, :, 0]
    db = lab[:, :, 2] - background[:, :, 1]
    red_cand = (
        (da >= 3)
        & (lab[:, :, 1] >= 131)
        & (hsv[:, :, 2] >= 40)
        & (hsv[:, :, 1] >= 10)
        & ((hsv[:, :, 0] < 23) | (hsv[:, :, 0] > 160))
    )
    blue_cand = (
        (db <= -5)
        & (lab[:, :, 2] <= 125)
        & (hsv[:, :, 2] >= 40)
        & (hsv[:, :, 1] >= 20)
        & (hsv[:, :, 0] > 90)
        & (hsv[:, :, 0] < 145)
    )
    # Dark concrete is still blue: classify chroma before dark fill.
    dark_cand = (
        (gray < np.minimum(110.0, 0.70 * paper.astype(np.float32)))
        & ~red_cand
        & ~blue_cand
    )
    outline_cand = (gray < 0.82 * paper.astype(np.float32)) & ~red_cand & ~blue_cand

    ink = dark_cand | red_cand | blue_cand
    stats = estimate_widths(ink)
    w_line, w_wall = stats["w_line"], stats["w_wall"]
    k_open = max(3, int(round(0.5 * min(stats["classes"]))))
    rejected = {
        "too_thin": np.zeros((h, w), bool),
        "text": np.zeros((h, w), bool),
        "no_outline": np.zeros((h, w), bool),
        "dashed": np.zeros((h, w), bool),
    }

    def strips_from(cand, hatch_ok, recover_thin=False):
        cand_u8 = cand.astype(np.uint8)
        filled = cand_u8
        density_dilate = False
        if hatch_ok and cand.any():
            period = hatch_period(cand)
            stats["hatch_period"] = period
            kc = max(3, int(round(1.5 * period)) | 1)
            # Fuse along the wall, without growing across its thickness.
            filled = cv2.morphologyEx(
                cand_u8, cv2.MORPH_CLOSE, np.ones((1, kc), np.uint8)
            ) | cv2.morphologyEx(cand_u8, cv2.MORPH_CLOSE, np.ones((kc, 1), np.uint8))
            density_dilate = True
        kernel = np.ones((k_open, k_open), np.uint8)
        opened = cv2.morphologyEx(filled, cv2.MORPH_OPEN, kernel)
        if recover_thin and opened.any():
            # A small population of real partitions may not form a peak in the
            # area-weighted width histogram. Rescue long, multi-pixel bands
            # attached to structural cores, while leaving single strokes out.
            # Do not use the histogram's "thin" mode here: when partitions are
            # rare it can mistake the partition width itself for line width.
            thickness = max(3, int(round(2 * max(1.0, max(h, w) / 1600))))
            length = max(24, int(round(4 * w_wall)))
            horizontal = cv2.morphologyEx(
                filled, cv2.MORPH_OPEN, np.ones((thickness, length), np.uint8)
            )
            vertical = cv2.morphologyEx(
                filled, cv2.MORPH_OPEN, np.ones((length, thickness), np.uint8)
            )
            joined = opened | horizontal | vertical
            _, components, _, _ = cv2.connectedComponentsWithStats(
                joined, connectivity=8
            )
            seeds = np.unique(components[opened > 0])
            opened = np.isin(components, seeds[seeds > 0]).astype(np.uint8)
        rejected["too_thin"] |= (filled > 0) & (opened == 0)
        n, labels, st = _components(opened)
        keep = np.zeros((h, w), bool)
        outline_ink = (
            cv2.dilate(
                (outline_cand & ~opened.astype(bool)).astype(np.uint8),
                np.ones((3, 3), np.uint8),
            )
            > 0
        )
        for i in range(1, n):
            x, y, bw, bh, area = st[i]
            long, short = max(bw, bh), min(bw, bh)
            comp = labels == i
            if long < max(3 * k_open, 3 * w_wall * 0.6):
                rejected["text"] |= comp
                continue
            # digits and symbols: compact boxes
            if (
                long < 8 * w_wall
                and short > 0.45 * long
                and area / max(1, bw * bh) < 0.72
            ):
                rejected["text"] |= comp
                continue
            width = area / max(long, 1)
            if width < 0.65 * min(stats["classes"]) and width < 1.3 * k_open:
                rejected["too_thin"] |= comp
                continue
            if density_dilate:
                solid = float(cand[comp].mean())
                if solid < 0.8:
                    edge = comp & ~(
                        cv2.erode(comp.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0
                    )
                    near = float(outline_ink[edge].mean()) if edge.any() else 0.0
                    if near < 0.45:
                        rejected["no_outline"] |= comp
                        continue
            keep |= comp
        return keep

    pale_colour = (
        (da >= 2)
        & (lab[:, :, 1] >= 130)
        & (hsv[:, :, 1] >= 10)
        & (hsv[:, :, 2] >= 40)
        & ((hsv[:, :, 0] < 23) | (hsv[:, :, 0] > 160))
    )
    recovered = (
        _pale_bands(
            outline_cand, pale_colour, da, stats["classes"], hatch_period(red_cand)
        )
        if red_cand.sum() > 100
        else np.zeros((h, w), bool)
    )
    stats["recovered_hatch_px"] = int(recovered.sum())
    dark = strips_from(dark_cand, False, recover_thin=True)
    red = strips_from(red_cand, True) | recovered
    blue = strips_from(blue_cand, False)
    # Coloured fills (window glass, door leaves, rugs) inside a plan whose walls are drawn dark
    # are decoration, not walls. Hatched-wall drawings have almost no dark band at all.
    if dark.sum() > 3 * (red.sum() + blue.sum()):
        rejected["decor"] = red | blue
        red = np.zeros_like(red)
        blue = np.zeros_like(blue)
        stats["dark_walls"] = True
    elif red.sum() + blue.sum() > max(100, 0.003 * h * w):
        # Window rails and stair treads are thin neutral strokes in a coloured
        # architectural plan. Do not let them become solid wall bands.
        kd = max(3, int(round(min(stats["classes"]))))
        dark = (
            cv2.morphologyEx(
                dark.astype(np.uint8), cv2.MORPH_OPEN, np.ones((kd, kd), np.uint8)
            )
            > 0
        )
    # Hatched walls carry their own dark outlines; those belong to the strip, not to thin ink.
    strip = dark | red | blue
    grown = cv2.dilate(strip.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0
    thin = ink & ~grown
    stats["strip_px"] = int(strip.sum())
    return Strips(
        red=red,
        blue=blue,
        dark=dark,
        thin=thin,
        stats=stats,
        rejected=rejected,
        ink=ink,
    )
