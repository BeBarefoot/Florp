# Florp — architecture and delivery gates

Updated October 2026. This is an implementation assessment, not a product accuracy claim.

## Core principle

Treat blueprint evidence, model detection boxes, editable spatial graph, physically
calibrated scene, and photographic rendering as **separate stages**. A detection
score is not geometric confidence; a model wall box is not a measured wall.
Architectural truth is versioned separately from design styling.

## Phase 0 — Local engineering foundation (in place; testing incomplete)

Next.js/React UI, FastAPI API, SQLite, local file storage, PDF/raster upload,
uv-managed backend, versioned layouts and simple 3D display.
**Gate:** CI green, upload/extract/reload/save works for scanned and vector PDFs.
**Missing:** robust integration tests, production authentication/queue.

## Phase 1 — Evidence extraction and model baselines (experimental)

PyMuPDF vector/text evidence, OpenCV Hough line hints, local Tesseract OCR,
consensus-based low-confidence scale hypotheses, optional pretrained YOLOv8
object detector (walls/doors/windows/dimensions/columns), configurable remote
multimodal vision API. Current YOLO checkpoint emits bounding boxes, not pixel
wall masks or junction topology. Existing user corrections include negative
line-candidate labels; these do not assess YOLO recall.
**Gate:** Create a representative, reviewed held-out benchmark; measure detection
precision, recall and calibration separately by class, including photo/scanned
drawings, dimension graphics, furniture and exterior/property lines.
**Missing:** positive and missed-wall ground truth, line-to-box semantic fusion,
building region segmentation, validated scale associations.
**Decision:** benchmark existing YOLO first; only then decide whether another
pretrained semantic segmentation model or fine-tuning is justified.

## Phase 2 — Geometry reconstruction and correction (current focus)

YOLO elongated wall boxes -> unverified wall centerline proposals. Nearby model
door/window boxes -> tentative opening records. Original model boxes remain
optional diagnostics, not a second geometry source. 2D wall edits feed the 3D
preview. Structural-only review is separate from metric verification.
**Gate:** walls connect without false overlaps; openings align with wall graph;
on supported test plans at least 90% reach acceptable verified geometry in <=5
minutes of human review (target, NOT measured).
**Missing:** intersection snapping/shared graph nodes, thickness estimation from
wall masks, room boundary polygonization, edit lineage and training corrections
from changed YOLO predictions, segment/box matching under zoom, undo/history UI.

## Phase 3 — Dimensions and semantic opening fidelity

Collect OCR labels and dimension chains, detect units, relate dimension markers
to endpoints, solve global scale and local dimension consistency. Height/sill
information may require elevations or user confirmation; do not invent them.
Distinguish structural/concrete walls only where legend, schedule or hatching
supports it, otherwise classify as unknown.
**Gate:** no critical metric conflict, missing height, or inferred opening
silently promoted to verified geometry; human correction is targeted to evidence.
**Missing:** robust dimension-chain association, unit inference, wall type
recognition, opening geometry review and validated metric tolerance.

## Phase 4 — Photorealistic scene generation

Freeze verified wall graph, openings, room floor meshes, structural renders
(depth/edge/segmentation as supported), stable camera and design state.
Integrate one actual conditioned image provider; detect and flag structural
drift in output. Neither depth nor a generative model guarantees geometry.
**Gate:** successive material/prompt revisions preserve verified openings, wall
positions and camera within established visual QA tolerance.
**Missing:** scene camera/version persistence, depth renderer, provider-specific
render submit/poll, structural QA and editable styling.

## Phase 5 — Model improvement loop and scale

Retain reviewed wall/non-wall/missed-wall examples with source dimensions,
model version, class and per-prediction edits. Split by blueprint/project before
training to avoid leakage. Benchmark candidate algorithms on held-out projects.
Fine-tune a segmentation/object detector *only if* a measured baseline failure
justifies it. Keep training offline and release with regression gates.
**Gate:** improvement in wall precision/recall AND median review time on held-out
plans, without regressions in opening alignment. Cost and latency tracked.

## Known issues and safeguards

- Scale: `px_per_meter` is internal. The pipeline may suggest it but cannot
  assume it from unrelated OCR numbers; structural-only review should work when
  scale is unknown, metric verification cannot.
- Vision LLM: valid JSON is not guaranteed. Bounded retries and explicit
  truncation/configuration errors avoid overwriting a saved layout.
- YOLO: bounding boxes are approximate. Do not claim concrete wall or full
  polygon recognition. Model-to-geometry conversion is still heuristic.
- UI: all edits must act on one draft geometry version; do not require users to
  manually draw an entire plan. Editing and reject controls are transitional
  feedback collection tools, not the intended consumer workflow.
- Dataset: the current supplied 29-label session contains 28 `not_wall`, one
  `unsure`, and zero `wall` or manually drawn positives. It is not sufficient
  to train a new model and must not be published without approval.

## Immediate next tasks in priority order

1. Run CI and fix Python/TypeScript build or tests until green.
2. Label representative *positive walls* and missing walls, in addition to
   existing negative candidates; retain YOLO box IDs and correction diffs.
3. Convert YOLO wall proposals into snapped connected graph; derive enclosed
   rooms/floors only from topologically closed regions.
4. Improve dimension-chain OCR and scale consensus, with a short review UI.
5. Benchmark precision/recall, opening hit/miss and human editing time.
6. Select whether to fine-tune existing detector or use pretrained wall
   segmentation; avoid premature training.
