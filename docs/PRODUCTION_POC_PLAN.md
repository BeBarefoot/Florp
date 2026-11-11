# Production POC delivery plan

Updated 11 November 2026. Canonical execution plan for
[issue #1](https://github.com/BeBarefoot/Florp/issues/1). Read the
[implementation audit](ARCHITECTURE.md) for what exists today.

## Deliverable and boundary

Immediate target confirmed by the user on 11 November 2026: a reliable single-user
app on their own computer. Hosted authentication and multi-tenant storage (gate F)
are deferred from this release; keep all servers bound to localhost.

Deliver a responsive local web POC: upload a plan or mobile
photo → extract editable 2D → review uncertainty and confirm one measurement →
inspect matching 3D → place/save a camera → enter a design prompt → generate and
compare an image → revise style without changing the saved architecture/camera.

Initial scope is one floor per blueprint and first-page PDF rasterization. State
these limits in the upload UI. Multi-floor alignment, arbitrary multi-page PDF
selection, native mobile apps, BIM-grade measurements and fully automatic photo
rectification are subsequent work. Unsupported inputs must fail visibly without
losing saved edits. A generated image is a visualization, not construction evidence.

For the immediate release, “production POC” means a reliable local workflow with
repeatable results and recoverable local data. A later hosted pilot requires gate F.
The broader hosted contract is a safe limited external pilot with repeatable results,
recoverable data and known limits. It does not mean architectural certification
or unrestricted public release. Dates depend on measured gates, not estimates.

## Baseline

Implemented: upload/preview, default local extraction, shared-node PlanModel v2,
hosted opening review, calibrated editing, revision conflicts, derived 3D,
saved scenes/cameras, depth/mask capture, Comfy/fal integration, object editing,
optional local fixture weights and mock-tested prompt-to-image flow.

Unproven: representative full-plan accuracy, automatic scale reliability, fixture
recall/orientation, live provider compatibility/cost, output structural consistency,
touch usability and hosted operations. No model benchmark win is claimed.
PR #52 engineering baseline: 405 backend passes / 1 skip, 34 browser passes and
green GitHub build. Passing these does not close the product gates below.

## Issue #1 coverage

| Issue requirement | Existing capability | Remaining release evidence | Gate |
|---|---|---|---|
| Upload/image/PDF/mobile photo | Upload and preview | Touch camera input, orientation/quality checks, explicit unsupported cases | A, D |
| One-pass 2D + brief review | Local proposals and editor | Held-out accuracy, correction time, false/missing opening review | B |
| Verify topology/scale | Schema checks, reference calibration, findings | Persistent verification bound to revision; invalidate on edits | C |
| Same-model 3D | Shared wall pieces and rooms | Cross-language export/render parity and golden cases | C |
| Saved viewpoint | Revisioned scene/camera | Touch placement, reload/resizing and stale-plan review | C, D |
| Prompt/style → image | Consent, capture, provider jobs/results | Authorized live smoke test, cost/latency and drift evaluation | E |
| Iterate without moving structure/camera | Separate plan/scene/job inputs | Input hashes plus output comparison and QA enforcement | E |

## Ordered work packages and exit gates

Each work package should become a focused PR with an owner assigned before work
starts. Keep benchmark artifacts private where source plans are private. Link
results and decisions here; unchecked requirements remain open.

### A — Reproducible baseline and supported input contract

Owner role: platform engineer, reviewed by product/QA.

- [ ] Document the supported drafting styles, resolution, units and one-floor/one-page limits.
- [ ] Validate upload type/decoded size, EXIF orientation, PDF page identity and image
      dimensions. Preserve source hash and every resize/padding/rectification transform.
- [ ] Add a deterministic fixture command that builds synthetic demo projects without
      private drawings; make local startup and hosted pilot configuration reproducible.
- [ ] Pin runtime/dependencies, record optional model hashes/licenses and explain missing
      model/provider configuration in the app. CI must avoid dependency re-resolution drift.

Exit: fresh checkout can upload, extract, correct, save and reload synthetic PNG,
JPG and PDF fixtures; transformed coordinates round-trip within one source pixel;
invalid uploads preserve the latest revision. CI artifacts identify build/runtime versions.

### B — Gate 1: measured extraction and fixture review

Owner role: extraction engineer + independent architectural annotator.

- [ ] Assemble at least 30 consented full plans across clean/vector, scanned and
      photographed styles, including dimensions, furniture and negative site marks.
      Freeze project-disjoint splits: 10 development, 20 held out. Expand if any
      supported cohort has fewer than 5 test plans. Never tune on the held-out split.
- [ ] Independently review ground truth for wall centerlines/thickness, shared junctions,
      room faces, door/window hosts and spans, scale and fixture classes/orientation.
- [ ] Run the default extractor first, then optional YOLO/Yytsi and fixture checkpoints
      on identical inputs. Record hashes, model/config, hardware, latency and failures.
- [ ] Extend existing `extraction_benchmark.py` / `plan_score.py` reporting where needed:
      wall/opening precision and recall, host correctness, width/placement error,
      per-room/topology errors, metric error and median/P90 correction time.
- [ ] Implement only evidence-backed fixes to dominant errors. Keep uncertain fixtures
      optional; measure precision/recall per class rather than importing all boxes.

Proposed pilot thresholds (targets, not achieved results): wall precision and recall
≥.95, door/window precision and recall ≥.90, correct host ≥.95, room-count agreement
≥.90, confirmed scale error ≤2%, opening placement/width P90 error ≤10 cm, and ≥90%
of supported plans acceptable after ≤5 minutes correction. Report per cohort and
sample counts; do not hide unsupported failures in an aggregate. Product and the
architectural reviewer must agree these tolerances before freezing the test set.
A fixture model is optional until its per-class precision is ≥.90; missing fixtures
can be manually added. Unknown orientation must always remain reviewable.

Exit: versioned report, independent review sign-off and failure gallery. If thresholds
fail, narrow declared supported inputs or iterate on development data; do not rename
failed inputs “unsupported” after seeing held-out results. Training requires a measured
recognition gap, suitable licensed data and a separate test set.

### C — Verified architecture, metric scene and parity

Owner role: geometry/API engineer + frontend engineer.

- [ ] Persist acceptance per PlanRevision: topology checked, opening review complete,
      scale reference confirmed, elevations confirmed or explicitly assumed.
- [ ] Enforce the same verification rules in API/export/render paths. Allow draft preview
      with a clear status; do not label calibrated but unreviewed geometry “verified”.
- [ ] Any structural edit/re-extraction invalidates prior acceptance and flags dependent
      scenes. Never silently substitute the latest plan for a saved render's revision.
- [ ] Golden parity fixtures cover L/T/unequal joints, stairs, doors, windows, short walls,
      unknown scale, rotated views and export. Check floor/wall/opening dimensions in
      Python exports, client meshes and capture; shared reference math must agree.

Exit: no invalid host/crossing/critical unresolved topology can pass acceptance;
API bypass tests fail safely; canonical coordinates/metric sizes agree within 1 px /
1 mm numerical tolerance (separate from extraction error). Camera capture/reopen and
resize preserve pose/FOV/frame and known depth within the established encoding tolerance.

### D — Mobile-first guided journey

Owner role: product/frontend engineer + usability reviewer.

- [ ] Implement upload/photo → review → calibrate → 3D → camera → design as clear steps,
      with one primary action, saved progress, undo, visible errors and retry guidance.
- [ ] Keep training/model diagnostics in developer mode. Add touch pan/zoom and reliable
      feature selection, object list/add/remove/rotate/resize and camera aim controls.
- [ ] Add manifest/install behavior for the PWA; define offline scope explicitly. Never
      silently queue billable submissions offline. Camera/upload permissions need fallbacks.
- [ ] Test 360/390px phones, tablet and desktop, keyboard operation, labels, focus and
      44px touch targets. Verify an actual iOS Safari and Android Chrome session.

Exit: five new pilot users complete the supported journey without developer tools;
at least four finish unaided, no lost edits, no hidden generation prerequisites.
Record task time and confusion. Desktop browser automation alone cannot close this gate.

### E — Live image generation and iteration quality

Owner role: rendering/backend engineer + visual QA reviewer.

- [ ] In an explicitly authorized, capped-cost session, run a real Comfy or fal request
      using a synthetic calibrated scene. Confirm actual workflow/model access, submit,
      polling, image download, dimensions and useful failure messages. Record spend/latency.
- [ ] Evaluate at least 10 saved viewpoints with three style variants each. Compare camera,
      wall boundaries and openings against preview, mask and depth. Define an overlay-based
      review protocol and label each changed/missing/invented architectural feature.
- [ ] Store immutable input hashes and revision/model/seed metadata where available.
      Warn on output drift; do not present it as verified measured geometry.
- [ ] Measure cost, P50/P90 latency, failures and duplicate charges. Freeze numeric pilot
      cost/latency budgets before the live run. No automatic paid retry after ambiguity.

Exit: every result remains traceable to exact inputs; zero unflagged critical opening
or camera drift in the reviewed set; no duplicate submissions in timeout/retry tests.
If provider consistency is insufficient, add control/compositing/review or narrow scope.
Depth guidance alone is not a lock. Live evidence is required; mocks are insufficient.

### F — Hosted pilot readiness

Owner role: platform/security engineer + QA.

- [ ] Add login and project-level authorization, including every image/export/job route;
      test cross-user denial. Protect paid generation with quotas/rate limits and audit events.
- [ ] Use managed persistent DB/storage with migrations, retention/deletion and encrypted
      backups; prove full restore including captures and source identities.
- [ ] Move extraction/render execution to bounded durable workers. Test restart during
      submission, lost response, browser disconnect and duplicate polling. Reconcile provider
      receipts before retrying; expose recoverable status without requiring an open tab.
- [ ] Add staging, rollback, structured redacted logs, request/job IDs, latency/error/cost
      dashboards, alerts and a runbook. Keep credentials server-side.
- [ ] Run 10 concurrent pilot sessions with no lost revisions or duplicate paid jobs;
      verify upload limits, resource exhaustion controls and correct conflict responses.

Exit: restore and rollback drills succeed; all authorization/abuse tests pass; production
credentials/quotas are configured; operator approves limited pilot access. Localhost
and a cloud workspace test server are not deployment/access solutions.

## Sequencing and release decision

Start A and benchmark preparation B next. Implement C while collecting B evidence.
D can proceed on the stable PlanModel/Scene contracts. E needs C and provider setup;
F must precede any external hosted pilot. Do not block interface work on model training,
but do not claim trusted architecture until B/C pass. Issue #1 is complete only when
A–F artifacts and the full user journey are independently reviewed.

For each gate, retain: owner, commit/model/config, date, dataset split, command/device,
result artifact, failures, reviewer and decision. Current decision: **not production
ready**; B–F evidence is incomplete. No delivery date or passed gate is implied by this plan.

## Measurement and decision gaps to close before benchmarking

The targets above are not a complete scoring specification. Before freezing data,
write down wall matching distance/angle/overlap tolerances, whether scores are
length-weighted, one-to-one opening matching rules and metric conversions. Report
unmatched, duplicate and wrong-host detections separately. Room-count agreement
alone can conceal wrong boundaries: also report matched per-room IoU, false/missing
faces and junction connectivity. Agree an IoU release threshold with the architectural
reviewer before evaluating the holdout. Never silently infer metres on uncalibrated plans.

Record both uncorrected results and corrected results; start the correction timer
at the first visible result and include calibration/review time. Report timeouts
as failures. Report cohort results, total counts and uncertainty intervals; the
initial 20 held-out plans are a pilot sample, not proof of broad generalization.
A second engineer owns reproducibility and a separate reviewer owns ground truth.

No verified field evaluation or user study can be replaced by synthetic fixtures.
A gate failure must produce a written corrective decision and a fresh, untouched
holdout before making a new general accuracy claim. Distinguish validation edits
from changes to the production acceptance contract.

## Autonomous engine improvement phase

No user input is needed for the following bounded work, starting after this plan
is merged. Keep each behavior change backed by a failing regression and run CI.

1. Floorplan → 3D: add deterministic room/metric parity cases across Python derivation
   and TypeScript geometry, including unequal walls, T partitions and edits. Compare
   source polygons/areas and metric dimensions; reject nonfinite or invalid geometry.
2. Room adjustments: test label/type/ceiling behavior across move, split and merge,
   ensuring ambiguous inheritance requests review rather than silently reusing semantics.
3. Item discovery: test optional detector boxes against source bounds, explicit outline,
   stairs and supported classes; ensure uncertain detections never mutate architecture.
   Fix demonstrated contextual filtering gaps without claiming improved model recall.
4. Generation: test that auto-capture includes visibility facts from the actual captured
   frame, rather than a stale or absent capture; preserve consent and idempotency behavior.
5. Run focused regressions, full backend/browser suites and CI, document results and merge.

Inputs needed later for real-world model selection: consented representative plans
covering the intended drafting/photo styles, at least one independently known dimension
per plan, reviewed wall/opening/room and fixture truth (including absences), and intended
model-license/commercial-use constraints. Do not request uploads to perform the synthetic
phase. Before a paid live generation evaluation, obtain explicit authorization for the
provider and spending cap; no secret values should be sent in chat. Do not download or
activate arbitrary checkpoints merely to increase a test count.

Autonomous phase results and remaining empirical limits are recorded in
[Engine validation](ENGINE_VALIDATION.md). These regressions and fixes do not
close held-out benchmark, live generation or hosted-readiness gates.

## Production hardening execution log

Each step includes its README/plan update and is merged only after required CI
passes, before implementation of the next step.

1. Input reliability: pre-decode 45 MP bounds, explicit PNG/JPEG/WebP allowlist,
   first-page-only PDF validation, EXIF normalization and source/preview hashes
   with transformation metadata. Validation: 420 backend passes / one skip; TypeScript check passes. Seven
   focused regressions cover
   allocation guards and rejected uploads preserving existing blueprints.
   This completes the bounded upload portion of A; round-trip transform scoring,
   synthetic demo tooling and reproducible runtime work remain open. Historical
   uploads retain their existing files and have no backfilled provenance.
2. Next: make installation/CI reproducible and reconcile README with the current
   user journey, then harden generation recovery and review remaining gate work.

No hosted-readiness, real-world accuracy or live paid-render gate is closed by
these changes. Credits/account access and authorized live evaluation remain external
prerequisites; authentication/storage/worker architecture still requires implementation.

### Step 2 — Reproducible startup and current documentation

Step 1 merged as [PR #55](https://github.com/BeBarefoot/Florp/pull/55), all three
CI checks green (420 backend passes / one skip; upload browser regression included).
Step 2 pins CI to Python 3.12, Node 22 and uv 0.13.5, uses `uv sync --locked`
and `npm ci`, and supplies a localhost-only two-server launcher. README now documents
the actual supported journey, server configuration, credits and current limits; old
milestone notes are preserved in HISTORY.md. Existing `.env` values are never replaced.
Local launcher smoke test: API health and web HTTP 200; SIGTERM closes both ports.
Locked uv install and shell syntax checks pass. CI validates locked installs and all suites; this does not imply dependencies
have received a complete security audit or that optional research extras are supported.

Next step: resolve the npm audit critical Next.js and high PostCSS findings with
a tested framework dependency update. Then render idempotency/recovery and actionable
provider failures, with mocked
provider regressions. Preserve explicit consent; never retry a potentially billable
submission automatically. Hosted worker/authorization and live evidence gates stay open.

### Step 3 — Resolve dependency audit findings

Step 2 merged as [PR #56](https://github.com/BeBarefoot/Florp/pull/56), with all
three checks green, including 40 browser tests. The audit then found affected
Next.js, PostCSS and Pillow versions. Upgrade to Next.js 15.5.29 with React/React DOM 19.3.1, Fiber 9.8.2 and Drei 10.7.9
for App Router compatibility, override PostCSS to patched 8.5.32, and upgrade
Pillow to 13.0.0. Lockfiles record exact resolutions.

Validation: 420 backend passes / one skip; production build passes; `npm audit
--omit=dev` and pip-audit of the installed base Python environment report no known
vulnerabilities on 11 November 2026. Optional research extras are not covered.
The override is explicit because Next's declared PostCSS dependency remains old.
Recheck and remove it when the framework resolves a patched version itself.
The original Fiber 8 renderer failed the 3D browser regressions under the new
App Router runtime. Upgrade the renderer and React together, including React 19
types and compatible Lucide icons. Full browser validation and CI are required
before merging this framework change.

Next: render polling recovery, request identity and provider-account guidance.

### Step 4 — Local render recovery and account failures

Step 3 merged as [PR #57](https://github.com/BeBarefoot/Florp/pull/57) after all
three CI checks passed. Immediate scope is now explicitly local single-user use.

The API lifespan starts a receipt-reconciliation loop: up to 20 saved jobs per
batch, four concurrent status checks, 45-second per-check budget and five-second
interval between batches. A cursor prevents permanently queued jobs from starving
later jobs. Completed jobs leave the scan. Restart with a stored receipt checks
the provider result before declaring an old job timed out. Unknown submissions
never retry; the user must reconcile the provider dashboard. This is local receipt
recovery, not a durable provider-submission queue or multi-worker hosted scheduler.

Transient HTTP 429/5xx and network failures retain pending receipts. Conditional
DB status updates prevent stale browser/worker responses from downgrading completion.
New request identities use canonical validated JSON, preserving idempotency across
key ordering/whitespace. Manifests include input and individual capture hashes.
Comfy credit, authentication and access failures have separate actionable messages;
the app links to the account and keeps saved scene inputs available. No paid calls
were made. Focused backend recovery/provider tests pass, including API lifecycle cleanup.
Full backend run: 427 pass / one skip before the added lifecycle test; browser
credit-recovery regression passes. CI runs the complete final suite.

Next local steps: recoverable full-project backups, revision-bound architecture
acceptance, and a reproducible synthetic end-to-end demo. Held-out plan accuracy
and live provider QA still need real inputs/authorized credits; they are not
replaced by these regressions. Hosted login is not a prerequisite for local use.

### Step 5 — Full local workspace recovery (macOS target)

Step 4 merged as [PR #58](https://github.com/BeBarefoot/Florp/pull/58), all checks
green. User confirmed macOS as the target operating system. Local backups now
include the complete SQLite database and storage tree, not only training annotations.
An OS workspace lock shared by API startup and backup prevents concurrent writes.
The same lock rejects a second API instance using the same database.

Backup uses SQLite's snapshot API, normalizes known stored file references, records
per-file hashes and publishes a new archive exclusively. Restore checks inventory,
size/count limits, paths, hashes and DB integrity before creating a new destination;
references are rebased to its storage tree. Current data and existing archives are
never overwritten. Provider `.env` configuration outside storage is intentionally
separate. Limits: file-backed SQLite, macOS/Linux, 10 GiB / 50,000 files; hosted DB
backup is deferred. Pending annotation-restore journals must be reconciled first.

Validation: 434 backend tests pass / one skip. Automated restore tests cover saved projects, plan/scene revisions, generated assets,
path rebasing, workspace-lock exclusion, checksum tampering, traversal, missing
files and refusal to overwrite. Linux tests validate the POSIX implementation; an
actual macOS install/run/restore check remains release evidence to collect.

Next: revision-bound architecture acceptance and a synthetic local walkthrough.
