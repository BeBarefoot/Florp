# Florp dataset and training workflow

## Start

Run the API and web app using LOCAL_DEV.md. Open **Dataset** on the home screen. Configure your trusted local segmentation checkpoint in `WALL_SEGMENTATION_WEIGHTS` and install the optional runtime with `uv sync --extra pretrained-yolo` in apps/api. Keep model/data permissions appropriate to your use. No checkpoints are downloaded implicitly. MPS needs a compatible Mac; CPU is available for a small smoke run.

## Review a collection

1. Import PNGs/images or multipage PDFs. Every PDF page is a case. If interrupted, reimport the identical file: completed pages are retained. Errors identify the failed file.
2. Select a case and choose **Extract model proposals**. This captures original mask/detector evidence without replacing existing annotations. If the model is unavailable, configure it or draw labels directly. Door/window boxes are initial outlines; edit them into the physical opening footprint, excluding swing arcs.
3. Review the whole source, not only model proposals. Choose Wall, Door or Window, click polygon vertices and Finish polygon. Select a mask to drag its vertices; delete false objects. Undo/Redo support polygon operations. Zoom and scroll to inspect small details. Split bent footprints into straight wall instances where practical; complex masks are decoded by the mask-topology engine and flagged for inspection. No unsupported blank gaps are filled merely to close a room.
4. Autosave acknowledges a server revision. Local recovery retains pending mask edits; leave the tab open until Saved before changing devices. Source hash and revision guards reject stale writes. Fix invalid polygons when indicated. Use **Calibrate known length** only if needed: click two known points, enter meters and confirm. Unknown scale does not prevent mask annotation. Opening spans are retained in pixels until scale is available. Heights use explicit draft defaults.
5. Inspect the 3D preview from the same saved annotation revision. It remains a draft, not a measurement certificate. The older project editor remains available for existing projects; dataset annotations do not silently overwrite saved layouts.
6. Assign the real building group so related floors/scans stay together. Set train/validation/test. For 30 independent buildings, start with 15 train, 5 validation and 10 test; additional examples improve statistical confidence. Confirm rights, record the author and independent reviewer, then mark Ready only after complete source review. A second name is an attestation, not an authenticated identity. Never invent a second reviewer.
7. Download a backup after each review session. Archives include original/page sources, histories, model evidence, dataset snapshots, training logs and available weights. Restore into a clean installation; existing cases/files are not overwritten. Keep a second copy outside the machine. Archives are limited to 2 GiB compressed / 4 GiB expanded; larger corpora need external storage/partitioning. Keep trusted checkpoints private.

## Train and compare

1. Prepare a snapshot. The builder refuses missing splits, duplicate sources, building leakage, incomplete reviews or malformed labels. Draft cases stay preserved but are excluded. Snapshots never change when later annotations change.
2. Choose device, epoch budget, batch size and seed, then Train candidate. Start with batch 1 on Mac and perform a small smoke run before a long experiment. The local worker serializes training. It survives an API restart, and stores status/logs before loading the model.
3. Read logs and refresh jobs. Stop requests are cooperative at epoch boundaries. Resume is available only when a saved optimizer checkpoint exists; it uses `last.pt`, not a fresh weights-only restart. A machine interruption is reported as interrupted after the worker lock is released. Resume after restart; if no checkpoint exists, start a new run.
4. Completed runs compare the initial checkpoint and best candidate against the validation split, saving per-case predictions and mask precision/recall/IoU plus geometry comparison. Inspect false positives and false negatives. Model outputs are never automatically promoted. A failed validation comparison appears as a failed job with its retained training artifacts.
5. Try several seeds and tune only on training/validation. Freeze the chosen candidate before running the separate held-out release evaluator described in PRODUCTION_2D_PROCEDURE.md. The validation report's graph references are derived from masks; independent reviewed structure, opening hosts, scale and timing are still required for a production accuracy claim. Test results cannot honestly be supplied before the real corpus is annotated and evaluated.

No new real-model accuracy is implied by passing software tests. Mac/MPS runtime and model quality must be observed on your hardware and actual plans. The local app is not a publicly hardened multi-user service.
