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
