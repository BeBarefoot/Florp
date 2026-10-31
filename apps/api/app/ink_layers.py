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
    small = cv2.resize(ink.astype(np.uint8), None, fx=f, fy=f, interpolation=cv2.INTER_AREA) > 0 if f < 1 else ink
    small = small.astype(np.uint8)
    kmax = max(8, min(48, int(0.05 * max(small.shape))))
    area = [int(small.sum())]
    for k in range(2, kmax + 1):
        area.append(int(cv2.morphologyEx(small, cv2.MORPH_OPEN, np.ones((k, k), np.uint8)).sum()))
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
        i for i in range(len(smooth))
        if smooth[i] >= 0.12 * smooth.max() and smooth[i] >= smooth[i - 1] and smooth[i] >= (smooth[i + 1] if i + 1 < len(smooth) else 0)
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
    return {"w_line": w_line * inv, "w_wall": float(main) * inv, "classes": [c * inv for c in classes]}


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
            dx, dy = (step * r)
            prof.append(ac[int(round(dy)) % patch.shape[0], int(round(dx)) % patch.shape[1]])
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
    small = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA) if scale < 1 else gray
    k = max(15, int(round(min(small.shape) / 12)) | 1)
    paper = cv2.dilate(small, np.ones((5, 5), np.uint8))  # ignore thin dark lines
    paper = cv2.medianBlur(paper, k if k % 2 else k + 1)
    return cv2.resize(paper, (w, h), interpolation=cv2.INTER_LINEAR) if scale < 1 else paper


def _components(mask):
    n, labels, st, _ = cv2.connectedComponentsWithStats(mask.astype(np.uint8), connectivity=8)
    return n, labels, st


def wall_strips(image: np.ndarray) -> Strips:
    h, w = image.shape[:2]
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB).astype(np.int16)
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    paper = _local_paper(gray)

    dark_cand = (gray < 110) & (gray < 0.55 * paper.astype(np.float32))
    red_cand = (lab[:, :, 1] - 128 >= 7) & (hsv[:, :, 1] >= 12) & ~dark_cand & ((hsv[:, :, 0] < 20) | (hsv[:, :, 0] > 160))
    blue_cand = (lab[:, :, 2] - 128 <= -7) & (hsv[:, :, 1] >= 20) & ~dark_cand & (hsv[:, :, 0] > 90) & (hsv[:, :, 0] < 140)

    ink = dark_cand | red_cand | blue_cand
    stats = estimate_widths(ink)
    w_line, w_wall = stats["w_line"], stats["w_wall"]
    k_open = max(3, int(round(0.5 * min(stats["classes"]))))
    rejected = {"too_thin": np.zeros((h, w), bool), "text": np.zeros((h, w), bool),
                "no_outline": np.zeros((h, w), bool), "dashed": np.zeros((h, w), bool)}

    def strips_from(cand, hatch_ok):
        cand_u8 = cand.astype(np.uint8)
        filled = cand_u8
        density_dilate = False
        if hatch_ok and cand.any():
            period = hatch_period(cand)
            stats["hatch_period"] = period
            kc = max(3, int(round(1.5 * period)) | 1)
            filled = cv2.morphologyEx(cand_u8, cv2.MORPH_CLOSE, np.ones((kc, kc), np.uint8))
            density_dilate = True
        kernel = np.ones((k_open, k_open), np.uint8)
        opened = cv2.morphologyEx(filled, cv2.MORPH_OPEN, kernel)
        rejected["too_thin"] |= (filled > 0) & (opened == 0)
        n, labels, st = _components(opened)
        keep = np.zeros((h, w), bool)
        outline_ink = cv2.dilate((dark_cand & ~opened.astype(bool)).astype(np.uint8), np.ones((3, 3), np.uint8)) > 0
        for i in range(1, n):
            x, y, bw, bh, area = st[i]
            long, short = max(bw, bh), min(bw, bh)
            comp = labels == i
            if long < max(3 * k_open, 3 * w_wall * 0.6):
                rejected["text"] |= comp
                continue
            # digits and symbols: compact boxes
            if long < 4 * w_wall and short > 0.6 * long:
                rejected["text"] |= comp
                continue
            width = area / max(long, 1)
            if width < 0.6 * min(stats["classes"]) * 0.8 and width < k_open:
                rejected["too_thin"] |= comp
                continue
            if density_dilate:
                solid = float(cand[comp].mean())
                if solid < 0.8:
                    edge = comp & ~(cv2.erode(comp.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0)
                    near = float(outline_ink[edge].mean()) if edge.any() else 0.0
                    if near < 0.45:
                        rejected["no_outline"] |= comp
                        continue
            keep |= comp
        return keep

    dark = strips_from(dark_cand, False)
    red = strips_from(red_cand, True)
    blue = strips_from(blue_cand, False)
    # Coloured fills (window glass, door leaves, rugs) inside a plan whose walls are drawn dark
    # are decoration, not walls. Hatched-wall drawings have almost no dark band at all.
    if dark.sum() > 3 * (red.sum() + blue.sum()):
        rejected["decor"] = red | blue
        red = np.zeros_like(red)
        blue = np.zeros_like(blue)
        stats["dark_walls"] = True
    # Hatched walls carry their own dark outlines; those belong to the strip, not to thin ink.
    strip = dark | red | blue
    grown = cv2.dilate(strip.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0
    thin = ink & ~grown
    stats["strip_px"] = int(strip.sum())
    return Strips(red=red, blue=blue, dark=dark, thin=thin, stats=stats, rejected=rejected, ink=ink)
