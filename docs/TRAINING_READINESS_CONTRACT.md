# Florp: complete training-readiness contract

29 October 2026 · Code inspected against main `6f669535570628d68850d51aa3d3c9b5432a2bb2`.

**Status: implementation plan, not completed fixes or measured extraction accuracy.** This is one bounded delivery with one acceptance checklist, not another series of phases. It supersedes the fragmented editor/training workflow in earlier plans. Preserve those documents as historical evidence. The goal is that an operator can import, annotate, validate, back up, train and compare 30+ plans without editing JSON, fixing code or asking a developer to recover data.

Thirty plans are an initial supervised improvement experiment, not evidence of production accuracy. No plan can guarantee that arbitrary floor plans will become perfect after training. Completion means the tooling works end to end, failures are actionable, and accuracy is measured honestly.

## What is actually wrong today

| Evidence | Meaning | Required resolution |
|---|---|---|
| Screenshot: 56 loose endpoints, 0 enclosed regions; connection preview reduces endpoints to 53 | Short endpoint snapping cannot reconstruct missing walls or distinguish all openings | Evidence-based reconstruction plus explicit gap classification; never optimize the endpoint count alone |
| Screenshot: `422: Cannot export: pending legacy opening anchors need reconciliation` | In `graph_adapter.to_geometry`, any pending opening blocks projection. Import can make openings pending when scale is absent, host missing, or a span crosses split edges | Lossless migration, pixel-space anchors, visible reconciliation and separate draft versus verified export contracts |
| `CanonicalWorkspace.tsx` imports repaired graph into another draft; `PlanGraphRevision` and `Layout` store separate state | Users must understand two models, histories and save paths | One authoritative revision used by both 2D and 3D |
| `automatic_connections.py` uses 4 px tolerance and skips user walls, hosted openings, reviewed structures and geometry with rooms | It deliberately covers only a small subset of gaps | Preserve conservative behavior until replacement has evidence and regression coverage; do not merely enlarge the radius |
| `training_dataset.py` requires complete polygons and independent review | Corrected centerlines and accepted candidate boxes are not segmentation ground truth | Add complete mask annotation and review to the editor, linked to structural annotations |
| Screenshot still shows a Raster2Seq button, while the inspected main removed that active workflow | Displayed build may differ from main; screenshot alone cannot identify why | Show frontend commit, API commit, model and schema versions in About; detect incompatible builds |

No new accuracy measurements or runtime tests were performed for this planning document. The original raster and full matching current revision are needed to reproduce the screenshot failure exactly. Add that case as a regression fixture after obtaining them; do not manufacture ground truth from screenshots.

## The operator experience

### Dataset workspace

Open **Dataset**, drop 30+ PNGs or PDFs, name the collection, and group related floors/scans by building. PDF pages become separately selectable cases. Keep original uploads and normalized page rasters. Show thumbnails and columns: plan name, building, processing status, review progress, unresolved issues, save status, split, reviewer and last edit. Filters: Needs review, In progress, Ready, Failed. Actions: Import, Continue review, Export backup and Train candidate. Batch extraction runs in the background with per-file retry/cancel; one failed file never stops the collection.

Normal navigation has only **Dataset · Review · Training runs**. Hide provider selection, raw detector output, graph diagnostics and parameter experiments in a developer panel. Remove the normal-flow buttons for graph initialization, graph import, separate repair previews, repeated Apply/Save/Confirm actions, model comparison and baseline capture. Their useful behavior becomes internal pipeline work or a single reversible suggestion.

### One review screen

- Top bar: plan name, previous/next plan, Undo/Redo, clearly acknowledged save status and 2D/3D toggle.
- Left tool rail: Select, Wall, Door, Window, Region, Scale. Contextual mask-outline editing is available when labeling a selected object.
- Center: large zoomable source image and overlay; pan, fit, source/overlay visibility and opacity. A minimap supports large drawings. Selection remains visible when the inspector changes.
- Right inspector: one selected object or one issue, its evidence crop, reason, proposed correction and at most three relevant actions. Primary action is **Accept**, **Edit**, or **Resolve**. **Next issue** advances spatially, with the ability to revisit any decision.
- Bottom strip: walls/openings/regions reviewed, scale state and remaining blocking issues. Distinguish “12 items checked” from “whole plan checked.”

