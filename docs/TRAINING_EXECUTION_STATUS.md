# Training workflow implementation status — 29 October 2026

This branch implements working annotation tooling but does not complete the training-readiness contract. It must not be presented as production-ready or as a measured detection improvement.

## Implemented

- Dataset workspace at `/dataset`, linked from home. Multiple-file upload uses existing project ingestion (PDF first page only).
- Source-bound polygon masks for wall/door/window, vertex dragging, deletion and mask undo. Debounced annotation autosave, local recovery copy and optimistic server revision checks. Existing geometry editor remains separate.
- Append-only SQLite annotation revisions in configured persistent storage. Incomplete drafts can save. Ready requires complete valid polygons, rights confirmation and distinct reviewer identities (self-reported; not authenticated).
- Building group/split controls. Immutable dataset preparation invokes the existing validator: requires train/validation/test and rejects duplicate sources, leakage, invalid masks and hash mismatch.
- Downloadable dataset snapshots. Annotation archive includes original/raster, annotation histories, layouts, graph revisions, candidate decisions and evaluation records with checksums. Clean-install restore and conflict/corruption rejection tested. It is not a full system backup: training runs/checkpoints/render assets/project metadata are not included. Restore spans two databases; crash-atomic recovery remains incomplete.
- Background local training launcher with CPU/MPS selection, configured trusted local checkpoint, dataset/checkpoint identity validation, single-worker lock, persistent status and bounded log reads. It invokes the existing trainer and never promotes a model. This is not a durable queued scheduler; competing runs fail explicitly. Cancellation, optimizer resume and interrupted-machine recovery remain incomplete.
- Opening-anchor reconciliation API and UI: attach a preserved legacy span to an explicit host or dismiss with a reason. The original evidence remains in revision operation history. Draft-only wall preview can bypass pending-opening rendering; default projection and graph application retain strict guards. No pending openings are silently rendered or discarded.

## Local validation

- Backend: `uv run --directory apps/api pytest -q`: **228 passed**, one pre-existing Starlette/httpx deprecation warning.
- Browser: `npm run test:ui` in apps/web: **11 passed**. Browser tests use mocked API responses; API persistence and clean restore are separately covered by backend integration tests.
- Frontend production build: successful before final server-only worker/test additions; final rebuild run recorded in session output.
- `git diff --check`: passed.
- No real pretrained training, Mac/MPS execution, 35-plan batch experiment, real-model accuracy benchmark or new measured detection accuracy result.

## Remaining contract work

A unified graph/mask editor and authoritative revision; lossless pixel-space opening migration and span editing; evidence-ranked semantic gap repair beyond short snapping; shared floor/opening topology; improved OCR dimension association; full multipage PDF/batch jobs; full mask redo/split/merge and zoom/pan; issue prioritization and coverage review; real-API browser acceptance; whole-system backup/restore and cross-database crash atomicity; resumable/cancellable resource-limited jobs; real Mac train/reload/infer smoke test; complete host/room/scale/automatic-repair metrics; frozen corpus evaluation; public-service hardening.

The code preserves existing editor behavior instead of prematurely claiming the separate graph, draft and mask stores have been unified. Polygon editing is available to gather draft labels; do not claim that all operator/developer intervention has been eliminated. No additional user decision is needed to continue this engineering work.

## Operator entry points

Start existing API and web services, open Dataset from home, import/select a case, draw and correct true object footprints, assign building and split, save drafts, complete independent review, prepare a snapshot, download it, and launch a candidate run if configured. Set `WALL_SEGMENTATION_WEIGHTS` to a trusted licensed local segmentation checkpoint. CPU is the default; use MPS only on a compatible Mac. The launcher's runtime errors appear in the run log. Never mark incomplete labels Ready solely to make preparation succeed.
