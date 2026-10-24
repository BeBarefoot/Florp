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
