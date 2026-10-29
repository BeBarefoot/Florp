# Florp: exact 2D extraction and training procedure

## What is true today

This is a production-readiness procedure, not a declaration of production readiness.
No arbitrary-plan extractor can be guaranteed perfect. Success means a measured
release gate, explicit uncertainty, faithful corrections and reversible versions.

The two October 28 exports show:

| Item | Saved v3 | Corrected v4 |
|---|---:|---:|
| Stored wall entries | 38 | 40 |
| Legacy placeholder walls | 4 | 4 |
| Actual wall entries after removing placeholders | 34 | 36 |
| Physical openings | 1 | 1 |
| Confirmed metric scale | No | No |
| Wall-supported room faces | 0 | 0 |
| Canonical disconnected groups | 30 | 30 |
| Canonical loose endpoints | 64 | 64 |

V4 adds three manual walls, deletes mask-29-gap-0, and reshapes mask-47-gap-0 and
mask-48-gap-0. Its single room is the old starter rectangle. The blue rectangle
is exactly that placeholder at (52.8,52.8)–(939.2,387.2); it is not a detection.
There are 20 additional door/window classifications without physical geometry.
These are draft supervision candidates, not complete training references.

The code now starts new uploads empty, strips exact untouched placeholders from
legacy layout responses/saves/exports without rewriting history, preserves moved
or opening-hosting legacy walls, exposes geometry readiness, couples coincident
endpoints during manual edits and protects opening-hosting walls from accidental
moves. A valid graph is not necessarily an accurate graph.

## 1. Freeze and reproduce the baseline

1. Pull main; run `uv sync` in apps/api and `npm ci` in apps/web. Restart both.
2. Preserve the original source PNG used by the backend (not a UI screenshot).
   Keep its SHA256 and original width/height with every annotation/prediction.
3. Create a new project; extract once; save an uncorrected evaluation baseline.
4. Review, apply labels, repair geometry, save the corrected draft. Export saved
   walls + labels. Record actual correction time; do not backfill guessed times.
5. Never use the corrected geometry as the baseline or the baseline as gold.

## 2. Correct the source contract before training

Minimum editor workflow: **Upload → Extract → Review/repair → Save**. Scale and
opening dimensions are required before metric 3D verification. Dataset preparation,
training and benchmarking are CLI workflows, not extra tasks for homeowners.

For every plan:
- Trace all actual wall axes, including exterior runs and partitions missed by
  either model. Remove furniture, dimension lines and duplicate wall evidence.
- At T/X intersections use shared junctions and split edges. Moving one shared
  junction must move all incident walls. Do not join offset parallel wall faces
  merely because they are close.
- Review closed faces individually. An enclosed closet and an accidental line
  cycle are not interchangeable. Open contours are not floors.
- Put each opening on its real host and confirm its full source-image span.
  A classified window with no host is unresolved. Do not clamp a detection to fit
  a short wall and call the resulting window accurate.
- Confirm at least one reliable dimension and cross-check a second dimension on
  another axis. If they disagree, resolve crop, perspective, OCR or unit errors.
- Compare 2D to the original image, then 3D to 2D. Never repair 3D independently.

Current remaining modeling limits: uncertain missing walls, offset-axis matching,
overlapping detections, unknown-scale openings and semantic room classification
still require review. Existing provisional opening creation uses heuristics; it
is not a ground-truth annotation tool. Segmentation training cannot by itself
solve the global graph reconstruction problem.

## 3. Build a licensed, diverse annotation corpus

Start with a 50-plan annotation pilot, then expand by error strata. This is a
planning target, not a claim that 50 plans are sufficient. Include scans, vector
PDF renders, Hebrew/English labels, different drafting conventions, thick/thin
walls, stairs, balconies, oblique walls, furniture and poor contrast. Obtain
permission to use each source for the intended training/deployment.

Assign `group_id` by building/project/source drawing family BEFORE splitting.
All crops, revisions, floors and augmentations of a group stay in one split.
Use approximately 70% train / 15% validation / 15% locked test by independent
groups. Keep at least ten independent test buildings for the minimum release gate;
expand the test set to cover every intended customer segment.

Annotate pixel polygons in an annotation editor, one instance per wall run,
door or window. Use the original raster coordinate frame. Wall polygons describe
actual occupied wall regions, not inflated bounding boxes or arbitrary thickness
around a centerline. Split complex connected masks into simple instances so no
hole is silently filled. Include thin, diagonal and short structural walls.
Door/window masks describe the physical opening span on the host, not door-swing
arcs or nearby dimension text. Inspect every false-negative region.

Require a second review of the whole image, not just accepted model proposals.
The saved Florp draft is useful as a starting point, but its axes do not supply
true wall thickness/mask polygons. Do not relabel an incomplete export as gold.

## 4. Prepare a versioned dataset (implemented)

From `apps/api`:

```bash
uv run python -m scripts.prepare_training --schema annotation
uv run python -m scripts.prepare_training --schema manifest
```

Create one annotation JSON per image:

