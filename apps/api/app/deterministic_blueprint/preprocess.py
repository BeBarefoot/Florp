from __future__ import annotations

from io import BytesIO
import math
import cv2
import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError
from .schema import Options, ExtractionError

MAX_INPUT_PIXELS = 24_000_000
MAX_UPLOAD_BYTES = 24 * 1024 * 1024


def decode(data: bytes) -> np.ndarray:
    if not data or len(data) > MAX_UPLOAD_BYTES:
        raise ExtractionError(
            "invalid_image", "Supply a PNG/JPEG no larger than 24 MiB"
        )
    try:
        with Image.open(BytesIO(data)) as source:
            if (
                source.format not in ("PNG", "JPEG")
                or source.width * source.height > MAX_INPUT_PIXELS
            ):
                raise ExtractionError(
                    "invalid_image", "PNG/JPEG only; maximum 24 million pixels"
                )
            oriented = ImageOps.exif_transpose(source)
            # Composite alpha onto white, never interpret transparent black as ink.
            rgba = oriented.convert("RGBA")
            background = Image.new("RGBA", rgba.size, "white")
            background.alpha_composite(rgba)
            rgb = np.asarray(background.convert("RGB"))
            return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise ExtractionError(
            "invalid_image", "Image cannot be decoded safely"
        ) from exc


def transform_points(points, matrix):
    return cv2.perspectiveTransform(
        np.asarray(points, dtype=np.float64).reshape(1, -1, 2), matrix
    )[0]


def order_quad(points):
    pts = np.asarray(points, dtype=np.float32)
    center = pts.mean(axis=0)
    pts = pts[np.argsort(np.arctan2(pts[:, 1] - center[1], pts[:, 0] - center[0]))]
    pts = np.roll(pts, -int(np.argmin(pts.sum(axis=1))), axis=0)
    return pts


def detect_page(image):
    """Require four supported edges AND white paper on a darker surround.

    A rectangular wall outline inside a cropped white scan is not a page.
    """
    h, w = image.shape[:2]
    scale = min(1.0, 1000 / max(w, h))
    gray = cv2.cvtColor(cv2.resize(image, None, fx=scale, fy=scale), cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 50, 150)
    lines = cv2.HoughLinesP(
        edges, 1, np.pi / 360, 70, minLineLength=min(gray.shape) // 4, maxLineGap=20
    )
    if lines is None:
        return None
    lines = np.asarray(lines).reshape(-1, 4)
    if len(lines) < 4:
        return None
    contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    for cnt in sorted(contours, key=cv2.contourArea, reverse=True)[:12]:
        if cv2.contourArea(cnt) < 0.5 * gray.size:
            continue
        quad = cv2.approxPolyDP(cnt, 0.02 * cv2.arcLength(cnt, True), True)
        if len(quad) != 4 or not cv2.isContourConvex(quad):
            continue
        q = order_quad(quad.reshape(-1, 2))
        if (
            np.any(q[:, 0] < 3)
            or np.any(q[:, 1] < 3)
            or np.any(q[:, 0] > gray.shape[1] - 4)
            or np.any(q[:, 1] > gray.shape[0] - 4)
        ):
            continue
        inside = np.zeros_like(gray)
        cv2.fillPoly(inside, [q.astype(np.int32)], 255)
        outside = gray[inside == 0]
        paper = gray[inside > 0]
        if (
            not len(outside)
            or np.median(paper) < 170
            or np.median(paper) - np.median(outside) < 35
        ):
            continue
        # Each proposed boundary must be supported by an actual long Hough line.
        supported = 0
        for a, b in zip(q, np.roll(q, -1, axis=0)):
            v = b - a
            for raw in lines:
                c, d = raw[:2], raw[2:]
                u = d - c
                if (
                    abs(np.dot(v, u)) / max(np.linalg.norm(v) * np.linalg.norm(u), 1)
                    < 0.995
                ):
                    continue
                distance = abs(v[0] * (c - a)[1] - v[1] * (c - a)[0]) / np.linalg.norm(
                    v
                )
                if distance < 8:
                    supported += 1
                    break
        if supported == 4:
            return q / scale
    return None


def normalize(image, options: Options):
    h, w = image.shape[:2]
    transform = np.eye(3, dtype=np.float64)
    notes = []
    q = (
        order_quad(options.document_corners)
        if options.document_corners
        else detect_page(image)
    )
    method = "unchanged"
    if q is not None:
        if (
            not cv2.isContourConvex(q)
            or abs(cv2.contourArea(q)) < 0.1 * w * h
            or np.any(q < 0)
            or np.any(q[:, 0] > w - 1)
            or np.any(q[:, 1] > h - 1)
        ):
            raise ExtractionError(
                "invalid_corners",
                "Document corners must form a large convex quadrilateral inside the source",
            )
        vectors = np.roll(q, -1, axis=0) - q
        deviations = []
        for a, b in zip(vectors, np.roll(vectors, -1, axis=0)):
            cosine = np.clip(
                np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)), -1, 1
            )
            deviations.append(abs(math.degrees(math.acos(cosine)) - 90))
        roll = math.degrees(math.atan2(vectors[0, 1], vectors[0, 0]))
        if max(deviations) > 1.5 or abs(roll) > 1.5:
            if options.page_aspect_ratio is None:
                # Inventing the unknown true aspect ratio would distort dimensions.
                raise ExtractionError(
                    "perspective_requires_aspect",
                    "Skewed document detected: provide page_aspect_ratio and a reference calibration line after rectification",
                )
            width = int(
                round((np.linalg.norm(vectors[0]) + np.linalg.norm(vectors[2])) / 2)
            )
            height = int(round(width / options.page_aspect_ratio))
            if width * height > MAX_INPUT_PIXELS:
                raise ExtractionError(
                    "rectification_too_large",
                    "Rectified document exceeds 24 million pixels",
                )
            target = np.float32(
                [[0, 0], [width - 1, 0], [width - 1, height - 1], [0, height - 1]]
            )
            transform = cv2.getPerspectiveTransform(q, target)
            image = cv2.warpPerspective(
                image, transform, (width, height), borderValue=(255, 255, 255)
            )
            method = "homography"
    else:
        notes.append(
            "page_boundary_not_detected: no homography applied; flat, top-down input is assumed"
        )
    h, w = image.shape[:2]
    factor = min(1.0, options.max_processing_side / max(w, h))
    if factor < 1:
        width, height = int(round(w * factor)), int(round(h * factor))
        sx, sy = width / w, height / h
        resize = np.diag([sx, sy, 1.0])
        transform = resize @ transform
        image = cv2.resize(image, (width, height), interpolation=cv2.INTER_AREA)
    return (
        image,
        transform,
        {
            "method": method,
            "source_to_working": transform.tolist(),
            "working_to_source": np.linalg.inv(transform).tolist(),
            "warnings": notes,
        },
    )
