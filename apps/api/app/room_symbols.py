"""Match source symbols independently of physical scale, before buyer calibration."""

import cv2
import numpy as np

from .plan_model import Pt, RoomSymbol


def _template(kind, single=False):
    # Normalize the long axis vertically. Internal strokes distinguish a car
    # from a rectangular parking bay and a mattress from a bare rectangle.
    mask = np.zeros((96, 64), np.uint8)
    if kind == "car":
        for y, arch in [(25, -8), (71, 6)]:
            points = [
                (x, round(y + arch * np.sin(np.pi * (x - 6) / 51)))
                for x in range(6, 58)
            ]
            cv2.polylines(mask, [np.int32(points)], False, 255, 1)
        cv2.polylines(
            mask, [np.int32([(6, 25), (12, 33), (11, 62), (6, 71)])], False, 255, 1
        )
        cv2.polylines(
            mask, [np.int32([(57, 25), (51, 33), (52, 62), (57, 71)])], False, 255, 1
        )
    else:
        for a, b in [(11, 52)] if single else [(5, 29), (34, 58)]:
            cv2.rectangle(mask, (a, 5), (b, 22), 255, 1)
        cv2.line(mask, (3, 30), (60, 30), 255, 1)
    return np.where(mask)


_TEMPLATES = {
    "car": [_template("car")],
    "bed": [_template("bed"), _template("bed", True)],
}


def detect_symbols(image, roi=None):
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    # Keep detection bounded while converting every returned point to source pixels.
    scale = min(1.0, 1600 / max(gray.shape))
    if scale < 1:
        gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    ink = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 21, 4
    )
    contours, _ = cv2.findContours(ink, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    matches = []
    region = np.float32(roi) if roi is not None and len(roi) else None
    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        short, long = sorted((w, h))
        if short < 14 or long > min(440, max(gray.shape) * 0.5) or long / short > 3.2:
            continue
        if cv2.contourArea(contour) < 0.77 * w * h:
            continue
        center = ((x + w / 2) / scale, (y + h / 2) / scale)
        if region is not None and cv2.pointPolygonTest(region, center, False) < 0:
            continue
        patch = ink[y : y + h, x : x + w]
        for turns in range(4):
            rotated = np.rot90(patch, turns)
            aspect = rotated.shape[0] / rotated.shape[1]
            if not 0.97 <= aspect <= 3.2:
                continue
            normalized = cv2.resize(rotated, (64, 96), interpolation=cv2.INTER_AREA)
            strokes = normalized > 48
            if not 0.018 < strokes[4:-4, 4:-4].mean() < 0.35:
                continue
            # A ruled bay or hatched cabinet also has transverse lines. Both
            # the mattress and vehicle cabin need a relatively clear center.
            if strokes[40:60, 19:45].mean() > 0.14:
                continue
            distance = cv2.distanceTransform(
                (~strokes).astype(np.uint8), cv2.DIST_L2, 3
            )
            for kind, templates in _TEMPLATES.items():
                if (
                    kind == "car"
                    and not 1.85 <= aspect <= 3.2
                    or kind == "bed"
                    and aspect > 2.55
                ):
                    continue
                for rows, cols in templates:
                    close = distance[rows, cols] <= 2.4
                    # Require both ends of the cabin, or both pillow and blanket.
                    split = 48 if kind == "car" else 26
                    score = min(close[rows < split].mean(), close[rows >= split].mean())
                    if score >= 0.82:
                        matches.append((score, kind, center, short / scale))
    found = []
    for _, kind, (x, y), width in sorted(matches, reverse=True):
        if any(
            np.hypot(s.position.x - x, s.position.y - y) < width * 0.5 for s in found
        ):
            continue
        found.append(RoomSymbol(kind=kind, position=Pt(x=x, y=y)))
        if len(found) == 256:
            break
    return found


def tag_rooms(model, symbols):
    model.room_symbols = symbols
    for room in model.rooms:
        if room.label or room.room_type:
            continue
        polygon = np.float32([(p.x, p.y) for p in room.polygon])
        kinds = {
            s.kind
            for s in symbols
            if cv2.pointPolygonTest(polygon, (s.position.x, s.position.y), False) > 0
        }
        if {"cooktop", "sofa", "dining_table"} <= kinds and not kinds.intersection({"bed", "car"}):
            room.room_type = "other"
            room.label = "Kitchen & living room"
            room.needs_semantic_review = True
        elif "toilet" in kinds and not kinds.intersection({"bed","car","cooktop","sofa"}):
            room.room_type = "bathroom"
            room.label = "Bathroom"
            room.needs_semantic_review = True
        elif kinds in ({"car"}, {"bed"}):
            room.room_type = "garage" if kinds == {"car"} else "bedroom"
            room.label = room.room_type.title()
            room.needs_semantic_review = True
    return model
