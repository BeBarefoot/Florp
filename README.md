# Florp — blueprint to possibility

**Status:** working local-first **Milestone 1 engineering scaffold**, not a completed photorealistic generation product. No secret tokens are included.

## What works now
- Create local projects and upload PNG/JPEG or first-page PDFs.
- Store originals and previews locally; persist project, blueprint and layout versions in SQLite.
- See an explicitly unverified starter geometry overlay, drag room vertices, set scale and save drafts.
- Run **real** LLM image-to-JSON extraction using an OpenAI-compatible chat completions endpoint when `LLM_API_KEY` is configured. Output is schema validated and warnings are shown. Provider errors are surfaced.
- Verify geometries only when basic checks pass. Preview walls and floors in Three.js.
- Baseline unit tests for layout validation; no synthetic AI render masquerading as output.

## Not implemented yet
- Robust line/OCR preprocessing and evidence fusion; PDF page selection; topology reconciliation after room edits.
- Windows/doors in 3D mesh, true depth capture, image-generation submission/polling and revisable material layers.
- Multi-user authentication, production job queue, cost tracing, model training/evals and deployment hardening.
- The image API adapter is an **integration starting point only** and may require endpoint-specific argument and upload changes; it is not wired to the UI.

## Run locally
Requires Python 3.11+, Node 20+ (or compatible). Start two terminals:

```bash
cd apps/api
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp ../../.env.example .env
uvicorn app.main:app --reload --port 8000
```

```bash
cd apps/web
npm install
cp ../../.env.example .env.local
npm run dev
```

Visit http://localhost:3000. Backend OpenAPI: http://localhost:8000/docs.

In `apps/api/.env`, set `LLM_API_KEY` and a compatible `LLM_MODEL` when you are ready to run real image extraction. `IMAGE_API_KEY` is intentionally optional until the render workflow is complete. Never commit `.env`.

## Verify
```bash
cd apps/api && python -m pytest -q
cd apps/web && npm run build
```

## Privacy and safety
The local API is intended for trusted development on localhost only. There is no auth. Do not deploy it publicly as-is, and do not upload sensitive third-party plans without proper handling. Uploaded images are sent to the configured vision provider **only** when the user clicks the extraction action.

## Suggested next commits
1. Local PDF vector evidence, OCR, multi-scale raster plan, geometry schema and confidence attribution.
2. Constraint graph and shared-wall editor, structural validator and annotation diffs.
3. Robust 3D opening meshes, deterministic depth/edge renders, provider-specific image generation and polling.
4. Design-state revisions and masked editing, benchmarks/telemetry, auth, queue and model-training exports.


## Milestone 2: evidence extraction and conservative fusion

The editor's **Show detected line evidence** option overlays PDF-native vector lines (blue) or OpenCV raster Hough lines (orange); the sidebar displays native PDF text or Tesseract OCR tokens. These are *observations*, not verified geometry. The explicit `GET /blueprints/{id}/evidence` endpoint runs locally and needs no API key. When a configured vision model produces a proposed layout, the backend reconciles duplicate wall segments, checks nearby geometric evidence and preserves room coordinates rather than moving them based on uncertain line matches.

For OCR on scanned plans, install the open-source `tesseract` executable on your machine in addition to Python requirements. Without it, the app still works and reports that OCR is unavailable. The current extractor does **not** infer full room polygons solely from OpenCV line detection and does not claim the 90% accuracy target; that requires benchmark evaluation and advanced wall graph reconstruction.


## Milestone 3: wall candidates and inspection UI

The evidence overlay now defaults to a grayscale scan with a **Wall candidates** layer rather than drawing all raw detected lines. A separate **Raw lines (diagnostic)** layer is available. The backend pairs long, nearly parallel lines and filters some text-centered detections; they remain unverified suggestions, not confirmed structure. Click a blue candidate line to preview/accept it as a new **draft wall**. Acceptance is validated against the current evidence and creates a new layout version. Walls may still need careful manual correction; see `docs/CALIBRATION.md` for limitations and benchmarking steps.


## Geometry sync and review update

The **3D floor and boundary walls are generated from the same room polygon points** used by the 2D editor; legacy starter w0–w3 segments no longer create a second stale rectangle. Moving a shared room vertex also moves matching room vertices and stored wall endpoints. Separate manual interior walls use amber strokes and appear in 3D; draw one by clicking two points in **Draw interior wall** mode, then **Save draft**. Remove user-added walls in the geometry sidebar. Invalid, self-intersecting room polygons are omitted from 3D and blocked at verification.