Use solid blue for saved draft geometry, amber plus an icon for uncertain proposals, and green for selected handles. Do not use color alone. Keep original prediction visible only through an optional comparison layer. Tooltips and keyboard equivalents accompany controls; support keyboard navigation, visible focus and an inspector drawer on smaller screens.

### The repeatable per-plan procedure

1. **Open the next plan.** Automatic extraction, conservative repair and original-prediction capture have already run. Failed extraction offers Retry or Start manual annotation on the same source.
2. **Resolve highlighted issues on the drawing.** Missing wall, false wall, junction, opening host/span and scale are categories in one queue. Draw missing objects, delete false ones, drag shared nodes, and edit opening spans directly. No coordinate forms or JSON editing.
3. **Check the entire source, including unhighlighted areas.** Guided coverage tiles prevent “no detected issues” from being mistaken for completeness. Inspect wall footprint polygons as well as axes; edit polygons where thickness or shape is wrong. Check every door/window span, room boundary and intentionally open passage. Source image alone can be toggled to reduce model anchoring bias.
4. **Set scale if necessary.** Confirm correctly associated dimensions, or click two points on a known segment and enter its real length with units. Unknown scale does not block pixel annotation. Do not guess ceiling/window heights from a 2D PNG; keep explicit configurable defaults or measured values.
5. **Submit for review, then mark Ready and open Next.** The second reviewer checks the entire plan and adjudicates discrepancies. A solo review stays provisional rather than falsely claiming independent review. All edits autosave; Ready creates an immutable approved annotation revision after validation.

Returning tomorrow restores the same plan, viewport, issue and pending edits. No manual baseline saving, file renaming, per-plan download or repeated application between 2D and 3D is required.

## Code changes required to deliver that experience

### One plan contract and lossless persistence

Extend `plan_graph.py`, `models.py`, `graph_adapter.py`, `graph_operations.py`, `graph_validation.py` and API contracts around one versioned source-bound plan. Store source image hash/dimensions, transform chain, shared nodes, walls, opening spans, derived regions, scale evidence and object provenance. Each object distinguishes predicted, edited, reviewed and verified states. Keep masks as a separate linked annotation layer: a wall axis does not define its true footprint.

Represent editable openings in source pixels or normalized positions along a directed host edge, independent of scale. Derive metric offsets and widths only when scale is available. Preserve direction through reversal/split/merge; remap spans transactionally and retain lineage. Treat openings crossing a junction as an explicit ambiguity; never silently shrink, drop or duplicate them. Store missing/ambiguous host evidence and resolution reasons.

Migrate legacy data with a pre-migration backup, dry-run report, idempotent versioned migration and old-to-new IDs. Keep every original Layout and opening record. Automatically reconcile only unambiguous mappings. For the rest, present **Choose host**, **Adjust span**, **Not an opening**, or **Leave unresolved** on the canvas. Leaving unresolved permits save/backup but excludes the case from applicable verified exports. Do not remove the 422 guard without replacing its invariant checks.

Generate 2D, 3D, derived metrics and exports from the same acknowledged revision. Compatibility endpoints project that revision into old response formats. Re-extraction creates a separate candidate revision; it never overwrites corrections or approved truth. One undo history covers all editing operations. Undo creates a new revision rather than deleting audit history.

Use server transactions, expected revision checks and idempotency keys for edits. Local queued edits survive refresh via IndexedDB; server storage remains authoritative. Show Saved only after acknowledgment. Distinguish Saving, Offline edits retained and Save failed—Retry. Recover interrupted writes; surface conflicts rather than overwriting another tab. Ensure moving Next flushes or durably queues edits and never implies they reached the server when they did not.

### Detection and reconstruction

Keep current models as frozen baselines. Normalize EXIF orientation, PDF rendering, crop and deskew once, recording reversible transforms. Preserve original and normalized sources. Every mask, box, OCR line and graph point must round-trip through this transform contract; test non-square images, rotations, crop offsets and multiscale padding.

Combine wall-mask evidence with line orientation, thickness, local source pixels and opening candidates. Skeletonize/fit wall runs, merge duplicates, split true intersections and construct shared nodes. Preserve diagonal walls; do not force Manhattan geometry everywhere. Make gap tolerances relative to local wall thickness and image normalization, bounded by validation-tested limits rather than arbitrary large pixel radii.

