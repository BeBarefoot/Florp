# Florp — Extraction Accuracy Sprint (Mac-first, commercial-product roadmap)

**Scope:** Restore a simple user experience, create genuine ground truth, quantify
the accuracy gap, and choose ONE production extraction strategy. Do not ship
Raster2Seq's CC BY-NC checkpoint in a commercial service. Do not assume the
YOLO or Yytsi pretrained-weight/data license is automatically commercially cleared.

## 0. Run the application on an Apple Silicon Mac

```bash
git pull origin main
cd apps/api
uv sync --extra pretrained-yolo --extra yytsi
uv run pytest -q
uv run uvicorn app.main:app --reload --port 8000
```

In another terminal:

```bash
cd apps/web
npm install
npx tsc --noEmit
npm run dev
```

Open http://localhost:3000. The existing `apps/api/.env` must point to
actual local YOLO and Yytsi checkpoints; see `GET /models/status`.
Using pretrained research checkpoints for local testing does not establish
commercial distribution rights. `RASTER2SEQ_ENABLED=false` should remain
the default on a Mac.

## 1. Collect a real benchmark dataset

Use **10 plans** at minimum, with deliberate variety:
- 3 clean digital plans with dimensions
- 3 scanned/photographed plans (including imperfect scans)
- 2 cropped/touching-edge plans
- 2 plans with unusual interior partitions, door arcs, and windows

Include existing failures: the cropped bottom-wall case and the plan with
missing lower-left inner partitions. Do not use ten near-identical screenshots.
Keep the original full-resolution upload and SHA256 unchanged. Do not upload
plans you lack permission to store or test.

Split the dataset before future fine-tuning: 6 development, 2 validation,
2 **held-out test**. Do not optimize on held-out plans. Expand to 30+ varied
plans before claiming robust product-level geometry accuracy.

## 2. Run a complete evaluation in Florp

For **each blueprint**, perform the same steps:

1. Upload the original PNG, JPG, or PDF.
2. Click **1 · Extract and compare** in the left sidebar. Florp runs the
   configured YOLO/Yytsi comparison and displays the predicted wall lines,
   proposed doors/windows, and segmentation evidence.
3. BEFORE manually correcting any geometry, click
   **Save uncorrected model baseline**. This stores source-image SHA256,
   extraction provider, initial proposal and layout version in SQLite.
4. Review every wall (exterior and interior), door, window, junction, and
   available dimension. Mark incorrect proposals as nonwalls, doors or
   windows, add missing walls, adjust ends, and avoid inventing an opening
   across a structural wall.
5. Accept selected proposals into the **unsaved** draft; then correct wall
   geometry. Use **2 · Save corrected draft** to preserve an editable
   layout version. The original baseline never changes.
6. Confirm that corrections are independently checked against the SOURCE
   IMAGE, not copied from the AI overlay. When all items are reviewed,
   tick the human-review attestation.
7. Enter actual active correction minutes, plus brief notes such as
   "2 bottom exterior and 3 bathroom partition segments missing".
8. Click **Score reviewed geometry**. Evaluation results persist even after
   refreshing the editor; view previous runs in **Saved evaluations**.

**Careful:** the metric compares your *whole corrected reference* with the
initial AI proposal. It is not reliable if you leave a placeholder room
outline or an uncorrected inferred wall in the reference. Human review is
explicitly required. A saved draft is not automatically ground truth.

If you do NOT have dimensions in the source, leave pixels-per-meter
unconfirmed. Missing scale is not scored as 0% accuracy or guessed.

## 3. Stored data, retrieval and backup

New SQLModel table: `extractionevaluation`, using existing SQLite file
`apps/api/data/florp.db` unless `DATABASE_URL` is configured otherwise.

Each evaluation stores:
- stable ID, blueprint reference, image SHA256, provider name, layout version
- immutable model baseline (JSON in **original** source pixels)
- human-checked reference geometry (JSON) and active correction duration
- precise benchmark metric JSON, notes, completion status, creation time

API routes:
- `POST /blueprints/{bid}/evaluations` — capture model baseline
- `GET /blueprints/{bid}/evaluations` — list historical scores
- `POST /blueprints/{bid}/evaluations/{evaluation_id}/finish` — score after
  independent human review

Records stay **local** with the SQLite database and blueprint images. Back
up the entire `data/` folder (DB + storage), NOT just the database.
Do not delete projects if you want to preserve evaluation records.
This version has no cloud synchronization or export of all evaluation rows;
use the SQLite database backup as the authoritative record.
Existing `training-export` remains separate: it captures user-candidate
classification events but is NOT a verified gold-standard drawing.

## 4. What the metrics actually mean

