# Florp deterministic blueprint microservice

An opt-in local extractor for red and blue architectural wall bands. It returns metric wall footprints and diagnostic exports. The homeowner workflow uses the main Florp extractor and editor. See the [Florp README](../../README.md).

## Run on macOS

From the repository root, install local OCR once:

```bash
brew install tesseract tesseract-lang
```

Then use the existing API environment:

```bash
cd apps/api
uv sync --locked
uv run --locked uvicorn app.deterministic_blueprint.service:app --host 127.0.0.1 --port 8010 --workers 1
```

Check `tesseract --list-langs` includes `eng` and `heb`. Missing languages are reported, never downloaded implicitly. The service does not need Torch, MPS, a GPU or Florp's model weights.

For a minimal installation separate from Florp, create a Python 3.12 environment, install `services/deterministic-blueprint/requirements.txt`, and put `apps/api` on `PYTHONPATH`. The package has no imports from Florp's database or legacy extraction modules.

Container alternative (build from repository root; builds download packages, processing does not):

```bash
docker build -f services/deterministic-blueprint/Dockerfile -t florp-deterministic .
docker run --rm --cpus=8 --memory=2g -p 127.0.0.1:8010:8010 florp-deterministic
```

## Extract one plan

Use a long known segment in the EXIF-oriented original image. Coordinates are before resizing/rectification. Example values below describe an example image, not a calibration for the supplied scans:

```bash
curl --fail-with-body http://127.0.0.1:8010/extract \
  -F 'file=@blueprint.png' \
  -F 'options={"reference":{"start":[200,300],"end":[1200,300],"length_cm":500},"mode":"all_walls"}' \
  --output florp-walls.zip
```

Alternatively, explicitly assume a source-image scale:

```bash
curl --fail-with-body http://127.0.0.1:8010/extract \
  -F 'file=@blueprint.png' \
  -F 'options={"default_scale_px_per_cm":2.5,"ocr":false,"mode":"outer_walls"}' \
  --output florp-walls.zip
```

With no reference/default, OCR attempts automatic calibration. It requires at least three distinct label boxes, two distinct dimension values, supporting dimension lines, paired witness ticks and agreement within 4%. Equally supported competing scales are rejected. This remains provisional: verify one physical reference before relying on measurements. A single line assumes a planar image with uniform scale; it cannot correct arbitrary lens distortion or an unknown perspective aspect ratio.

`GET /docs` exposes the multipart endpoint. The `options` field is a JSON string; options and reference objects reject unknown keys and non-finite numbers. Import `Options` from `app.deterministic_blueprint` for the complete typed contract.

Useful options:

| Option | Meaning |
| --- | --- |
| `mode` | `all_walls` or `outer_walls`; never ignored |
| `reference` | Two source-pixel points and `length_cm` |
| `default_scale_px_per_cm` | Explicit assumed scale, no silent default |
| `document_corners`, `page_aspect_ratio` | Four page corners plus **known true width/height ratio** |
| `architecture_roi` | Source-pixel polygon excluding site boundaries/other plans |
| `ocr_languages`, `ocr_timeout_s` | Defaults `eng+heb`, 1.5 seconds |
| `max_processing_side` | Default 2400; maximum 4000; transform is recorded |
| `print_scale` | 300 DPI drawing denominator; default `100` means 1:100 |
| `close_kernel_px` | 3/5/7, further capped to 6 physical cm; one iteration |
| `simplify_cm`, `snap_degrees` | 1.5cm displacement budget, at most 5 degrees |
| `envelope_gap_cm` | Default 180cm; bridges for classification only, never new wall output |
| `exterior_band_cm` | Provisional perimeter classification band; default 40cm |

Perspective correction needs known document proportions. A detected skew above 1.5 degrees without a page aspect ratio returns an actionable error; estimating it from a photographed quadrilateral and then claiming exact dimensions would be unsound. No page boundary means no automatic warp; the report states the flat-input assumption. A scalar source default is rejected after a perspective warp: supply a reference line or allow OCR calibration in the rectified image.

## Outputs and coordinates

ZIP contains:

- `walls.png`: white background, material colors, 300 DPI at explicit print ratio; 50cm viewport frame and ticks every 50cm.
- `walls.svg`: named layer groups, even-odd paths retaining holes, viewBox in local centimeters. Physical paper size accounts for `print_scale`.
- `walls.dxf`: R2000 ASCII DXF, **millimeters**, closed LWPOLYLINE footprints and hole rings with opposite winding. These are curves, not certified solids or BIM elements. Y increases upward; the origin is the bottom-left viewport corner.
- `geometry.geojson`: local planar **centimeters**, Y downward; explicitly not geographic WGS84.
- `report.json`: source hash, source↔working homography, working-pixel↔output-cm transform, calibration evidence, options, bounds, layer counts/areas, warnings and stage timings.

Required layers are `LAYER_WALLS_EXTERIOR`, `LAYER_WALLS_INTERIOR`, `LAYER_MAMAD_CONCRETE`, `LAYER_50CM_BOUNDS`. If the exterior cannot be inferred, all-walls output adds `LAYER_WALLS_UNCLASSIFIED` rather than mislabeling walls. Outer-only requests fail with `exterior_ambiguous` in that case. Concrete stays a separate material even when it lies on the exterior.

The viewport is the selected architecture's axis-aligned bounding box expanded **exactly 50.0cm on each side**. This is a bounding rectangle, not a 50cm offset curve following every concavity. All floating-point vector coordinates retain the metric margin. PNG samples necessarily round: up to one output pixel of discrepancy per side, recorded in the report. Setting PNG DPI metadata alone does not calibrate a drawing; default print sampling at 1:100 is 1.1811 output pixels per architecture centimeter. It adds no source detail.

## Supported drawings

The pipeline uses colour to separate red block walls and blue concrete. It uses local OCR for scale candidates, morphology to recover hatched bands, and closed-ring geometry to preserve holes. Perimeter classification can use gaps to infer a boundary. Exported footprints follow the extracted wall evidence.

This service targets colour wall footprints. For grayscale plans, hosted doors and windows, rooms, or walkthroughs, use the [main Florp app](../../README.md#upload-correct-and-walk).

## Timing and overload behavior

Target: measured extraction below 3.5 seconds on eight available CPU cores. Default processing deadline is **4.8 seconds**. A fresh subprocess handles each request; timeout kills its process group, including OCR, and returns HTTP 504 without partial geometry. One active plan per API worker; concurrent arrivals return 429 rather than silently waiting. Run one Uvicorn worker for that admission rule. Several API worker processes each have their own slot and would need an external admission controller to avoid oversubscription.

`BLUEPRINT_TIMEOUT_SECONDS` can raise the deadline up to 20 seconds on a slower Mac; doing so changes the fast-response contract. Limits reject oversized/over-complex results before PNG/vector allocations. Network upload/download, HTTP multipart parsing before endpoint dispatch, installation and operating-system scheduling are outside a hard real-time guarantee. Direct Python calls do not impose a killable native-operation deadline; use the service/supervised worker for that guarantee. The deadline is an abort policy, not a promise that every plan will yield a usable model within the budget.

Run the reproducible benchmark **separately from tests**:

```bash
cd apps/api
uv run --locked python scripts/benchmark_deterministic.py --runs 5 \
  --image /path/to/private-plan.png \
  --output /tmp/florp-local-benchmark.json
uv run --locked pytest -q tests/test_deterministic_blueprint.py
```

Benchmark exits nonzero if any measured cold/warm/isolated request fails or exceeds 3.5 seconds. Linux pins the benchmark and its children to eight CPU cores. macOS reports hardware without pretending affinity was set. Native dependency imports occur inside every isolated HTTP worker and are included in those measurements. Outputs and evidence must also be checked: speed is not an accuracy score.

## Accuracy and validation

Each report sets `requires_review=true` and `accuracy_certified=false`. The metric viewport margin is measured from the extracted architecture at the chosen scale. Check scale and perimeters on faded, cropped, or annotated plans. Establish accuracy with independently traced walls and known dimensions, and report quality and timing per input style. Historical measurements are in [engine validation](../../docs/deterministic-engine/VALIDATION.md).
