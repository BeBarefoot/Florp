from __future__ import annotations

from dataclasses import dataclass
import hashlib
import time
from .schema import Options
from .preprocess import decode, normalize
from .calibration import recognize, choose_scale
from .geometry import wall_masks, clean_geometry, classify, polygons, polygonal
from .export import normalize_metric, png, svg, dxf, bundle


@dataclass
class Result:
    archive: bytes
    report: dict
    layers: dict
    bounds: object


class BlueprintEngine:
    """Pure local pipeline. Bounds/coordinates are floats, never truncated.

    Pass an explicit Options object; no default scale is silently assumed.
    Direct calls have bounded data sizes and OCR, but only the HTTP/CLI worker
    supervisor imposes a killable wall-clock deadline on native operations.
    """

    def __init__(self, options: Options | None = None):
        self.options = options or Options()

    def process_bytes(self, data: bytes) -> Result:
        started = time.perf_counter()
        timings = {}
        previous = started

        def mark(name):
            nonlocal previous
            now = time.perf_counter()
            timings[name] = round(now - previous, 6)
            previous = now

        image = decode(data)
        source_shape = image.shape[:2]
        mark("decode")
        working, matrix, preprocessing = normalize(image, self.options)
        mark("normalize")
        words, ocr_notes = recognize(working, self.options)
        mark("ocr")
        scale, calibration = choose_scale(working, matrix, words, self.options)
        calibration["working_pixels_per_cm"] = scale
        mark("calibration")
        red_mask, blue_mask, mask_stats = wall_masks(
            working, words, scale, matrix, self.options
        )
        mark("masks")
        red, rejected_red = clean_geometry(red_mask, scale, self.options)
        blue, rejected_blue = clean_geometry(blue_mask, scale, self.options)
        # Concrete takes precedence at material overlap; eliminate CAD z-fighting.
        red = polygonal(red.difference(blue))
        layers, classification = classify(
            red, blue, working.shape[:2], scale, self.options
        )
        mark("vectors_and_classification")
        metric, bounds, bound_stats = normalize_metric(layers, scale)
        image_bytes, raster = png(metric, bounds, self.options.print_scale)
        svg_bytes = svg(metric, bounds, self.options.print_scale)
        dxf_bytes = dxf(metric, bounds)
        mark("render_and_cad_encode")
        warnings = [
            *preprocessing.pop("warnings"),
            *ocr_notes,
            classification["warning"],
            "color_semantics_unverified: identical colors can represent walls, annotations or site objects",
            "not_survey_grade: source resolution, perspective and calibration limit accuracy",
        ]
        if calibration["status"] != "user_calibrated":
            warnings.append("scale_requires_confirmation: " + calibration["status"])
        if rejected_red + rejected_blue:
            warnings.append(f"unsafe_snaps_rejected: {rejected_red + rejected_blue}")
        report = {
            "schema_version": 1,
            "engine": "florp-deterministic-color-v1",
            "source_sha256": hashlib.sha256(data).hexdigest(),
            "source_size_px": list(reversed(source_shape)),
            "working_size_px": list(reversed(working.shape[:2])),
            "options": self.options.model_dump(mode="json"),
            "preprocessing": preprocessing,
            "calibration": calibration,
            "ocr": {
                "recognized_tokens": len(words),
                "requested_languages": self.options.ocr_languages,
                "status": "disabled"
                if not self.options.ocr
                else (
                    "failed"
                    if any(
                        "ocr_failed" in w or "ocr_unavailable" in w for w in ocr_notes
                    )
                    else "completed"
                ),
            },
            "masks": mask_stats,
            "classification": classification,
            "bounds": bound_stats,
            "raster": raster,
            "layers": {
                name: {"polygons": len(polygons(g)), "area_cm2": g.area}
                for name, g in metric.items()
            },
            "warnings": warnings,
            "timings_seconds": timings,
            "requires_review": True,
            "accuracy_certified": False,
        }
        archive = bundle(metric, bounds, report, image_bytes, svg_bytes, dxf_bytes)
        mark("zip_encode")
        # Re-encode report once to include ZIP packaging cost. External benchmark
        # measures this final encode too; internal time is not an SLA claim.
        report["processing_seconds"] = round(time.perf_counter() - started, 6)
        archive = bundle(metric, bounds, report, image_bytes, svg_bytes, dxf_bytes)
        return Result(archive, report, metric, bounds)

    def process_pipeline(self, image_path, mode="all_walls"):
        from pathlib import Path

        options = Options.model_validate({**self.options.model_dump(), "mode": mode})
        return BlueprintEngine(options).process_bytes(Path(image_path).read_bytes())
