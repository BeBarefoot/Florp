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
