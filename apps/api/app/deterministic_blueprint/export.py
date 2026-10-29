from __future__ import annotations

from io import BytesIO
from html import escape
import json
import zipfile
import cv2
import numpy as np
from PIL import Image
from shapely.affinity import affine_transform
from shapely.geometry import box, mapping
from shapely.geometry.polygon import orient
from shapely.ops import unary_union
from .geometry import polygons
from .schema import ExtractionError

COLORS = {
    "LAYER_WALLS_EXTERIOR": "#c86464",
    "LAYER_WALLS_INTERIOR": "#c86464",
    "LAYER_MAMAD_CONCRETE": "#1e4b8c",
    "LAYER_WALLS_UNCLASSIFIED": "#c86464",
}
MARGIN_CM = 50.0


def normalize_metric(layers, px_per_cm):
    combined = unary_union(list(layers.values()))
    if combined.is_empty:
        raise ExtractionError("empty_output", "No walls remain in the requested mode")
    x1, y1, x2, y2 = combined.bounds
    # Keep full floating precision; never int(50 * scale).
    margin_px = MARGIN_CM * px_per_cm
    bounds_px = [x1 - margin_px, y1 - margin_px, x2 + margin_px, y2 + margin_px]
    width = (x2 - x1) / px_per_cm + 2 * MARGIN_CM
    height = (y2 - y1) / px_per_cm + 2 * MARGIN_CM
    matrix = [
        1 / px_per_cm,
        0,
        0,
        1 / px_per_cm,
        MARGIN_CM - x1 / px_per_cm,
        MARGIN_CM - y1 / px_per_cm,
    ]
    metric = {name: affine_transform(g, matrix) for name, g in layers.items()}
    bounds = box(0, 0, width, height)
    meta = {
        "units": "cm",
        "margin_cm": MARGIN_CM,
        "margin_working_px": margin_px,
        "architecture_working_bounds_px": [x1, y1, x2, y2],
        "viewport_working_bounds_px": bounds_px,
        "viewport_bounds_cm": [0.0, 0.0, width, height],
        "architecture_bounds_cm": [
            MARGIN_CM,
            MARGIN_CM,
            width - MARGIN_CM,
            height - MARGIN_CM,
        ],
        "working_px_to_output_cm": matrix,
    }
    return metric, bounds, meta


def rings(poly):
    p = orient(poly, sign=1.0)
    return [p.exterior, *p.interiors]


def svg(layers, bounds, print_scale):
    _, _, width, height = bounds.bounds
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width * 10 / print_scale:.6f}mm" height="{height * 10 / print_scale:.6f}mm" viewBox="0 0 {width:.9f} {height:.9f}">',
        '<rect width="100%" height="100%" fill="white"/>',
    ]
    for name, g in layers.items():
        parts.append(
            f'<g id="{escape(name)}" fill="{COLORS[name]}" fill-rule="evenodd">'
        )
        for poly in polygons(g):
            paths = []
            for ring in rings(poly):
                coords = list(ring.coords)
                paths.append(
                    "M" + " L".join(f"{x:.9f},{y:.9f}" for x, y in coords[:-1]) + " Z"
                )
            parts.append('<path d="' + " ".join(paths) + '"/>')
        parts.append("</g>")
    parts.append(
        f'<g id="LAYER_50CM_BOUNDS" fill="none" stroke="#555" stroke-width="0.5"><rect x="0" y="0" width="{width:.9f}" height="{height:.9f}"/>'
    )
    for x in np.arange(50, width, 50):
        parts.append(f'<path d="M{x},0 v5 M{x},{height} v-5"/>')
    for y in np.arange(50, height, 50):
        parts.append(f'<path d="M0,{y} h5 M{width},{y} h-5"/>')
    parts.extend(["</g>", "</svg>"])
    return "\n".join(parts).encode()