**Wall suggestions are off by default.** When enabled, they are restricted by length, confidence heuristic, and proximity to existing drawn rooms. They are NOT reliable structural wall matches. Raw line diagnostics are also off by default. Floor-plan extraction has not yet reached the desired accuracy target or learned to distinguish all symbols/furniture/windows.


## Wall and opening editing

**Draw continuous wall lines across door/window spans.** The opening is a separate wall-attached record with `wall_id`, offset, width, sill and height (meters). Use **Draw wall** to add interior wall centerlines; clicks snap to existing geometry vertices and nearly orthogonal orientations. Use **Add door** or **Add window**, then click the desired perimeter edge or interior wall to create an opening. Default door: 0.9m width, 2.1m tall, sill 0; window: 1.2m width, 1.2m tall, 0.9m sill. All are *inferred* until manually confirmed. The sidebar allows editing opening dimensions, and the 3D viewer splits walls around openings. Geometry validation rejects missing wall references, opening overflow, overlapping openings and height excess. A calibrated `px_per_meter` is required to position openings. Auto-recognition of doors and windows from the raster input is not yet trustworthy or implemented.


## Detector review and training data

The 2D editor again displays **all automatic paired-line wall candidates by default** (blue). The scope filter switches between *All detections* and *Near current outline*. Select a candidate, then label it **Wall**, **Not wall**, or **Unsure**, or explicitly accept it as a draft wall. Labels persist in SQLite, and **Export training annotations (JSON)** includes reviewed segments and manually drawn walls. This is a dataset collection/evaluation mechanism, not automatic model training. Evaluate precision/recall on labeled plans before considering fine-tuning; screenshots with colored dimension marks and furniture are known failure cases. Candidate scores remain heuristic.

Door/window tools now use the nearest wall centerline to a canvas click instead of requiring a precisely hit transparent SVG stroke. Set **Pixels per meter** first. Openings are editable and unverified until confirmed.

If the OpenAI API returns HTTP 401/403, Florp provides a targeted authentication error. Put an active API key from the correct provider in `apps/api/.env` as `LLM_API_KEY`, confirm `LLM_BASE_URL` and `LLM_MODEL`, and restart the backend. ChatGPT Plus is not an OpenAI API credential.


## Extraction-first workflow and measurement evidence

Local OCR/PDF labels and long axis-aligned vector/scan lines are combined to yield *low-confidence* scale hypotheses via `GET /blueprints/{id}/evidence`, under `scale_suggestions`. These are speculative label-to-line matches, not a verified measurement: clicking **Use estimate** accepts one tentative scale, but the association and unit must be checked. No numeric annotation is silently promoted to verified geometry. The editor allows provisional door/window placement without user entering a scale; provisional metrics remain flagged and verification is blocked until confirmed. Manual pixels-per-meter entry remains an advanced option, not the primary workflow. Accurate semantic wall, door and window identification still requires a reviewed benchmark and dedicated extraction work.

## Groq configuration

Groq: `LLM_BASE_URL=https://api.groq.com/openai/v1`, `LLM_MODEL=qwen/qwen3.8-27b` (check currently available models), and `LLM_API_KEY` set to a valid Groq key. OpenAI model IDs do not transfer automatically to Groq. `GET /vision/provider-check` performs a credential-protected model-list lookup and returns only model status without revealing the key. HTTP 404 and 400 yield actionable configuration messages rather than a generic 502.


## Review local annotation exports

Do not commit users' annotated floor plans into a public repo. Analyze an exported session locally:

```bash
cd apps/api
uv run python scripts/analyze_training.py "/path/to/training session1.json"
```

Session 1 currently contains 31 `not_wall` labels, zero positive walls and zero manually drawn walls. These are valuable negative examples but insufficient to train or evaluate a wall model. We need confirmed walls, missing walls, different blueprint styles and a held-out evaluation set. The report flags class imbalance and duplicate segment labels; it does not claim trained accuracy.


## Optional pretrained YOLO detector (research integration)

