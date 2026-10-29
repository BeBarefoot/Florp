# Training workflow execution — 29 October 2026

Implemented for local macOS/CPU operation; no new pretrained accuracy claim is made.

## Delivered

- Source-bound dataset workspace, multipage PDF import with per-page retry checkpoints, image orientation normalization, whole-source polygon labeling, undo/redo, selection/vertex edits, zoom, calibration and review filters.
- Automatic pretrained mask proposals and detector opening outlines. Original model evidence is stored separately. Predictions never overwrite corrections. Boxes remain review proposals, not verified training masks.
- Dataset annotation, reconstructed wall topology, pixel-space opening spans and 3D projection saved together in one annotation revision. Overlapping footprint evidence can join corners; explicit opening masks can bridge a compatible host gap. Blank gaps are not forcibly closed. Complex footprints use the existing mask-topology decoder and remain flagged for review. The older project editor is retained for compatibility; its independent saved layouts are not silently migrated/overwritten.
- Annotation revisions now reside in the application SQLite database, with guarded one-time migration from the earlier standalone workspace database. Revision/source mismatch guards remain active. Pending legacy openings have explicit attach/dismiss reconciliation and draft-only preview.
- Immutable datasets with source hashes, complete review, group leakage and duplicate checks. Reviewer identities are self-reported attestations in this local application.
- Training workers serialize locally, retain logs/state, support epoch-boundary cancellation and actual optimizer-checkpoint resume. Interrupted workers are detected by lock state. Restored jobs relocate local paths. No automatic production model promotion.
- Automatic baseline/candidate comparison on validation masks after training, retaining raw predictions, per-class footprint precision/recall/IoU and mask-derived geometry metrics. Test cases are excluded from candidate selection. Independent structural truth and real test evaluation remain distinct from these derived scores.
- Portable archives include original/page sources, historical records, annotations, model evidence, dataset snapshots, available training checkpoints and run logs. Restore rejects conflicts/checksum failures, relocates dataset paths, and restores annotation/structural records in one database transaction. A recovery journal cleans staged uncommitted files on restart. Automatic review-session archives retain two versions; manual backup remains available.
- Operator instructions: TRAINING_OPERATOR_GUIDE.md.

## Validation evidence

Backend suite covers the new reconstruction, source coordinates, opening-only bridging, false-positive footprint scoring, pending-opening resolution, stale revisions, review gates, leak checks, clean restore, relocated snapshots/checkpoints, interrupted restore, training preflight/cancel/resume guards, prediction preservation, retry-safe two-page PDF import, and a synthetic 35-case import/annotation/dataset campaign.

The browser suite covers mask autosave, rejected-ready preservation and previous editor/undo/opening behaviors. Its API responses are mocked; database persistence is separately tested through real API integration tests.

See the PR/session for final test counts and CI outcomes. No real model dependencies/checkpoints are installed in this execution environment: real training, MPS execution, real-plan extraction accuracy, user correction time and production acceptance cannot be reported as tested. Synthetic 35-case acceptance is not an accuracy evaluation of 35 customer plans.

## Boundaries to preserve

Unknown metric scale does not prevent pixel labels; wall/window heights remain explicit draft defaults. Reconstructed room cycles and geometry are hypotheses, not independent structural gold. Complex wall masks and ambiguous opening hosts require review. Automatic OCR association is still the existing provisional estimator, not a new measured scale solution. The local app has no public multi-user security certification. Backup size limits and single-machine worker semantics are documented in the operator guide.

These are product/validation boundaries, not evidence that a trained candidate is production-ready. Do not replace them with an assertion that passing CI proves perfect 2D or 3D extraction.