Classify candidate gaps as: endpoint misalignment, missing wall, door, window, intentional passage or uncertain. Rank alternatives using continuous wall-band evidence, collinearity, compatible thickness, junction support and competing opening evidence. Dark pixels alone are insufficient because text, furniture and dimension lines also contain ink. Only high-confidence nonconflicting repairs apply automatically; medium-confidence alternatives enter the issue queue; unsupported geometry remains unresolved. Existing reviewed objects are locked unless explicitly unlocked.

Model a wall host with opening intervals so doors/windows do not become accidental missing wall segments. For room derivation, use explicit topological boundaries across hosted openings without filling their physical 3D apertures. Intentional passages and partial drawings require explicit boundary semantics, not forced closure. Report invalid gaps separately from legitimate free ends. Derive planar faces, reject self-intersections and exclude the exterior face; room names are separately reviewed.

Pair OCR labels to dimension lines/endpoints with units and orientation, then check independent scale estimates for agreement. Conflicting or absent evidence produces a calibration request. Retain uncertainty and source provenance. Do not treat OCR text detection as successful measurement extraction.

Validate 3D from canonical endpoints, scale and opening spans. Test axis orientation, wall length/thickness, winding, floors and aperture cuts. Incomplete plans can preview with an explicit warning, but verified geometry export must reject unresolved structural defects. Backup export never rejects an incomplete plan.

### Complete annotation and dataset export

Add polygon vertex/edge editing, split/merge, undo and object selection for wall, door and window masks. Seed annotations from predictions but require correction against the source. Label actual wall footprints; exclude door swing arcs, text and furniture. Define a consistent opening-footprint convention and wall-mask treatment at apertures in a versioned illustrated label guide before labeling. Support diagonal/curved boundaries with polygons; split shapes with holes into supported simple polygons without filling holes.

Store two linked truths: segmentation masks for model fitting, and structural graph/opening hosts/room boundaries/scale for reconstruction evaluation. A centerline-only correction is useful structural truth, not a complete mask dataset. Validate object links without requiring an artificial one-to-one relationship where an opening splits a wall mask.

Extend `training_dataset.py` with annotation revision/source binding, reviewer and adjudication records, taxonomy version and immutable snapshots. Preserve the current wall/door/window class mapping. Mark missing objects, ambiguous source regions and excluded cases explicitly; do not mark incomplete labels complete simply to pass export. If the selected trainer cannot represent ignore regions, exclude ambiguous cases or resolve them before training.

Add a dataset snapshot API that writes original sources, normalized rasters, raw predictions, canonical revisions, masks, reviewer decisions, transforms, scale evidence, split assignments and provenance. Generate all training annotation JSON, YOLO labels, dataset configuration and end-to-end evaluation inputs automatically. No hand-authored manifests in the normal workflow.

### Training runs and recoverability

Wrap `prepare_training.py`, `train_segmentation.py` and `evaluate_release.py` in durable background jobs with progress, logs, cancellation, failure reason and restart recovery. Add preflight checks for label completeness, group leakage, checkpoint task/classes, source hashes, free disk space and runtime/device availability. Run a tiny real train/save/reload/infer smoke test on the actual Mac before offering a full run. Prefer tested MPS on Apple Silicon; provide explicit CPU fallback and smaller batches when necessary. Intel Mac uses CPU unless another supported execution target is configured. No Linux/CUDA dependency in the required operator workflow.

Record dataset/model/config/code hashes, environment, device, seed, timestamps, metrics and artifacts before execution so failed jobs retain evidence. Save best and latest checkpoints periodically. Distinguish true optimizer-state resume from starting a new run using weights; never present them as equivalent. UI offers Resume only when compatible state exists. Log memory failures, allow a smaller-batch retry as a new run, and keep the previous run immutable.

A run page shows baseline versus candidate overlays, per-plan/class metrics, correction effort and regressions. Model promotion is explicit and reversible with stored checkpoint/config identities. Running training never changes the default production model. Parser comparison remains optional and off the critical path; it is not an installed, evaluated replacement today.

## What gets saved, and where

Server database stores collection/case IDs, revisions, reviews, jobs and artifact references. A configurable persistent data directory holds original files, rasters, masks, predictions, dataset snapshots, logs and weights. Do not store the only copy in a browser, temporary directory or Git checkout. Use checksums and atomic file writes, and test disk-full behavior.

