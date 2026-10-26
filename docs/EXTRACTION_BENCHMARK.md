# Floor-plan extraction bake-off — safe benchmark

This experiment is isolated from Florp's production extraction, user corrections,
and SQLite projects. It does **not** modify `main.py` endpoints or choose a model
without held-out, manually verified results.

## What is actually runnable today

| Source | Status | Output |
|---|---|---|
| Florp YOLO | Runnable if `PRETRAINED_YOLO_WEIGHTS` and Ultralytics are installed | Wall axes from current YOLO detections |
| Florp Yytsi | Runnable if `YYTSI_RUN_DIR` contains working config and checkpoint | Wall axes from multi-scale masks |
| Florp saved layout | Runnable from geometry JSON | Walls, rooms, scale, confirmed-width openings where computable |
| Tectly | External inference not configured: requires account/API credentials and verified mapping | Strict normalized JSON import only |
| Raster2Seq | Official Linux/CUDA build is separate, not automatically installed on Mac | Strict normalized JSON import only |

**No model accuracy comparison has been measured yet.** Published benchmark
scores are not directly comparable to Florp's images.

## Get started with existing local models

From `apps/api`:

```bash
uv sync --extra pretrained-yolo --extra yytsi
uv run python -m app.extraction_exports --provider florp-yolo \
  --image /absolute/path/blueprint.png --output /tmp/florp-yolo.json

uv run python -m app.extraction_exports --provider florp-yytsi \
  --image /absolute/path/blueprint.png --output /tmp/florp-yytsi.json

uv run pytest -q tests/test_extraction_benchmark.py
```

**Ground truth is essential.** Export the verified reference plan as a
`PlanPrediction` JSON with `provider: "human-verified"`, wall start/end
coordinates, room polygons, doors/windows, and scale when actually confirmed.
All coordinates must refer to the **original** input image. Include its exact
SHA-256 and width/height, which can be found via:

```bash
uv run python -c 'from pathlib import Path;from app.extraction_benchmark import image_identity;print(image_identity(Path("/absolute/path/blueprint.png")))'
```

For a verified Florp layout stored as a geometry JSON object:

```bash
uv run python -m app.extraction_exports --provider florp-layout \
  --image /absolute/path/blueprint.png --source verified_geometry.json \
  --output /tmp/ground-truth.json
```

Only use that as truth if its walls, rooms, dimensions, and openings were
**independently reviewed**. A previously accepted AI proposal is not ground truth.

Run:

```bash
uv run python -m app.extraction_benchmark \
  --image /absolute/path/blueprint.png \
  --truth /tmp/ground-truth.json \
  --predictions /tmp/florp-yolo.json /tmp/florp-yytsi.json \
  --output /tmp/benchmark-report.json
```

The report contains segment-level wall precision/recall/F1, opening precision/
recall/F1, union room-area IoU, and scale error when both sources have
reliable pixels-per-meter. It does NOT yet score wall thickness, junction
topology, per-room matching, or human correction time. Keep those as separate
manual pass/fail reviews until implemented.

## Running third-party systems safely

### Raster2Seq

The [official repository](https://github.com/Cornell-VAILab/Raster2Seq)
provides pretrained `hf:cubicasa5k` checkpoints and
`tools/predict_cc5k.sh`. Its README documents Linux, Python 3.10, CUDA
11.8, and compiled operators; don't install those into Florp's `uv` env.
Use Docker/Linux GPU or an isolated compatible environment.

The published model predicts **room polygon sequences**, not metric scale or
reliable door/window width by itself. Export its predicted room polygons into
the schema below only after verifying its image preprocessing and coordinate
transform. Then import as `--provider normalized-external
--external-name raster2seq`.

### Tectly

[Developer documentation](https://docs.tectly.com/) describes an API
for room, wall, opening and measurements extraction, but authentication,
endpoint details and output structure must be confirmed from an actual
account/API response. Do not invent field mappings or make paid calls without
an explicit account configuration. Normalize its output into the same schema
using confirmed source-image coordinates, then import with
`--external-name tectly`.

Example normalized JSON (illustrative **schema**, not model output):

```json
{
  "schema_version": 1,
  "provider": "raster2seq",
  "image_sha256": "<64-character SHA-256 of exact PNG bytes>",
  "width_px": 992,
  "height_px": 440,
  "walls": [{"start": {"x": 12, "y": 20}, "end": {"x": 370, "y": 20}}],
  "rooms": [[{"x": 12, "y": 20}, {"x": 370, "y": 20}, {"x": 370, "y": 210}]],
  "openings": [],
  "px_per_meter": null,
  "scale_source": null
}
```

### Fairness and acceptance

1. Use the same *full uncropped original* image across all systems. An export
   with a different hash or size is rejected.
2. Keep any padding/crop transform in provider metadata, and invert it before
   normalizing coordinates.
3. Capture provider/model/checkpoint version and elapsed inference seconds.
4. Record **both** model mistakes and correction minutes on 10+ varied plans,
   including Hebrew dimension text, photographed/scanned plans, and complete
   exterior walls.
5. Do not choose a new primary engine based on a single attractive overlay.
6. Consider license and hosting costs before selecting a production provider.

## Current decision

**Do not replace YOLO-first or tune models yet.** Run the bake-off against real
ground truth first. If Raster2Seq improves connected rooms, investigate a
production adapter. If Tectly dramatically reduces manual correction and
recovers trustworthy metric dimensions, evaluate its total cost and
vendor-dependency trade-offs. If neither improves reliability, retain the
current pipeline and prioritize corrections and calibration benchmarks.