```json
{
  "schema_version": 1,
  "width_px": 992,
  "height_px": 440,
  "independently_reviewed": true,
  "annotation_complete": true,
  "reviewer": "reviewer-id",
  "objects": [
    {"kind": "wall", "polygon": [[100,80],[300,80],[300,88],[100,88]]}
  ]
}
```

The coordinates above illustrate the schema only. They are not labels for the
user's plan. Include EVERY wall, door and window; set review/completeness true
only after that work is finished.

Create `corpus/manifest.json` with a `cases` array. Each entry:

```json
{
  "id": "building-a-floor-1",
  "group_id": "building-a",
  "split": "train",
  "image": "images/building-a.png",
  "annotation": "annotations/building-a.json",
  "source_sha256": "REPLACE_WITH_EXACT_64_CHARACTER_SHA256",
  "usage_rights_confirmed": true
}
```

Paths are relative to the manifest. Include independent train, val and test cases.
Then run:

```bash
uv run python -m scripts.prepare_training \
  --manifest /absolute/corpus/manifest.json \
  --output /absolute/datasets/florp-v1
```

The builder checks dimensions, source hashes, finite/in-bounds/nondegenerate
polygons, complete review, duplicate source and decoded images, and group leakage.
It writes normalized YOLO segmentation polygons, PNG images, dataset.yaml and
provenance hashes. Output is immutable; use a new directory for every version.
The minimum three-case schema is a smoke-test minimum, not enough training data.
Do not generate detection boxes from corrected centerlines and mistake those for
wall segmentation masks.

## 5. Train a segmentation candidate (implemented entrypoint; real training pending)

Use the existing optional Ultralytics runtime after resolving code/checkpoint/
training-data licensing. This is a candidate route compatible with Florp's current
mask adapter; it is not a promise that YOLO segmentation is the winning model.
Keep Yytsi and the current checkpoint as baseline candidates.

```bash
uv sync --extra pretrained-yolo
uv run python -m scripts.train_segmentation \
  --dataset /absolute/datasets/florp-v1 \
  --model /absolute/trusted/segmentation-checkpoint.pt \
  --output /absolute/runs/florp-v1-seed42 \
  --epochs 100 --imgsz 1024 --batch 4 --device mps --seed 42 --dry-run
```

After reviewing that configuration, run the same command without `--dry-run`.
Use `--device 0` on a configured CUDA machine or `--device cpu` for a small smoke
run. Choose batch size from available memory; 100 epochs is a starting budget,
not a convergence guarantee. The script refuses detection-only checkpoints,
modified prepared datasets and existing output directories. Checkpoints must be
trusted local files; no model download or production promotion is implicit.

The initial run disables mosaic/flips/perspective to preserve plan semantics.
Tune augmentation, input resolution, confidence thresholds and decoder parameters
on validation data only. Compare at least three seeds and inspect failures by
plan type. Record dependencies, machine/device, checkpoint SHA and dataset SHA.
The trainer records run configuration, versions and returned metrics in
`florp-run.json`; retain `uv.lock`, training logs and the actual best checkpoint.

Do not pick a model using test scores. Once architecture and thresholds are fixed,
run the locked segmentation test ONCE for that release candidate:

```bash
uv run python -m scripts.train_segmentation \
  --dataset /absolute/datasets/florp-v1 \
  --model /absolute/runs/florp-v1-seed42/weights/best.pt \
  --output /absolute/runs/florp-v1-heldout \
  --imgsz 1024 --batch 4 --device mps --test-only
```

Mask/detection metrics are component metrics. They do not measure whether the
final apartment has connected walls, correct opening hosts or correct rooms.
No real checkpoint training/inference was executed in the implementation session.

## 6. Integrate only in a comparison environment

Set in an isolated API environment (retain old values for rollback):

```dotenv
WALL_SEGMENTATION_PROVIDER=ultralytics
WALL_SEGMENTATION_WEIGHTS=/absolute/runs/florp-v1-seed42/weights/best.pt
PRETRAINED_YOLO_WEIGHTS=/absolute/runs/florp-v1-seed42/weights/best.pt
```

The segmentation checkpoint must use wall/door/window class names. Its masks feed
wall proposals; its object boxes feed opening hints. Restart the API to clear
cached models. Re-extract the frozen original images with no manual corrections;
export both predictions and independently reviewed references using the existing
benchmark export schema (`app.extraction_exports`, docs/EXTRACTION_BENCHMARK.md).
Use source-specific checkpoint hashes and decoder versions in metadata.

## 7. Evaluate the complete pipeline (implemented minimum gate)

Create a separate release manifest with `split: "test"`, `frozen: true` and cases:

```json
{
  "image": "original.png",
  "truth": "gold-prediction-schema.json",
  "prediction": "candidate-prediction-schema.json",
  "group_id": "building-a",
  "independently_reviewed": true,
  "exterior_complete": true,
  "opening_spans_reviewed": true,
  "correction_seconds": 180
}
```