**Export backup** creates a portable versioned archive containing database export, assets, labels, splits, model/run metadata and checkpoints when selected. Include checksums, schema version and a restore manifest. A normal backup includes unfinished work and pending openings. **Export training dataset** includes only eligible immutable annotation revisions and reports exclusions. These are different operations.

Automatic backups run after completed review sessions and before migrations; configure retention and a second storage destination. Show last successful backup and failures. Restore into a clean installation must recreate every case, review, split and run reference without absolute-path dependencies. Archive restore validates checksums and rejects path traversal. Source files and private labels stay out of Git by default.

## Exact procedure for the first 30+ plans

1. Choose diverse original plans and record usage permissions. Include clean exports, scans, thin walls, small windows, diagonal walls, Hebrew/other dimension labels and typical customer layouts. Group related floors, scans and variants by building.
2. Freeze a practical initial split of **15 training / 5 validation / 10 test building groups** when 30 independent groups exist. Multiple pages from one building stay together. If 30 files represent fewer groups, collect additional buildings rather than leaking them across splits. These counts are a starting experiment, not a training sufficiency claim.
3. Import and batch-extract using the unchanged baseline. Preserve raw results and configuration before any corrections. Label all objects and structural truth through the five-step review procedure. Second-review every approved case; measure active correction time separately from independent QA time.
4. Generate immutable dataset v1. Run validation and a real Mac smoke training job. Fix any acceptance failure in the delivered tooling before beginning the full annotation campaign; no manual data repair as a workaround.
5. Train a trusted licensed segmentation checkpoint through the UI. Start with the existing script's 1024 input, 100-epoch budget and seed 42, with device/batch selected by the smoke test; these are starting settings, not optimal values. Train additional seeds 43 and 44 if the resource budget allows. Use validation data for early stopping, checkpoint selection, confidence thresholds and reconstruction settings.
6. Compare four controlled configurations on validation: original detector + original reconstruction; original detector + new reconstruction; trained detector + original reconstruction; trained detector + new reconstruction. This identifies whether improvement comes from masks or geometry. Capture model-only and end-to-end metrics; do not treat training loss as extraction accuracy.
7. Freeze the chosen candidate and evaluate once on the locked test set without manual correction before scoring. Measure correction time afterward against the same reviewed truth. Include failures in denominators. If test failures guide further tuning, that set becomes development evidence and a fresh independent test set is needed for the next release claim.
8. Promote only a candidate passing the declared accuracy gates, with no critical regressions and a working rollback. Otherwise retain baseline, show which error categories dominate, and collect targeted examples. Data collection and experimental iteration remain necessary even after code readiness is complete.

## One acceptance checklist: definition of done

The delivery is not training-ready until all the following pass. These are proposed acceptance requirements, not reported results.

| Test | Required evidence |
|---|---|
| Legacy migration | Fixtures for absent scale, missing host, reversed/split host, span crossing junction and starter outline; repeated migration gives same result; no records silently lost; previous snapshots restore |
| Reported 422 | Matching source/revision fixture can save, reopen and back up while unresolved; issue queue resolves or dismisses each anchor; verified export succeeds only after relevant validation |
| Geometry correctness | T/cross/corner junctions, collinear runs, diagonal walls, thin parallel walls, true doors/windows, intentional passages, text/furniture and partial crops; no unsupported bridge to reduce counts |
| Coordinate correctness | Round-trip transforms and mask/axis/box alignment on rotated, non-square and cropped multiscale inputs; within a documented subpixel numeric tolerance |
| Edit integrity | Move/split/merge/delete/undo/redo preserve shared-node connectivity, opening direction/span and mask lineage; conflicts are explicit |
| Shared views | 2D/3D/export all report and use the same revision; openings remain holes; calibrated dimensions agree; defaults remain labeled |
| Durable editing | Reload, close/reopen, offline reconnect, request retry, duplicate request, two tabs, API crash and disk-full tests; no acknowledged edits lost; no false Saved status |
| Real batch workflow | Import at least 35 valid plans plus corrupt files; valid cases complete or receive an explicit recoverable failure; restart mid-job and continue without duplicate cases or lost work |
| Label workflow | Annotate missed objects and polygon masks, review the whole source, adjudicate and export without terminal/JSON editing; no automatic claim of independent review |
| Dataset integrity | Reject incomplete labels, wrong image hashes, invalid polygons, duplicate images and building leakage; preserve immutable snapshots; new revisions do not alter old runs |
| Real training on Mac | Actual train/save/reload/infer/validation cycle on target hardware, with logs and checkpoint hashes; cancel/resume/retry tested; mocked training is insufficient |
| Backup/restore | Restore the complete collection and a checkpoint on a clean installation; compare hashes, counts, revisions, labels and split membership |
| Independent operator | Operator imports, reviews, resumes next day, exports, starts training and compares results with no developer intervention; record friction and fix blocking defects before sign-off |