def dxf(layers, bounds):
    """Standards-based ASCII R2000 DXF, millimeters, oriented closed rings.

    Curves represent footprints/holes, not HATCH solids or door semantics.
    No additional CAD dependency is required at runtime.
    """
    out = []

    def pair(code, value):
        out.extend([str(code), str(value)])

    pair(0, "SECTION")
    pair(2, "HEADER")
    pair(9, "$ACADVER")
    pair(1, "AC1015")
    pair(9, "$INSUNITS")
    pair(70, 4)  # millimeters
    pair(9, "$MEASUREMENT")
    pair(70, 1)
    pair(0, "ENDSEC")
    pair(0, "SECTION")
    pair(2, "TABLES")
    pair(0, "TABLE")
    pair(2, "LAYER")
    pair(5, "1")
    pair(330, "0")
    pair(100, "AcDbSymbolTable")
    pair(70, len(layers) + 1)
    for i, name in enumerate([*layers, "LAYER_50CM_BOUNDS"]):
        pair(0, "LAYER")
        pair(100, "AcDbSymbolTableRecord")
        pair(100, "AcDbLayerTableRecord")
        pair(2, name)
        pair(70, 0)
        pair(62, [1, 1, 5, 8, 8][i])
        pair(6, "CONTINUOUS")
    pair(0, "ENDTAB")
    pair(0, "ENDSEC")
    pair(0, "SECTION")
    pair(2, "ENTITIES")
    height = bounds.bounds[3]
    for name, g in [*layers.items(), ("LAYER_50CM_BOUNDS", bounds)]:
        for poly in polygons(g):
            for ring in rings(poly):
                coords = list(ring.coords)[:-1]
                pair(0, "LWPOLYLINE")
                pair(100, "AcDbEntity")
                pair(8, name)
                pair(100, "AcDbPolyline")
                pair(90, len(coords))
                pair(70, 1)
                for x, y in coords:
                    pair(10, format(x * 10, ".12g"))
                    pair(20, format((height - y) * 10, ".12g"))
    pair(0, "ENDSEC")
    pair(0, "EOF")
    return ("\n".join(out) + "\n").encode("ascii")


def png(layers, bounds, print_scale):
    _, _, width_cm, height_cm = bounds.bounds
    resolution = 300 / 2.54 / print_scale
    width, height = round(width_cm * resolution) + 1, round(height_cm * resolution) + 1
    if width * height > 16_000_000 or max(width, height) > 16000:
        raise ExtractionError(
            "output_too_large",
            "300 DPI output exceeds 16MP/16000px: use a larger print_scale denominator or correct calibration",
        )
    canvas = np.full((height, width, 3), 255, np.uint8)
    for name, g in layers.items():
        full = np.zeros((height, width), np.uint8)
        for poly in polygons(g):
            mask = np.zeros_like(full)
            pts = lambda r: np.rint(np.asarray(r.coords) * resolution).astype(np.int32)
            cv2.fillPoly(mask, [pts(poly.exterior)], 255)
            for ring in poly.interiors:
                cv2.fillPoly(mask, [pts(ring)], 0)
            full |= mask
        rgb = tuple(int(COLORS[name][i : i + 2], 16) for i in (1, 3, 5))
        canvas[full > 0] = rgb
    cv2.rectangle(canvas, (0, 0), (width - 1, height - 1), (100, 100, 100), 1)
    for cm in np.arange(50, width_cm, 50):
        x = round(cm * resolution)
        cv2.line(canvas, (x, 0), (x, 5), (100, 100, 100), 1)
        cv2.line(canvas, (x, height - 1), (x, height - 6), (100, 100, 100), 1)
    for cm in np.arange(50, height_cm, 50):
        y = round(cm * resolution)
        cv2.line(canvas, (0, y), (5, y), (100, 100, 100), 1)
        cv2.line(canvas, (width - 1, y), (width - 6, y), (100, 100, 100), 1)
    stream = BytesIO()
    Image.fromarray(canvas).save(stream, format="PNG", dpi=(300, 300), compress_level=1)
    return stream.getvalue(), {
        "width_px": width,
        "height_px": height,
        "dpi": 300,
        "print_scale_denominator": print_scale,
        "output_pixels_per_cm": resolution,
        "margin_rounding_tolerance_cm": 1 / resolution,
        "note": "Source precision is unchanged; 300 DPI is print sampling at the specified drawing ratio",
    }


def bundle(layers, bounds, report, png_bytes, svg_bytes, dxf_bytes):
    data = BytesIO()
    with zipfile.ZipFile(data, "w", compression=zipfile.ZIP_STORED) as archive:
        files = {
            "walls.png": png_bytes,
            "walls.svg": svg_bytes,
            "walls.dxf": dxf_bytes,
            "report.json": json.dumps(
                report, ensure_ascii=False, indent=2, allow_nan=False
            ).encode(),
            "geometry.geojson": json.dumps(
                {
                    "type": "FeatureCollection",
                    "coordinate_system": "local centimeters, x right, y down; not geographic WGS84",
                    "features": [
                        {
                            "type": "Feature",
                            "properties": {"layer": name},
                            "geometry": mapping(g),
                        }
                        for name, g in [*layers.items(), ("LAYER_50CM_BOUNDS", bounds)]
                    ],
                },
                allow_nan=False,
            ).encode(),
        }
        # Fixed archive metadata makes repeated identical extractions reproducible
        # except the explicitly non-deterministic timing report.
        for name, content in files.items():
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            archive.writestr(info, content)
    return data.getvalue()
