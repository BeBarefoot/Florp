from __future__ import annotations

from functools import lru_cache
import re
import cv2
import numpy as np
import pytesseract
from pytesseract import Output
from .preprocess import transform_points
from .schema import Options, ExtractionError


@lru_cache(maxsize=1)
def installed_languages():
    try:
        return set(pytesseract.get_languages(config=""))
    except (pytesseract.TesseractNotFoundError, pytesseract.TesseractError):
        return set()


def recognize(image, options: Options):
    if not options.ocr:
        return [], ["ocr_disabled"]
    available = installed_languages()
    requested = options.ocr_languages.split("+")
    languages = [lang for lang in requested if lang in available]
    notes = []
    if len(languages) != len(requested):
        notes.append(
            "ocr_language_unavailable: "
            + ",".join(x for x in requested if x not in available)
        )
    if not languages:
        return [], notes + [
            "ocr_unavailable: install local Tesseract and eng/heb traineddata"
        ]
    factor = min(1.0, 1600 / max(image.shape[:2]))
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    if factor < 1:
        gray = cv2.resize(
            gray, None, fx=factor, fy=factor, interpolation=cv2.INTER_AREA
        )
    try:
        data = pytesseract.image_to_data(
            gray,
            lang="+".join(languages),
            config="--psm 11",
            output_type=Output.DICT,
            timeout=options.ocr_timeout_s,
        )
    except (RuntimeError, pytesseract.TesseractError) as exc:
        return [], notes + ["ocr_failed_or_timed_out: " + type(exc).__name__]
    words = []
    for i, text in enumerate(data["text"]):
        if not text.strip() or float(data["conf"][i]) < 45:
            continue
        x, y, w, h = (
            float(data[key][i]) / factor for key in ("left", "top", "width", "height")
        )
        words.append(
            {
                "text": text.strip(),
                "confidence": float(data["conf"][i]),
                "box": [x, y, x + w, y + h],
            }
        )
    return words, notes


def _runs(values):
    indices = np.flatnonzero(values)
    if not len(indices):
        return []
    groups = np.split(indices, np.flatnonzero(np.diff(indices) > 2) + 1)
    return [float(np.mean(g)) for g in groups]


def dimension_candidates(image, words):
    """Pair integer-cm labels to actual long dimension lines and witness ticks.

    No digit-only label is accepted merely because it is near a wall. Both
    ticks, a supporting horizontal/vertical dimension line, and a centered
    label are required. Consensus is still provisional, not semantic proof.
    """
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    _, ink = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)
    clean = ink.copy()
    for word in words:
        x1, y1, x2, y2 = map(int, word["box"])
        clean[max(0, y1 - 1) : y2 + 2, max(0, x1 - 1) : x2 + 2] = 0
    candidates = []
    for word in words:
        if not re.fullmatch(r"\d{2,5}", word["text"]):
            continue
        cm = int(word["text"])
        if not 30 <= cm <= 10000:
            continue
        x1, y1, x2, y2 = word["box"]
        for vertical in (False, True):
            src = clean.T if vertical else clean
            cx, cy = (
                ((y1 + y2) / 2, (x1 + x2) / 2)
                if vertical
                else ((x1 + x2) / 2, (y1 + y2) / 2)
            )
            text_height = (x2 - x1) if vertical else (y2 - y1)
            reach = max(15, min(70, 2.5 * text_height))
            lo, hi = max(0, int(cy - reach)), min(src.shape[0], int(cy + reach) + 1)
            roi = src[lo:hi]
            if not roi.size:
                continue
            horizontal = cv2.morphologyEx(
                roi, cv2.MORPH_OPEN, np.ones((1, 40), np.uint8)
            )
            # Long horizontal support, not an arbitrary nearby contour extent.
            counts = np.count_nonzero(horizontal, axis=1)
            for local_y in np.argsort(counts)[-4:]:
                if counts[local_y] < 40:
                    continue
                y = lo + int(local_y)
                v = cv2.morphologyEx(
                    src[max(0, y - 18) : y + 19],
                    cv2.MORPH_OPEN,
                    np.ones((11, 1), np.uint8),
                )
                ticks = _runs(np.count_nonzero(v, axis=0) >= 9)
                left = [t for t in ticks if t < cx]
                right = [t for t in ticks if t > cx]
                for a in left[-4:]:
                    for b in right[:4]:
                        distance = b - a
                        if distance < 40 or abs((a + b) / 2 - cx) > max(
                            12, 0.12 * distance
                        ):
                            continue
                        support = (
                            np.count_nonzero(horizontal[local_y, int(a) : int(b) + 1])
                            / distance
                        )
                        scale = distance / cm
                        if support < 0.85 or not 0.02 <= scale <= 100:
                            continue
                        endpoints = [[y, a], [y, b]] if vertical else [[a, y], [b, y]]
                        candidates.append(
                            {
                                "label": word["text"],
                                "box": word["box"],
                                "length_cm": cm,
                                "endpoints": endpoints,
                                "px_per_cm": scale,
                                "support": round(min(1.0, support), 3),
                            }
                        )
    # One observation per OCR label/tick span, independent of duplicate scan rows.
    unique = {}
    for item in candidates:
        key = (
            tuple(round(x, 1) for x in item["box"]),
            tuple(round(x / 5) for pt in item["endpoints"] for x in pt),
        )
        unique.setdefault(key, item)
    return list(unique.values())


