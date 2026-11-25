"""Propose scale from source-image dimensions for explicit confirmation."""
from math import hypot

import cv2

from .deterministic_blueprint.calibration import dimension_candidates, recognize
from .deterministic_blueprint.schema import Options
from .plan_model import Pt, Reference, ScaleProposal


def matching_proposal(candidates):
    # Each printed label contributes at most its closest, best-centered span.
    by_label = {}
    for c in candidates:
        (x1, y1), (x2, y2) = c["endpoints"]
        left, top, right, bottom = c["box"]
        cx, cy = (left + right) / 2, (top + bottom) / 2
        vertical = x1 == x2
        along, across = ((cy - (y1 + y2) / 2, cx - x1) if vertical
                         else (cx - (x1 + x2) / 2, cy - y1))
        rank = abs(across) + 2 * abs(along), -c["support"]
        key = tuple(c["box"])
        if key not in by_label or rank < by_label[key][0]:
            by_label[key] = rank, c, vertical

    by_span = {}
    for _, c, vertical in sorted(by_label.values(), key=lambda entry: entry[0]):
        # Duplicate OCR or repeated parallel dimension rows of the same span
        # do not count as independent physical measurements.
        axis = int(vertical)
        key = vertical, tuple(round(p[axis] / 5) for p in c["endpoints"])
        by_span.setdefault(key, (c, vertical))
    values = list(by_span.values())

    def rate(c):
        return c["px_per_cm"]

    # Require a three-span cluster covering both axes. Reject competing
    # clusters and contradictory evidence across full-length spans.
    groups = []
    ordered = sorted(values, key=lambda item: rate(item[0]))
    for i, (seed, _) in enumerate(ordered):
        group = [v for v in ordered[i:] if rate(v[0]) <= rate(seed) * 1.019]
        if len(group) >= 3 and len({v[1] for v in group}) == 2 and len({v[0]["length_cm"] for v in group}) >= 2:
            groups.append(group)
    if not groups:
        return None
    best = max(groups, key=len)
    if any(not any(item in best for item in group) for group in groups):
        return None

    def pixels(c):
        (x1, y1), (x2, y2) = c["endpoints"]
        return hypot(x2 - x1, y2 - y1)

    def ref(c):
        a, b = c["endpoints"]
        return Reference(p1=Pt(x=a[0], y=a[1]), p2=Pt(x=b[0], y=b[1]), length_meters=c["length_cm"] / 100)

    a = max((c for c, vertical in best if not vertical), key=pixels)
    b = max((c for c, vertical in best if vertical), key=pixels)
    span_by_axis = {False: pixels(a), True: pixels(b)}
    if any(abs(rate(c) / rate(a) - 1) > .025 and pixels(c) >= .8 * span_by_axis[vertical]
           for c, vertical in values):
        return None
    if pixels(b) > pixels(a):
        a, b = b, a
    return ScaleProposal(reference=ref(a), check_reference=ref(b), evidence_count=len(best))


def propose_scale(image):
    options = Options(ocr_languages="eng", ocr_timeout_s=1)
    words, _ = recognize(image, options)
    # OCR sees vertical labels when the image is turned. Map their boxes
    # back to source coordinates so the user can verify them on the plan.
    height, width = image.shape[:2]
    if words:
        rotated, _ = recognize(cv2.rotate(image, cv2.ROTATE_90_CLOCKWISE), options)
        for word in rotated:
            x1, y1, x2, y2 = word["box"]
            words.append({**word, "box": [y1, height - x2, y2, height - x1]})
        rotated, _ = recognize(cv2.rotate(image, cv2.ROTATE_90_COUNTERCLOCKWISE), options)
        for word in rotated:
            x1, y1, x2, y2 = word["box"]
            words.append({**word, "box": [width - y2, x1, width - y1, x2]})
    return matching_proposal(dimension_candidates(image, words)) if words else None
