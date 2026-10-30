# Source-image extraction: measured result and release limits

The previous color-only workspace output discarded major connected walls. The
new strip fitter keeps separate horizontal and vertical runs in an L/T network,
measures thickness across scan bands, and projects nearby perpendicular
junctions without repeatedly averaging their coordinates. It does not fill a
blank gap to force a room to close.

The workspace also has an **explicitly configured local semantic evaluation
path**. It uses the supplied CubiCasa model to locate structure, corroborates
colored-plan runs against the source, removes contained raster fragments,
refines opening spans against physical color gaps, and emits the same editable
`Document` used by save, calibration, 3D and export. Model output is unreviewed.
Color-only extraction remains the default. No checkpoint or upstream model
implementation is bundled or downloaded implicitly.

## What was tested

Exact uploaded original: 992 × 440 pixels, SHA-256
`38fa5011aa0f72777610e3641d8c404f0a7253c94f0ff4a1e4ac6b88d5696dc4`.
No manual geometry edits were made to the candidate output.

| Check | Result |
| --- | --- |
| Visible structural spans, manually traced independently | 21 |
| Reference centerline recall within 5 source pixels, previous main worker | 35.14% |
| Same reference check, single-pass semantic candidate | 100% |
| Candidate cold process times, including imports, model loading, inference, document serialization | 3.785 / 3.929 / 3.828 s |
| Five-second target on this environment | Passed these three runs |
| 3.5-second target | Not met |
| Twenty-second hard worker budget | Passed |
| CPU inference thread limit | 8 |
| Mac CPU / MPS hardware benchmark | Not performed |
| Confirmed real-world scale | None; one known reference remains necessary |

The centerline check is **recall on this single image**, not overall accuracy.
It does not establish false-positive rate, opening correctness, wall thickness
accuracy, room dimensions, or behavior on other plans. Material transitions can
split one physical opening across multiple host segments. The image is cropped
at the bottom; no missing content is invented.

A second supplied plan remains unreliable. An independently tested Yytsi
checkpoint also misclassified large regions of these photographs and was not
selected for this path. The four-rotation CubiCasa trial took approximately
4.94–5.13 seconds cold, with no sufficient benefit on the uploaded image to
justify making it the default.

## License boundary

The official CubiCasa repository publishes CC BY-NC 4.0:
https://github.com/CubiCasa/CubiCasa5k/blob/master/LICENSE

The local checkpoint evaluated came from the official repository's linked
pretrained model. This evaluation is **not approval for unrestricted commercial
use**. The adapter remains opt-in and marks its results accordingly. Resolve
model/implementation permissions or replace the provider before a commercial
release. No weights or upstream implementation are committed to Florp.

## Reproduce the local evaluation

Use only a trusted local copy of the upstream implementation and a checkpoint
you are permitted to use. This workflow does not add a training dataset or
annotation queue to the product.

From `apps/api`:

```bash
uv sync --extra semantic-eval
export WORKSPACE_SEMANTIC_SOURCE=/absolute/path/to/CubiCasa5k
export WORKSPACE_SEMANTIC_WEIGHTS=/absolute/path/to/model_best_val_loss_var.pkl
export WORKSPACE_SEMANTIC_DEVICE=cpu
export WORKSPACE_SEMANTIC_ROTATIONS=1
uv run python scripts/evaluate_workspace.py \
  --image /absolute/path/to/original.png \
  --output /absolute/path/to/evaluation \
  --runs 3
```

The same environment variables configure `/workspace/extract` in the app.
`WORKSPACE_SEMANTIC_DEVICE=mps` is supported as an explicit request; device
failures do not silently change providers. Partial/missing configuration fails
instead of downloading assets or silently falling back to color extraction.
Both semantic environment paths empty restores the color-only default.

Outputs: `document.json`, `clean.png`, `overlay.png`, `clean.svg`, `report.json`.
PNG/SVG coordinates are source pixels. They are not metric CAD exports and do
not claim a 50 cm margin without a confirmed reference. In the main workspace,
set one known length to derive metric measurements and the 50 cm export margin.
The source photograph still needs planar rectification if perspective or lens
warping makes a uniform scale invalid.

## Validation and remaining acceptance criteria

Backend regressions cover L/T branches, independent parallel axes, preserved
blank gaps, median thickness at crossings, contained-fragment suppression,
source-refined mixed-label windows, opening hosts, monochrome fallback,
cropped-edge labels and invalid local model paths. Existing save/version,
calibration, export, dataset and legacy editor tests remain in the full suite.

Before calling the extraction production-ready:

- Measure false positives and missed structure on independent complete plans.
- Independently verify opening spans, thickness and clear room dimensions.
- Benchmark cold/warm latency and memory on the supported Mac hardware.
- Resolve the evaluated provider's commercial permissions or use a permitted
  replacement and rerun these checks.

Passing synthetic tests or recovering these 21 centerlines does not satisfy
those remaining criteria.