| Metric | How measured | Interpretation |
| --- | --- | --- |
| Wall precision | 1:1 matched AI wall segments / all proposed segments | False positives |
| Wall recall | 1:1 matched AI wall segments / human reference segments | Missing walls |
| Wall F1 | Harmonic mean of precision/recall | Balanced detection |
| Opening F1 | Same for aligned door/window spans (when scale allows) | Opening completeness |
| Room-area IoU | Intersection/union of room polygon AREA sets | Rough floor completeness |
| Scale error | Relative difference of pixels per metre | Dimension calibration |
| Correction time | Manually entered *active minutes* | Actual homeowner friction |

Current wall matching allows 8 source-image pixels positional tolerance and
12 degrees orientation difference, plus >50% shorter-segment overlap. This
is a **coarse segment-level metric**. Large wall segmentation differences,
split walls, room adjacency, wall thickness, opening attachment, and common
junction IDs are not yet accurately measured by these scores.

**Do not compare scores between differently sized images as if an 8px
threshold means the same physical distance.** Record scan resolution and
confirm actual dimensions whenever possible. Do not average room IoU with
wall F1 into one arbitrary "accuracy" number.

## 5. Manual structural checklist (must accompany numeric scores)

For each drawing record in notes:
- Are *all* exterior boundaries present? (yes/no)
- Missing interior partition count
- False walls count (including furniture/text mistaken for structure)
- Dangling junction count and broken room boundaries
- Wrong/missing door count; wrong/missing window count
- Whether readable dimensions were converted to the correct metric scale
- Actual active correction minutes
- Whether the drawing is a clean PDF, scan, or mobile photograph

These manual observations are necessary until fine-grained topology and
opening measurements are grounded in independently verified data.

## 6. Release gates: what good enough means

**Initial target (before broader testing):**
- 100% of important exterior boundaries represented on held-out examples
- wall recall >=90% with precision >=90% for supported input classes
- no silently invented confirmed dimensions
- all proposed openings remain visibly provisional until reviewed
- 80% of test drawings corrected in <=5 active minutes
- no model output ever silently overwrites a saved reviewed layout

For a commercial v1, expand held-out tests substantially; validate
photographs, scans, notation language, edge-touching plans and actual 3D
alignment. The above are **acceptance targets**, not measured outcomes.

## 7. Commercial viability decision

**Do not select a checkpoint on image aesthetics alone.** Verify:
1. model source and weights license, any dependency copyleft obligations,
   and whether training datasets permit intended commercial use
2. local Apple Silicon MPS operation, RAM demands, batch size, latency
3. recall and false-positive rate on held-out plans
4. time needed for an ordinary user to fix residual errors
5. ongoing cloud/CPU costs and vendor reliance

Raster2Seq remains isolated/disabled on Mac; released checkpoint is
CC BY-NC and upstream relies on CUDA. It is a research quality-reference,
not a deployable commercial Mac-first foundation.
Commercial vendor outputs such as Tectly could define a **quality gap**
if an authorized account/API and real output schema become available;
they are not currently integrated or scored automatically.

**Next model investment:** after initial 10-plan dataset, compare current
YOLO and Yytsi independently via `docs/EXTRACTION_BENCHMARK.md`. If both
fail interior partitions, evaluate a fully licensed, MPS-compatible
segmentation architecture with commercial-rights-cleared weights/training
data; only then implement an alternative extraction engine.
Avoid stacking more heuristic fusion stages by default.

## 8. Common failure handling

- **No extracted candidates:** inspect `GET /models/status`, configured
  checkpoints and backend console.
- **Previous edit already started:** save/discard that unsaved edit before
  capturing model baseline, or start an entirely new evaluation.
- **Partial or ambiguous result:** keep it marked provisional and note it.
- **Cannot truthfully attest full wall/opening review:** do not finalize
  benchmark. Resume the draft later.
- **Green CI:** means Python regression suite and TypeScript build pass;
  it does NOT certify 90% detection accuracy or model licensing.
- **Scores unexpectedly 0%:** inspect source image identity, coordinate
  scale, segmentation splitting, and correct wall endpoints; do not
  automatically interpret as a failed model.

## 9. The one-screen user flow

Default controls:
- Left sidebar: **Extract and compare → Save corrected draft →
  Measure extraction quality**.
- 2D canvas: recognized walls and opening review; tools to draw missing
  walls/doors/windows.
- Advanced (collapsed): LLM extraction, Raster2Seq research comparison,
  raw segmentation, legacy OpenCV candidates, detailed topology, and
  expert scale controls.
- 3D preview stays available, but *verification follows corrected 2D*.

Success means a repeatable dataset and honest comparison numbers,
not another button or new model announcement.
