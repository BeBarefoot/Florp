# Mac parser evaluation and integration plan

Status: proposed; not implemented or benchmarked. Baseline Florp main a2c470e.
The direct Linux/CUDA Raster2Seq comparison has been removed from the active UI,
API and configuration. Historical benchmark examples remain for provenance.

## Important dependency and rights check

Takheer/floorplan-back is a Raster2Seq-based FastAPI MVP, not an independent
model. Its CPU PyTorch fallback is claimed by its README, but Mac execution has
not been demonstrated here. The default official checkpoint is CC BY-NC 4.0;
source, dependencies, dataset and weights have separate terms. Inspect the
upstream repository's actual license and secure explicit commercial rights before
using this checkpoint for commercial development or service. Until then, use only
for permitted noncommercial evaluation. Do not download or run arbitrary untrusted
checkpoints or copy upstream configuration files containing secrets.

## Where Florp stands

- Yytsi segmentation and detector fusion, human candidate review, 2D editing,
  graph-based repair proposals and 3D draft preview are present.
- The corrected example contained 36 non-placeholder wall entries, 30 graph
  components, 64 loose endpoints, no closed faces, one provisional opening and no
  confirmed scale. These are graph diagnostics, not accuracy measurements.
- Extraction metrics require independent reference annotations and source raster.
  The original source raster and gold truth were not available for this report.
- Parser has not been integrated, executed on Mac, or evaluated against Florp.

## 1. Freeze and prepare

1. Record `git rev-parse HEAD`, macOS version, chip, memory, Python and uv versions.
2. Obtain the original source PNG/PDF for each plan, rights to evaluate it, and
   hash the exact raster Florp uses. Use the same rendered image for both systems.
3. Select diverse plans; group variants/floors by building before splitting.
   Start with a small development sample, then freeze at least 10 independent
   held-out buildings. Never tune on this test set.
4. Independently annotate complete wall axes, opening spans/hosts and room
   boundaries; confirm scale from source dimensions. Have a second reviewer
   inspect the entire drawing, including false negatives. The supplied corrected
   JSON is a useful draft but is not complete gold truth.

## 2. Mac feasibility spike

1. Record the exact upstream parser commit and dependency versions; inspect the
   README, license, model card and network behavior before installation.
2. In an isolated Python 3.11 environment, follow the upstream setup for CPU;
   explicitly use a local trusted checkpoint with documented hash. Avoid sending
   plans to external services. Test startup, health, failure paths and one sample.
3. Record Apple Silicon/Intel, architecture, CPU/MPS availability, memory peak,
   model load time and per-plan runtime. CPU fallback is not proof of compatibility.
4. Save raw response and a screenshot/overlay; inspect that polygons map to the
   original pixel coordinates. Stop the spike if installation, rights, memory or
   source-coordinate checks fail. No new Florp adapter has yet been implemented.

## 3. Build an isolated, reviewable adapter

1. Pin upstream revision and isolate service dependencies. Add bounded upload,
   timeout, cancellation and actionable error handling; avoid embedding weights.
2. Define a versioned adapter contract containing original image SHA-256,
   dimensions, model/checkpoint hash, raw source coordinates and provenance.
3. Map room polygons and shared vertices into canonical graph proposals. Split
   intersections and track original IDs; do not close unsupported gaps.
4. Map opening endpoints to real host walls. Preserve ambiguous/unmatched openings
   as pending; never clamp widths silently. Keep scale unknown unless confirmed.
5. Expose a side-by-side comparison and a previewable, reversible apply action;
   never overwrite a saved/verified draft or existing corrections.
6. Test mapping with fixture examples: non-square input, crossing/T junctions,
   parallel walls, gaps, source mismatch, malformed data, windows on split walls,
   ambiguous hosts, stale revisions, failure/timeouts and undo/redo.

## 4. Run the same blind evaluation

For every frozen test plan save the original model outputs from both Florp and
the parser before correction. Compare against independently reviewed truth with
the same image hash, source dimensions and tolerance. Record wall length
precision/recall, junction and adjacency F1, per-room IoU, full window/door span
precision/recall, host accuracy, scale error, correction minutes, failure rate,
latency and memory. Keep raw prediction, reference, options and hashes.

Florp's `docs/PRODUCTION_2D_PROCEDURE.md` describes its available dataset and
release-evaluation commands and minimum test gate. Some metrics, notably opening
host accuracy and per-room evaluation, still require additional implementation or
explicit manual measurement. A parser-specific normalizer and real prediction
export are not implemented: do not imply the commands work directly on raw parser
JSON. Report failures and missing metrics, not only successful examples.

## 5. Decide and improve

Choose the candidate only after evaluating coverage, correction effort, Mac
runtime and commercial rights. If neither meets the agreed gate, categorize
errors (mask, wall topology, opening host/span, scale, domain shift); first fix
coordinate transforms and reconstruction. Train only if controlled experiments
show model errors remain dominant, using the separate HTML guide and a licensed,
independently reviewed dataset. Never call a result production-ready solely
because tests or a single plan pass.

References: https://github.com/Takheer/floorplan-back ;
https://huggingface.co/haopt/Raster2Seq ; docs/VALIDATION_RESULTS.md.
