"""Deprecated compatibility helper; production extraction uses openings.detect.

Two parallel dark rails suggest a window; hinge-localized circular evidence
suggests a door. Proposals remain uncertain and never invent an entire envelope.
"""

import math
import cv2
import numpy as np
from .plan_workspace import Segment, Point


def propose(image, objects):
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape
    walls = [o for o in objects if o.kind == "wall"]
    proposals = []
    checks = 0
    seen = set()
    for i, a in enumerate(walls):
        for b in walls[i + 1 :]:
            ah = abs(a.end.x - a.start.x) > abs(a.end.y - a.start.y)
            bh = abs(b.end.x - b.start.x) > abs(b.end.y - b.start.y)
            if ah != bh:
                continue
            axis = "x" if ah else "y"
            cross = "y" if ah else "x"
            if abs(getattr(a.start, cross) - getattr(b.start, cross)) > max(
                4, min(a.thickness_px, b.thickness_px)
            ):
                continue
            left, right = sorted(
                (a, b), key=lambda o: min(getattr(o.start, axis), getattr(o.end, axis))
            )
            lo = max(getattr(left.start, axis), getattr(left.end, axis))
            hi = min(getattr(right.start, axis), getattr(right.end, axis))
            span = hi - lo
            if not 12 <= span <= min(160, max(w, h) * 0.15):
                continue
            mid = (getattr(a.start, cross) + getattr(b.start, cross)) / 2
            key = (ah, round(lo / 5), round(hi / 5), round(mid / 5))
            if key in seen:
                continue
            seen.add(key)
            checks += 1
            if checks > 100:
                return proposals
            x1, y1 = (lo, mid) if ah else (mid, lo)
            x2, y2 = (hi, mid) if ah else (mid, hi)
            radius = max(4, round(max(a.thickness_px, b.thickness_px)))
            xa, xb = (
                max(0, int(min(x1, x2) - radius)),
                min(w, int(max(x1, x2) + radius + 1)),
            )
            ya, yb = (
                max(0, int(min(y1, y2) - radius)),
                min(h, int(max(y1, y2) + radius + 1)),
            )
            stripe = gray[ya:yb, xa:xb]
            stripe = stripe if ah else stripe.T
            if stripe.size == 0:
                continue
            dark = stripe < min(150, float(np.median(stripe)) * 0.8)
            rails = np.flatnonzero(np.mean(dark, axis=1) > 0.55)
            groups = (
                np.split(rails, np.flatnonzero(np.diff(rails) > 1) + 1)
                if len(rails)
                else []
            )
            kind = (
                "window"
                if len(groups) >= 2 and groups[-1].mean() - groups[0].mean() >= 3
                else None
            )
            if kind is None and len(proposals) < 50:
                r = int(span * 1.25)
                xx = max(0, int(x1) - r)
                yy = max(0, int(y1) - r)
                patch = gray[
                    yy : min(h, int(max(y1, y2)) + r), xx : min(w, int(max(x1, x2)) + r)
                ]
                circles = (
                    cv2.HoughCircles(
                        patch,
                        cv2.HOUGH_GRADIENT,
                        1,
                        max(8, span / 2),
                        param1=80,
                        param2=15,
                        minRadius=max(5, int(span * 0.8)),
                        maxRadius=int(span * 1.15),
                    )
                    if patch.size
                    else None
                )
                if circles is not None and any(
                    min(
                        math.hypot(cx + xx - x1, cy + yy - y1),
                        math.hypot(cx + xx - x2, cy + yy - y2),
                    )
                    < span * 0.2
                    for cx, cy, _ in circles[0]
                ):
                    kind = "door"
            if kind:
                host = Segment(
                    id=f"gap-host-{len(proposals)}",
                    start=Point(x=x1, y=y1),
                    end=Point(x=x2, y=y2),
                    thickness_px=max(a.thickness_px, b.thickness_px),
                    uncertain=False,
                )
                opening = Segment(
                    id=f"cv-opening-{len(proposals)}",
                    kind=kind,
                    start=host.start.model_copy(),
                    end=host.end.model_copy(),
                    thickness_px=host.thickness_px,
                    host_id=host.id,
                    uncertain=True,
                    confidence=0.6 if kind == "window" else 0.55,
                    height_m=2.1 if kind == "door" else 1.2,
                    sill_m=0 if kind == "door" else 0.9,
                )
                proposals.extend([host, opening])
            if len(proposals) >= 100:
                return proposals
    return proposals