Run existing backend tests, frontend production build and browser regression suite. Add real-API browser tests because mocked UI tests cannot prove persistence or migration. Maintain a results ledger with command, code commit, fixture hash, hardware, pass/fail and artifact links. No “all tests passed” without the recorded run.

## Accuracy gate and production boundary

Training readiness is not production accuracy. Retain the existing release gate: at least 10 independent held-out buildings; per-case wall-length precision/recall ≥90%; junction and adjacency F1 ≥95%; room-region F1 ≥90% at IoU 0.5; opening-span precision/recall ≥95%; manually verified complete exterior; at least 80% of cases corrected in five minutes. The current 3-source-pixel tolerance must be evaluated on a declared fixed raster normalization, and reported alongside scale-aware measurements rather than changed to improve scores.

Add missing evaluator fields before training runs are exposed: separate door/window metrics, matched opening host accuracy, room IoU, wall-thickness error, scale error/coverage, invalid-geometry rate, false automatic repair rate, inference latency and peak memory. Proposed initial release targets: ≥98% host accuracy among matched openings (report unmatched openings separately); scale relative error ≤2% for cases with reference scale; zero critical invented exterior/partition connections in the test corpus. Auto-scale abstentions must be counted and reported; low error on very few accepted cases is not success. Label these thresholds as product targets to validate, not achieved results.

For a public production service, also complete authentication and project authorization, upload/PDF limits, resource-limited workers, job timeouts, monitoring, retention/deletion and restore drills. These are part of production acceptance, not prerequisites for gathering local reviewed labels. AI room styling consumes the verified geometry as a constraint; a photorealistic render does not establish dimensional correctness.

## Implementation map and handoff

| Work area | Existing code to change | Deliverable |
|---|---|---|
| Canonical storage/migration | `plan_graph.py`, `models.py`, `graph_adapter.py`, `graph_operations.py`, `main.py` | Single revision API, migration/report, reconciliation and draft/verified export separation |
| Geometry and dimensions | `automatic_connections.py`, `graph_reconstruction.py`, `mask_topology.py`, `structural_graph.py`, `opening_review.py`, `scale_inference.py` | Evidence-scored repairs, opening topology, source transforms and calibration |
| Unified review | `app/blueprint/[id]/page.tsx`, `CanonicalWorkspace.tsx`, `SpatialReview.tsx`, `ReconstructionReview.tsx`, `Viewer3D.tsx`, history/API helpers | One canvas, issue queue, mask tools, shared revision and durable autosave |
| Collection and runs | Project UI, new Dataset/Training routes, API jobs and artifact storage | Batch import, persistent queue, operator run controls and compare view |
| Training/evaluation | `training_dataset.py`, `prepare_training.py`, `train_segmentation.py`, `evaluate_release.py`, benchmark modules | Versioned exports, real Mac preflight, resumable jobs and complete metrics |
| Acceptance | Existing API and Playwright tests plus real corpus fixtures | Evidence ledger, clean-machine restore and independent operator walkthrough |

Implement contract/persistence changes before wiring the unified UI; wire dataset export before the job runner; complete real end-to-end acceptance before handing over annotation work. These are dependencies within one delivery, not separate promises of future usability. Use reviewable commits and preserve compatibility through migration adapters. Remove obsolete normal-flow controls only after equivalent behavior passes regression checks.

The final handoff must include installed UI, tested code, the versioned labeling guide, one-page operator instructions, sample completed collection, training run evidence, restore instructions and an honest acceptance ledger. Once that checklist passes, routine user work is obtaining plans, correcting/reviewing labels, running experiments and selecting validated results—not diagnosing save paths or patching geometry code.

### Reference checked

Ultralytics instance segmentation label contract: https://docs.ultralytics.com/datasets/segment/ (checked 29 October 2026). Polygon annotations are required by the selected current trainer; they cannot be replaced with reviewed centerline JSON. Existing repository training commands and acceptance scripts were inspected directly; no newer model version is mandated by this plan.
