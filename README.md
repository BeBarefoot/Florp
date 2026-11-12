# Florp — floor plan to editable space

Florp turns a floor plan into editable 2D geometry, a matching calibrated 3D scene,
and optional AI design images from saved camera views.

**Status:** functional local single-user POC. Not yet ready for a public hosted pilot.
The immediate release target is a single-user app on your own computer. Hosted
accounts and multi-user storage are a later release. The [production plan](docs/PRODUCTION_POC_PLAN.md) tracks release gates through
[issue #1](https://github.com/BeBarefoot/Florp/issues/1); the
[architecture audit](docs/ARCHITECTURE.md) describes the implementation.

## Run on your computer

The first local release targets **macOS**; automated CI runs on Linux.
Use Node.js 22 (`nvm use`) and Python 3.12, with [uv](https://docs.astral.sh/uv/).
Install the committed dependency versions once, from the repository root:

```bash
(cd apps/api && uv sync --locked)
(cd apps/web && npm ci)
```

Optional configuration goes in `apps/api/.env`; use `.env.example` as a reference.
Keep any existing `.env`. No API key is needed for local extraction, editing, 3D,
or capture/export. Then start both servers:

```bash
./scripts/start.sh
```

The launcher builds the production UI first; wait for startup to finish. For
development with hot reload, use `./scripts/dev.sh` instead.

Keep the terminal open and visit **http://localhost:3000**. API documentation is at
http://localhost:8000/docs. Ctrl+C stops the servers. This starts the app on the
computer where the command runs: a cloud workspace's localhost is not your computer.
After pulling a new release, reinstall locked dependencies and restart the servers.

To run the servers separately:

```bash
# Terminal 1
cd apps/api
uv run --locked uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

```bash
# Terminal 2
cd apps/web
npm run dev -- --hostname 127.0.0.1 --port 3000
```

If Chrome reports connection refused, check that both commands are still running
and resolve the error in their terminals. Ports 3000 and 8000 must be available.

## Try a synthetic demo

With the API running, use a second terminal:

```bash
cd apps/api
uv run --locked python scripts/demo_project.py
```

This creates PNG, JPEG and PDF versions of a generated two-room plan, runs local
extraction, and sets its known synthetic 6 m reference. It prints the project URL.
Review is left draft and no paid provider is called. You can place a camera, add or
remove objects, save, reload and export a capture without using your own plans.
Each run creates a separate demo project that you can delete from the home page.

## Use the app

1. Create a project and upload one floor plan. Supported inputs: single-frame PNG,
   JPEG, WebP, or the first page of an unlocked PDF. Export other PDF pages separately.
   The default upload limit is 20 MB; decoded images are limited to 45 megapixels
   before conversion/rasterization. New uploads preserve originals, preview hashes,
   EXIF orientation and PDF raster metadata in `source-manifest.json`.
2. Review the extracted walls and door/window proposals against the source. Edit,
   add or remove geometry, and confirm one known distance to calibrate measurements.
   Save the plan. Extraction is a proposal; calibration alone does not verify accuracy.
   Open **Architecture review** in the inspector, resolve its blockers, check the
   source/reference, and record your review with confirmed or assumed elevations.
   Any saved edit starts a new draft revision; **Reopen review** retracts acceptance.
   Plan bundles, GLB files and render inputs record the relevant review status.
   Review is your confirmation, not independent architectural certification.
3. Open 3D, place and aim cameras, and add/edit/remove furniture. The object list
   supports obscured objects and undo. Save the scene to preserve views and objects.
4. Enter a **Design prompt**, capture the view, and export inputs locally or select
   provider consent and **Generate preview**. Generation captures automatically if
   necessary. Compare the result with the measured scene; AI images can alter structure.

Fixture discovery is optional and each suggestion requires individual acceptance.
The default local symbol matcher requires no downloaded weights. See
[optional weights and license constraints](docs/FIXTURE_WEIGHTS.md) before evaluating
trusted YOLO checkpoints. The plan graph remains the source of truth.

## Image generation and credits

Configure one provider on the **API server**, then restart it:

```dotenv
IMAGE_PROVIDER=comfy
COMFY_API_KEY=your-key
```

Alternatively set `IMAGE_PROVIDER=fal` and `IMAGE_API_KEY`. `auto` prefers Comfy when
its key exists. Keys stay server-side; never commit them or put them in a public
frontend environment variable. Exported terminal variables override `.env` values.
Use the key alone, without a `Bearer ` prefix.

Comfy Cloud requires account access and sufficient credits. **Out of credits** is
resolved in the provider account associated with your key; code cannot supply credits.
After resolving the issue, explicitly generate a new preview. A saved failed job does
not retry automatically. The running API checks saved provider receipts without
an open browser and resumes polling after restart. Temporary provider outages keep
receipts pending; a lost submission response is never automatically resubmitted.
For an ambiguous timeout, check the provider dashboard before
submitting again. No fallback to a different paid provider occurs automatically.

For local ComfyUI, [export a depth workflow bundle](docs/codex-handoff.md#local-depth-workflow-and-photo-normalization).
This path needs a separate ComfyUI installation and suitable weights; it is not an
in-app local inference service. Live cloud compatibility and visual quality still need
an authorized, capped-cost evaluation.

## Back up and restore your local work

Stop Florp with Ctrl+C first. From `apps/api`, create a backup outside the data folder:

```bash
uv run --locked python -m app.local_backup create ~/Desktop/florp-backup.zip
```

This copies the SQLite database and storage: projects, plan/scene revisions, original
plans, previews, captures, generated images and annotation data. A workspace lock
rejects backups while the API is running. The normal API `.env` and provider keys
are outside this backup; keep your configuration separately. Archives are limited
to 10 GiB / 50,000 files and contain your private project data.

Restore into a **new** directory, leaving the current workspace intact:

```bash
uv run --locked python -m app.local_backup restore ~/Desktop/florp-backup.zip ~/florp-restored
```

The command verifies checksums and database integrity, rebases file references, and
prints the `DATABASE_URL` and `STORAGE_PATH` values to put in `apps/api/.env`. Keep
your provider settings. Restart, open the restored projects and check their scenes
before choosing whether to remove old data. Existing backups/directories are never
overwritten. Missing source files fail visibly instead of creating a partial backup.

## Validate changes

```bash
(cd apps/api && uv run --locked pytest -q)
(cd apps/web && npm run build)
(cd apps/web && npx playwright install chromium && npm run test:ui)
(cd apps/web && npm run test:integration)
```

The integration test starts a real API and production frontend in a browser in a temporary workspace on
ports 8008/3108, disables provider keys, and checks the synthetic import → extraction
→ calibration → scene/camera → capture → reload journey. It does not touch your
configured database. The standard UI suite separately mocks provider jobs/errors.

CI uses Python 3.12, Node 22, uv 0.13.5 and committed lockfiles. Update lockfiles
explicitly when changing dependencies. Tests use synthetic/approved fixtures and
mock paid providers. See [engine validation](docs/ENGINE_VALIDATION.md) for measured
regressions and their limits.

## Architecture and next gates

- [Current architecture](docs/ARCHITECTURE.md): revisioned PlanModel, scenes, captures and providers.
- [Production POC plan](docs/PRODUCTION_POC_PLAN.md): ordered implementation and release evidence.
- [Contributor handoff](docs/codex-handoff.md): detailed workflows and configuration.
- [Deterministic color-plan service](services/deterministic-blueprint/README.md): separate CPU service.
- [Historical milestones](HISTORY.md): earlier experiments, not current setup instructions.

The dependency hardening step upgrades Next.js to 15.5.29, pins its PostCSS
resolution to 8.5.32 and upgrades Pillow to 13.0.0. React 19, Fiber 9 and Drei 10
keep the 3D renderer compatible with the App Router runtime. Production npm audit and the
installed base Python environment audit reported zero known vulnerabilities on
11 November 2026. Audits do not establish complete application security.

For the macOS local release, remaining acceptance evidence is an actual Mac
install/run/backup check, representative real-plan accuracy, and authorized live
image drift/cost evaluation after provider credits are available. The tested local
features are ready for that evaluation; this is not a claim of final production
quality. Hosted authentication/storage and the mobile/PWA journey remain later
roadmap work toward issue #1. Keep this unauthenticated development server on trusted localhost until
the hosting gates pass. Default extraction is local; external image generation sends
derived depth and the prompt only after consent. Optional legacy vision extraction
sends the source image when explicitly invoked.