def choose_scale(image, transform, words, options: Options):
    h, w = image.shape[:2]
    if options.reference:
        ref = options.reference
        # Validate in working coordinates (also rejects off-document source refs).
        points = transform_points([ref.start, ref.end], transform)
        if (
            np.any(points < 0)
            or np.any(points[:, 0] > w - 1)
            or np.any(points[:, 1] > h - 1)
        ):
            raise ExtractionError(
                "invalid_reference",
                "Reference endpoints must lie within the rectified document",
            )
        distance = float(np.linalg.norm(points[1] - points[0]))
        if distance < 5:
            raise ExtractionError(
                "short_reference",
                "Calibration line must span at least 5 working pixels",
            )
        return distance / ref.length_cm, {
            "source": "reference",
            "status": "user_calibrated",
            "working_reference": points.tolist(),
            "length_cm": ref.length_cm,
            "evidence": [],
        }
    candidates = dimension_candidates(image, words)
    groups = []
    for item in candidates:
        nearby = [
            c for c in candidates if abs(c["px_per_cm"] / item["px_per_cm"] - 1) <= 0.04
        ]
        # Distinct physical label boxes, not repetitions of a single annotation.
        by_label = {}
        for c in nearby:
            by_label.setdefault(tuple(c["box"]), c)
        values = list(by_label.values())
        if len(values) >= 3 and len({c["length_cm"] for c in values}) >= 2:
            groups.append(values)
    groups.sort(key=lambda g: len(g), reverse=True)
    if groups:
        winner = groups[0]
        scale = float(np.median([c["px_per_cm"] for c in winner]))
        rivals = [
            g
            for g in groups[1:]
            if abs(np.median([c["px_per_cm"] for c in g]) / scale - 1) > 0.08
            and len(g) >= len(winner)
        ]
        if not rivals:
            return scale, {
                "source": "ocr_witness_consensus",
                "status": "provisional_verify_reference",
                "evidence": winner,
            }
    if options.default_scale_px_per_cm is not None:
        if (
            not np.allclose(transform[2], [0, 0, 1])
            or not np.allclose(transform[0, 1], 0)
            or not np.allclose(transform[1, 0], 0)
        ):
            raise ExtractionError(
                "reference_required_after_warp",
                "A default source scale is invalid after perspective warp; supply a reference line",
            )
        sx, sy = abs(transform[0, 0]), abs(transform[1, 1])
        if abs(sx / sy - 1) > 0.002:
            raise ExtractionError(
                "anisotropic_resize", "Supply a reference for anisotropic input"
            )
        return options.default_scale_px_per_cm * (sx + sy) / 2, {
            "source": "explicit_default",
            "status": "assumed_not_measured",
            "evidence": candidates,
        }
    raise ExtractionError(
        "calibration_required",
        "No unambiguous dimension consensus. Supply reference={start:[x,y],end:[x,y],length_cm:...} or default_scale_px_per_cm; no scale is guessed",
    )