Reference and prediction use PlanPrediction (not arbitrary geometry JSON); both
must match the actual source hash/dimensions. `exterior_complete` is the human
assessment of the CANDIDATE's exterior. `opening_spans_reviewed` means the reviewer
checked every candidate host/span; it must not be prefilled. Correction time is
measured from the uncorrected candidate until the independent reference is met.

```bash
uv run python -m scripts.evaluate_release \
  --manifest /absolute/release/cases.json \
  --output /absolute/release/report.json
```

Exit 0 means the implemented geometry gate passed; exit 2 means it failed.
Minimum requirements:
- At least ten distinct source images and ten independent building groups.
- Per-case wall LENGTH precision and recall >=90%, within 3 source pixels.
- Junction and wall-adjacency F1 >=95%; room-region F1 >=90%; references include
  closed supported rooms. Use stable source raster resolution when choosing the
  pixel tolerance; three pixels is this gate's explicit versioned policy.
- Opening ENDPOINT-span precision and recall >=95%, within 3 pixels. This catches
  wrongly shortened windows that overlap-based object matching can miss.
- No missing exterior boundary, independently checked.
- At least 80% of cases corrected within five minutes.

Also measure scale error, exact window-host identity, per-room IoU, door swing,
wall thickness, latency (p50/p95), peak memory and failure rate. The minimum CLI
checks are NOT the entire production acceptance suite. Document thresholds for
these additional metrics before launch; do not waive them because CI is green.

## 8. Production engineering gates still required

Before public multi-user deployment, implement/test authentication, project-level
authorization, upload limits/content validation, safe PDF processing, job queue,
timeouts/cancellation/retries, rate limits, model isolation and resource budgets.
Add structured logs with source/model/decoder/revision IDs, latency/error metrics,
backup/restore drills, versioned migrations, retention and deletion handling.
The current local FastAPI prototype is not a public multi-tenant service.

Run integration tests with real models and representative files, load/soak tests,
and adversarial uploads. Canary the accepted checkpoint with rollback to the
previous checkpoint/config. Monitor subgroup quality and drift; collect corrected
failures with permission; adjudicate them before including the next training set.
Never silently overwrite a verified plan during re-extraction.

## Remaining human steps versus remaining engineering

Human work: obtain original plans/rights, annotate full masks and structural gold,
adjudicate disagreements, assign leakage-safe groups, run/fund training, measure
correction time and approve a successful held-out result.

Remaining engineering: improve graph reconstruction until the gate passes on the
real corpus; replace provisional opening/scale heuristics where they fail; finish
window-host/room/width accuracy gates and public-service hardening above. It would
be incorrect to say that only training remains or that this code is perfect.

## Primary references checked for this procedure

- https://docs.ultralytics.com/datasets/segment/ — polygon label contract.
- https://docs.ultralytics.com/modes/train/ — training configuration/API.
- https://www.ultralytics.com/license — review applicable licensing before launch.
- https://docs.pytorch.org/tutorials/beginner/basics/saveloadrun_tutorial.html —
  checkpoint state and safe loading guidance for any future custom architecture.

## Editor flow and remaining UX work

This change follows the recovered Research audit findings recommendation to keep
review on the drawing and separate advanced diagnostics. The main screen opens
on the plan and its one-item inspector. Repair tools and scale/details are below
the drawing in closed sections; training/evaluation is closed in the sidebar.
The unfinished rendering assistant is removed from this extraction workflow.

1. Extract and compare. Inspect proposed walls on the source plan.
2. Review walls and gaps, then opening classifications. Apply reviewed proposals
   explicitly to the draft; a classification alone does not create an opening.
3. Repair connections or missing walls when needed. Move shared endpoints together.
   Hosted openings require reconciliation before their shared junction can move.
4. Confirm scale and opening dimensions using the source's dimension labels.
5. Save the corrected draft, then independently verify the structure.

This is a simplification of the existing editor, not the full mockup implementation.
The follow-up spatial review adds selectable enclosed regions, boundary editing,
shared-partition removal, and loose-endpoint navigation. These are provisional
regions, not semantic room classification. Unified graph/draft persistence and
spatial review of all reconstruction alternatives remain required before claiming
the full research UX is delivered. Existing graph revision undo
remains available under Repair connected geometry.

Main draft undo/redo now covers local geometry edits, with each endpoint drag
grouped as one action. Saving or loading a server layout resets local history;
saved versions remain immutable. Graph revision undo remains a separate scope.


### Room and gap review (spatial follow-up)

Open **Rooms & gaps** to select a shaded enclosed region or an amber endpoint.
Select a room boundary in the adjacent inspector and drag its green handles.
Use **Draw partition in this region** to split a region using the existing
snapping wall tool. Use **Remove shared partition** to combine adjacent review
regions; this is disabled if the wall hosts an opening, or if any part of its
source wall is exterior/unshared. Undo restores the partition. Derived regions
refresh from the current draft after edits and are not automatically approved
or exported as physical floors. **Model candidates** returns to detection review.
