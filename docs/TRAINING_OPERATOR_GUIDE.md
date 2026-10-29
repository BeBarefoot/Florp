# Florp Training & Annotation Standard Operating Procedure (SOP)

## 1. System Setup & Initialization

- **Environment Startup:** Launch the API and web app following local development guidelines. Ensure your trusted local segmentation checkpoint is specified in `WALL_SEGMENTATION_WEIGHTS`.
- **Runtime Installation:** Install optional runtime dependencies using `uv sync --extra pretrained-yolo`. Confirm that model and data permissions are correctly set. Note that no checkpoints are downloaded implicitly.
- **Hardware Requirements:** Apple Silicon Macs with unified memory require a compatible MPS environment; standard CPU execution is available for small smoke tests.

## 2. Importing and Managing Blueprints

1. **Source Ingestion:** Import floor plan PNGs, images, or multi-page PDFs. Every page of a PDF is treated as an independent case.
2. **Resilience & Error Handling:** If an import is interrupted, re-importing the identical file will safely retain already completed pages. Any error logs will specifically identify the failed file.

## 3. Model Proposal Extraction & Manual Annotation

1. **Generate Proposals:** Select a case and click **Extract Model Proposals**. This captures original mask and detector evidence without overwriting any existing human annotations. If model weights are unavailable, configure the path or proceed with direct manual labeling.
2. **Opening Footprints:** Door and window bounding boxes serve as initial coarse outlines. Operators must refine them into the exact physical opening footprint, explicitly excluding swing arcs.
3. **Comprehensive Review:** Inspect the entire source plan, not just model proposals. Select *Wall*, *Door*, or *Window*, click polygon vertices sequentially, and select **Finish Polygon**. Click any existing mask to drag and adjust vertices, or delete false-positive objects. Undo and Redo are fully supported for all polygon operations.
4. **Complex Structures & Gaps:** Split bent or concave footprints into straight wall instances wherever practical. Complex masks are decoded automatically by the mask-topology engine and flagged for manual review. **Never** fill unsupported blank gaps solely to artificially close a room boundary.
5. **Scale Calibration:** Use **Calibrate Known Length** only when physical scale is required: click two known reference points, enter the real-world distance in meters, and confirm. Operating without a known scale is fully supported for mask annotation (opening spans remain in pixels until calibrated). Heights rely on explicit draft defaults.

## 4. Saving and Revision Control

- **Autosave & Recovery:** Autosave confirms successful server revisions. Local browser recovery retains pending mask modifications; keep the browser tab open until the status explicitly reads **Saved** before switching devices.
- **Integrity Guards:** Source hashes and revision controls reject stale writes. Operators must fix any flagged invalid polygons before proceeding.
- **3D Preview Verification:** Inspect the 3D preview derived from the current saved annotation revision. Note that this view represents an active draft and is not a certified architectural measurement. The legacy project editor remains accessible for older projects, and dataset annotations never silently overwrite saved layouts.

## 5. Dataset Curation & Quality Assurance

1. **Building Grouping:** Assign a real building group ID to ensure related floors and scans stay grouped together.
2. **Split Allocation:** Designate the split (`training`, `validation`, or `test`). For a baseline corpus of 30 independent buildings, target an initial distribution of 15 train, 5 validation, and 10 test examples. Scale up counts to improve statistical confidence.
3. **Attestation & Readiness:** Confirm rights, record the primary author and the independent reviewer, and select **Mark Ready** only after a complete, exhaustive source review.

> *Note:* Recording a second reviewer's name serves as an administrative attestation, not an authenticated cryptographic identity. **Never fabricate a second reviewer.**

## 6. Backup & Archiving

- **Session Backups:** Download a full backup archive after each review session. Archives bundle original sources, page histories, model evidence, dataset snapshots, training logs, and available weights.
- **Restoration:** Restoring into a clean installation will not overwrite existing cases or local files. Always maintain a secondary backup copy outside the primary machine. Archives are capped at 2 GiB compressed / 4 GiB expanded; larger corpora require external storage partitioning. Keep trusted checkpoints strictly private.

## 7. Model Training & Comparison Workflow

1. **Snapshot Preparation:** Generate a training snapshot. The builder will automatically reject missing splits, duplicate sources, building data leakage, incomplete reviews, or malformed labels. Draft cases are preserved in the workspace but excluded from training. Snapshots remain immutable even if subsequent annotations are modified later.
2. **Job Configuration:** Select your target device, epoch budget, batch size, and random seed, then click **Train Candidate**. On macOS, start with a batch size of 1 and execute a short smoke run before launching long training jobs.
3. **Worker Persistence:** The local worker serializes training tasks. It survives API restarts and persists status/logs prior to model loading. Stop requests are cooperative and process cleanly at epoch boundaries.
4. **Resuming Training:** Job resumption requires a saved optimizer checkpoint (`last.pt`), rather than a fresh weights-only restart. If a machine interruption occurs, the job status reports as interrupted once the worker lock releases; resume from the checkpoint or start a new run if no checkpoint exists.
5. **Validation & Evaluation:** Completed runs compare the baseline checkpoint against the best candidate using the validation split, recording per-case predictions, mask precision/recall/IoU, and geometry metrics. Inspect false positives and false negatives thoroughly. Model outputs are never automatically promoted.
6. **Production Release:** Experiment with multiple seeds, tuning exclusively on training and validation data. Freeze your chosen candidate before running the separate held-out release evaluator.