Florp can run the actual pretrained `best.pt` from [sanatladkat/floor-plan-object-detection](https://github.com/sanatladkat/floor-plan-object-detection) on the local machine. The upstream project includes a 49.6 MB YOLOv8 checkpoint and is MIT-licensed, **but its Ultralytics inference runtime has AGPL-3.0 / Enterprise licensing considerations**; do not deploy this in a proprietary SaaS without reviewing those terms. This feature is opt-in and NOT enabled in the baseline install.

1. Review the checkpoint source and licensing; PyTorch checkpoint loading can execute code and must only be used with trusted weights.
2. Run `cd apps/api && uv sync --extra pretrained-yolo`.
3. Download the upstream `best.pt` from `https://github.com/sanatladkat/floor-plan-object-detection/blob/main/best.pt` yourself and store it outside Git (e.g. `apps/api/models/best.pt`).
4. Set `PRETRAINED_YOLO_WEIGHTS=./models/best.pt` in `apps/api/.env`; restart API.
5. In the 2D editor click **Run pretrained model**. A local POST to `/blueprints/{id}/pretrained-detections` returns class-labelled bounding boxes and confidence, and draws dashed outlines (purple wall / orange door / cyan window). This does not contact OpenAI, Groq, or another API.

**Do not mistake boxes for geometrically aligned wall centerlines or cut actual openings automatically.** This is a baseline for comparing class detection to the existing line heuristic. Check the real model classes and quality on your scanned plans. Weights are never redistributed by Florp.


## Pretrained model geometry preview (new)

Click **Auto-build 2D + 3D** in the blueprint editor. Florp runs the optional local YOLO model, converts elongated `wall` object boxes into *approximate wall centerlines*, associates nearby `door` and `window` boxes to those centerlines, and persists a new **unverified layout**. The default placeholder room polygon is removed in the generated draft, so the 2D model walls and 3D wall extrusions refer to the **same stored geometry**. The old layout remains a historical version in SQLite.

This is NOT exact wall reconstruction: a box detector does not output room topology, robust corners, wall materials, usable floor polygons, or exact openings. There is intentionally no invented floor mesh for the model draft. Scale falls back to an illustrative 60 px/m for the 3D preview if no dimension was verified; real architectural fidelity needs further validation. Detection overlays can still be toggled independently from editable geometry. The action requires the local pretrained checkpoint; it does not use a paid LLM API.

OpenCV Hough line extraction now reshapes both standard `(N,1,4)` and `(N,4)` arrays into proper 4-coordinate segments. Tests for this regression and the model geometry adapter are in `apps/api/tests/`.


## Stabilization update: wall review vs metric verification

Model-generated 2D cyan wall centerlines can be selected in **Edit** mode. Drag the two green endpoints to correct their positions; **Reject / delete selected wall** removes false positives, along with any openings attached to the wall. Click **Confirm wall positions** to persist a structural review **without requiring metric scale**. **Verify physical dimensions** is a separate, stricter operation and can still be blocked by unknown scale or provisional openings. The training export now includes `model_wall_corrections` with confirmed/adjusted/rejected model-wall results, in addition to legacy Hough-line annotations. This is evaluation/correction data, not model fine-tuning.

Vision-model JSON may be incomplete or truncated. Florp sends a shorter extraction prompt, requests `LLM_MAX_COMPLETION_TOKENS` (default 8192), retries once on invalid or truncated output, and gives an actionable 424 rather than leaking a long Pydantic 502 traceback. API model output quality remains model-dependent. Set an output token count supported by your configured provider and account.

See [roadmap and acceptance gates](docs/ROADMAP_AND_GATES.md). CI checks Python compilation and tests and Next.js type/build on push; check GitHub Actions for actual job results.


## Connected wall topology and room proposal (phase 2)

Florp now has an experimental deterministic reconstruction stage using Shapely.
**Auto-build 2D + 3D** runs the local pretrained detector, produces approximate
wall centerlines, and then attempts to snap nearby endpoints/T-junctions and
find closed room contours. Existing users can **Save draft**, then select
**Propose connected rooms** in the Wall graph health section. The operation
creates a new unverified layout version; it never rewrites the original uploaded
plan or a prior layout version. A read-only wall audit remains available at
`GET /blueprints/{id}/topology`.

Backend API: `POST /blueprints/{id}/topology/propose`, returning the new
layout and topology audit. The solver lives in `app/graph_reconstruction.py`
and uses `shapely>=2` installed by `uv sync` (or
`uv sync --extra pretrained-yolo` for local model inference).

**Safety/limitations:** The algorithm can close narrow gaps, merge nearby
endpoint coordinates, and polygonize enclosed wall segments. Its tolerance is
a heuristic in image pixels, not a validated metric value. It cannot determine
whether walls detected by YOLO are real, and a false-positive closed loop can
still appear as a proposed room. Rooms default to confidence 0 and remain
unverified. Open contours do not produce floors. Wall height, thickness,
material, physical scale and exact opening geometry remain provisional.
Review outputs before selecting **Confirm wall positions**, and do not treat
this as successful floor-plan extraction without benchmark evaluation.

Tests: `uv run pytest -q tests/test_graph_reconstruction.py` covers rectangles,
small/large gaps, T-partitions, and open lines. Full backend/frontend CI also
needs to pass.


## Unified model review (October 2026)

The main workflow is now:
1. Upload a blueprint and select **Auto-build 2D + 3D** (optional local YOLO model).
2. Review **cyan model walls**. Click a wall to move its green endpoint handles or reject it. Use **Confirm wall positions** to save reviewed structure without physical scale.
3. Review **orange door / cyan window detection boxes** by enabling **Model boxes**. Click one to propose an opening on the nearest reconstructed wall. If an inferred opening already occupies that span, the click updates its type/location instead of failing with an overlapping-opening 409. A confirmed opening will not be overwritten automatically. Detected boxes that are too far from walls require wall correction first.
4. Export annotations from the advanced legacy detector review as needed. Model wall adjustments are recorded when structural review is confirmed. These are **training data collection**, not live model training.
5. Verify measurements separately after resolving dimension evidence.

The legacy OpenCV candidate overlay and label UI are now hidden under **Advanced detection layers** and **Advanced: experimental line-candidate labeling**. This avoids confusing those heuristic suggestions with YOLO model geometry.

Projects can now be deleted from the home page with a confirmation. Deleting removes the project's local blueprint files and dependent database records. It cannot be undone.

**Known limitations:** YOLO boxes cannot guarantee exact wall or opening geometry. The model may detect an object without a nearby reconstructed wall; those cases require review. No automatic retraining or background learning happens when a correction is saved. Benchmark results and actual production readiness remain unverified.


## Phase 3 experimental wall-mask segmentation

A **separate segmentation checkpoint** (trained to output a pixel mask for class
`wall` / `walls`) can now be evaluated alongside the existing pretrained
bounding-box detector. This does NOT magically turn the existing
`sanatladkat/floor-plan-object-detection/best.pt` into a segmentation model.

1. Obtain and review a trusted segmentation checkpoint; inspect its license,
   training domain, class mapping and compatibility with Ultralytics.
2. Store it outside version control; set
   `WALL_SEGMENTATION_WEIGHTS=./models/wall-segmentation.pt` in `apps/api/.env`.
3. `cd apps/api && uv sync --extra pretrained-yolo`. Restart the API.
4. In the 2D blueprint editor, expand **Experimental wall segmentation** and
   select **Try wall-mask reconstruction**. The API runs locally; it requires
   mask tensors and refuses to substitute ordinary object bounding boxes.
5. Examine proposed mask-derived centerlines and topology. These are rough
   Hough-derived lines supported by local pixels, *not* calibrated CAD walls.

The new endpoint `POST /blueprints/{id}/segmentation/propose` writes a new
unverified draft version. It refuses to replace metric-verified layouts,
structurally approved layouts or layouts containing user-drawn walls. It clears
old wall IDs/openings when forming a separate segmentation proposal, since
carrying their anchors to different centerlines would corrupt the model.
Previous saved layouts remain available in the database, but the app does
not yet include a general version-restoration UI. **Do not run this experiment
on unsaved edits.** If the checkpoint is absent or returns bounding boxes
without masks, the API responds with a clear 424 and does not modify the draft.

`app/wall_segmentation.py` contains the local mask interface, class filtering,
resolution normalization, conservative mask-supported straight-line extraction
and unverified proposal conversion. `tests/test_wall_segmentation.py` covers
synthetic masks. It is not a benchmark of real wall segmentation accuracy.
Next research step: compare a trusted real segmentation checkpoint against the
existing YOLO boxes on a held-out, annotated set of Florp scans (wall pixels,
junction completeness, opening preservation and human correction time).

Existing YOLO **Auto-build 2D + 3D** and review workflows are unchanged.


## Yytsi pretrained segmentation — use PNG/JPG/PDF directly (no SVG required)

Florp now provides a **native raster adapter** for Yytsi's pretrained
ResNet34-UNet model. Yytsi's public demo expects CubiCasa-style SVG; converted
images such as `width="992.000000pt"` trigger its SVG dimension parser and,
more importantly, don't carry the CubiCasa structural class tokens. The
Florp adapter bypasses SVG entirely:

- Upload PNG/JPG normally; the original RGB preview goes into Yytsi.
- Upload PDF normally; Florp first rasterizes page 1 at 2× into PNG, then
  supplies the preview directly to Yytsi.
- Yytsi's own config determines model resolution, aspect-preserving letterbox,
  ImageNet normalization and model/device. Class predictions are cropped to
  unpadded image content and nearest-neighbor scaled back to the source
  blueprint's original coordinates.
- The result includes wall-mask pixels overlaid in teal on the 2D drawing,
  proposed wall centerlines, and unverified connected-room hypotheses.
- Yytsi's 4 classes are floor, wall, door, window. The experimental endpoint
  currently vectorizes the **wall** pixels; door/window class masks are not
  yet converted to full opening graph objects. The YOLO opening workflow
  remains separately available.

### Setup on Mac (only once)

```bash
git pull origin main
cd apps/api
uv sync --extra yytsi
mkdir -p models/yytsi
curl -fL --retry 3 -o models/yytsi/best.safetensors 'https://huggingface.co/Yytsi/floorplan-to-3d-walls/resolve/main/best.safetensors'
curl -fL --retry 3 -o models/yytsi/config.yaml 'https://huggingface.co/Yytsi/floorplan-to-3d-walls/resolve/main/config.yaml'
```

Set these in `apps/api/.env`:

```dotenv
WALL_SEGMENTATION_PROVIDER=yytsi
YYTSI_RUN_DIR=./models/yytsi
YYTSI_CHECKPOINT=best.safetensors
YYTSI_DEVICE=auto
```

Restart FastAPI with `uv run uvicorn app.main:app --reload --port 8000`.
Then open any PNG/JPG/PDF blueprint in Florp, expand **Experimental wall
segmentation**, and click **Try wall-mask reconstruction**. Keep **Show actual
wall pixels** enabled to compare predicted mask against the plan. It works
without a paid AI API key. `YYTSI_DEVICE=cpu` forces CPU; `auto` uses the
upstream implementation's MPS/CUDA/CPU detection.

Do not re-run this on an edited or confirmed layout: the experiment intentionally
rejects user-drawn or reviewed walls, to avoid discarding corrections. Previous
saved versions are retained in SQLite, but there is not yet a version-restore UI.
Start a new blueprint copy to compare the models safely.

**Quality limitation:** Yytsi was trained on filtered CubiCasa SVG renders,
where nonstructural elements were removed programmatically. Real scanned PNG
plans contain furnishings, dimensions and noise. This domain shift may produce
many false walls and missed walls. Don't confuse an operational model adapter
with proven accuracy. Benchmark the raw overlay and then the wall graph separately.

### Upstream SVG-only demo workaround (optional)

For a converted SVG such as the one that reported
`could not convert string to float: '992.000000pt'`, the immediate parsing
error is caused by Yytsi's
`buildingcv.data._read_svg_dims` calling `float(root.get("width"))` without
handling physical unit suffixes. Setting unit-free SVG dimensions consistent
with `viewBox` avoids that exception, but **does not make converted PNGs into
CubiCasa semantic SVGs**. Prefer Florp's raster adapter above.


## Troubleshooting the Oct 26 local wall/3D issues

- **`POST /blueprints/{id}/pretrained-reconstruct` returns 424:** that action uses
  the **original YOLO detection checkpoint**, not Yytsi. Check
  `http://localhost:8000/models/status` and the response body of the failed
  request in browser DevTools. Confirm `PRETRAINED_YOLO_WEIGHTS` points to an
  actual local `best.pt` and install
  `uv sync --extra pretrained-yolo --extra yytsi` to enable both paths.
  The status endpoint checks local files/dependencies; it does not test whether
  the checkpoints are architecturally compatible until inference starts.
- **`ChunkLoadError` for `Viewer3D.tsx` or `/_next/undefined`:** Next.js
  failed to load a local development chunk. Stop the frontend, delete its
  generated **`apps/web/.next`** directory, and run
  `npm install && npm run dev` from `apps/web`. Hard-refresh your browser.
  Do not delete your API's `apps/api/data` SQLite/storage directories.
  If it persists, inspect the **Next.js terminal output** for a bundle/build
  exception; a broken build requires fixing the reported error.
- **Yytsi mask has some teal inner walls, but reconstructed walls are absent:**
  inspect the **actual mask overlay**, not only the 3D wall solids. Pixel-mask
  segmentation and mask-to-line extraction are different failure stages.
  The vectorizer now supplements Hough lines with morphological horizontal/
  vertical mask-supported runs. This may recover connected segments that Hough
  drops, but cannot invent an interior wall absent from the semantic mask.
  Yytsi's model operates at 512-pixel input with aspect-preserving letterbox;
  narrow scanned interior walls can be under-resolved, and the model was
  trained on a different image domain. A held-out annotated benchmark is still
  needed before making detection-accuracy claims.
- **Comparison:** run YOLO and Yytsi on separate blueprint uploads while
  debugging. The experimental segmentation replaces the *unverified* draft
  wall list, and cannot import old opening-wall anchors safely.


## Source-supported bottom/exterior wall recovery

**Why:** YOLO finds some wall boxes but can miss an entire bottom boundary.
The legacy **Auto-detected walls** checkbox only drew diagnostic lines and did
not feed 3D. It is now labelled **Legacy line hints** and kept under
**Advanced: diagnostic lines (not used in 3D)**.

The **Recover missing wall candidates** button beside the blueprint calls
`GET /blueprints/{id}/missing-wall-suggestions`, which now combines:
- Image-supported gap bridges between already detected wall endpoints; and
- One conservative long horizontal lower/exterior run, when the image pixels
  support it and an existing vertical wall provides a nearby structural anchor.

Candidates are shown in orange and are **not created automatically**.
Select **Add wall** to add one to the current draft, where it appears in 2D
and 3D; select **Save draft** to persist. Dismiss erroneous candidates.
The source remains unchanged and approved geometry is never silently extended.

This bottom-run recovery is a geometric heuristic. It does not prove the
candidate is a structural or concrete wall, and is not general wall
segmentation. Long dimension lines near the building can cause false
suggestions. Missing walls elsewhere or a completely absent facade still
require reviewed segmentation/other evidence.


## Main wall path: multi-scale masks and connected-region axes (October 2026)

The experimental segmentation action now runs **Yytsi wall softmax on a whole
image and overlapping local 448 px source-image tiles**. Each tile is
letterboxed to the checkpoint's network input using the existing inference
adapter, predicted at its own resolution, mapped back to the original source
pixels, and combined with the global prediction using feathered tile weights.
The default fuse weight for global context is 0.65; tile overlap is 30%.
The original PNG/PDF-preview coordinates are preserved, and only the source
wall probability is thresholded. The tiled result is displayed as the teal
**wall-pixel mask**. Predictions can differ from prior releases even using the
same checkpoint.

The new `app/mask_topology.py` uses **directional morphology + connected
components** to propose horizontal and vertical axes from wall-mask regions,
instead of relying exclusively on Hough edges. Existing graph reconstruction
then snaps possible junctions and polygonizes closed contours; it remains a
proposal and does not implement a full persistent half-edge wall graph yet.

Set optional values in `apps/api/.env`:

```dotenv
SEGMENTATION_MULTISCALE=true
SEGMENTATION_TILE_SIZE=448
SEGMENTATION_TILE_OVERLAP=0.30
SEGMENTATION_MAX_TILES=64
SEGMENTATION_WALL_THRESHOLD=0.46
```

Do not increase tile count arbitrarily on a Mac CPU. A 992×440 image needs
several network passes and may run noticeably more slowly than global-only.
If the image requires over `SEGMENTATION_MAX_TILES` the API returns an
actionable error instead of allocating unbounded work. Tiling helps thin
walls **only when the model recognizes their pixels**; it is not a substitute
for dataset-matched fine-tuning or topology validation.

To compare with the previous baseline, set
`SEGMENTATION_MULTISCALE=false`. Use separate unreviewed blueprint copies;
the segmentation endpoint does not overwrite approved/manual geometry, and
the app currently lacks a version-restoration UI.

Tests: `uv run pytest -q tests/test_multiscale_topology.py`. Before
claiming higher accuracy, inspect the teal mask for missed interior walls and
measure connected components, false positives and correction time using
held-out reviewed plans. CI and local checkpoint runtime validation are
required before promoting this pipeline to the default homeowner workflow.
