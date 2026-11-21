# Florp

Turn a floor plan into an editable 2D drawing, walk through it in 3D, and try design ideas from a saved camera view.

Florp is a single-user app that runs on your computer. macOS is the target for local use, and CI runs on Linux. Import, editing, walkthroughs, furniture and floor finishes work without an API key. The installable phone app is planned. [Phone app plan](docs/PHONE_APP_PLAN.md)

## Run on your Mac

Install Node.js 22 and [uv](https://docs.astral.sh/uv/getting-started/installation/). The API uses Python 3.12, which uv can install when syncing. From the root of your Florp checkout, run:

```bash
(cd apps/api && uv sync --locked)
(cd apps/web && npm ci)
./scripts/start.sh
```

Wait for the build and startup to finish, then open [Florp at localhost:3000](http://localhost:3000). Keep the terminal open while using Florp. Press Ctrl+C to stop both servers. If Chrome reports **Connection refused**, run the launcher on the Mac where you’re using Chrome, check the terminal output, and make sure ports 3000 and 8000 are free.

To update, stop Florp, run `git pull --ff-only` from a clean local `main` checkout, then rerun the commands above. Optional settings belong in `apps/api/.env`. Keep your existing settings and use the [example configuration](.env.example) as a reference.

## Upload, walk and design

1. **Upload a plan.** Create a project and add a PNG, JPEG, WebP or PDF. Florp imports the first page of each PDF. Export additional pages as separate files. The default limit is 20 MB per upload and 45 megapixels after decoding.
2. **Review and calibrate.** Check the proposed walls, doors and windows against the drawing. Set one known distance and save the plan. Use **Architecture review** to record your checks for that saved revision. Review any detected furniture or bathroom fixtures individually before inserting them.
3. **Walk and furnish.** Open 3D, place and aim a camera, then focus the 3D view. Use WASD to move and the left/right arrows to turn. Confirmed open doors allow passage when there’s enough clearance. Add, move or remove furniture, try a **Floor finish**, and save the scene to keep your view and edits.
4. **Design from a view.** Use **Capture view** and **Export render inputs** to save the camera-aligned preview, depth and object mask locally. With an image provider configured, enter a **Design prompt**, approve generation and click **Generate preview**. Compare the result with the scene, since generated images can change visual details.

**Working with two floors?** Upload both drawings to the same project and choose **Identify floors, garden and stairs**. Confirm the order, correct any suggested outlines, and select **Save floor pair**. Open either floor in its own editor. Calibrate the drawing to see an estimated garden area. Moving between floors uses the editor links. A continuous 3D stair connection is planned.

## Image generation

[Set up local ComfyUI](docs/LOCAL_COMFY.md) to generate on your Mac without cloud credits. Install the SDXL checkpoint and depth ControlNet described in the guide, set `IMAGE_PROVIDER=local-comfy` in `apps/api/.env`, and keep ComfyUI running. **Render area** lets you target a visible object and preserves the surrounding pixels in the captured view.

Comfy Cloud and fal are optional paid providers. Set `IMAGE_PROVIDER=comfy` with `COMFY_API_KEY`, or `IMAGE_PROVIDER=fal` with `IMAGE_API_KEY`, then restart Florp. Keep keys in the API environment. For a cloud credit error, check the account linked to your key. For an unclear submission timeout, check the provider queue before retrying.

## Try a demo or back up your projects

With Florp running, create a synthetic project from a second terminal at the repository root:

```bash
(cd apps/api && uv run --locked python scripts/demo_project.py)
```

Open the URL it prints to try a calibrated two-room plan without uploading your own drawing or using an image provider.

Stop Florp before backing up or restoring. Run these commands from `apps/api`:

```bash
uv run --locked python -m app.local_backup create ~/Desktop/florp-backup.zip
uv run --locked python -m app.local_backup restore ~/Desktop/florp-backup.zip ~/florp-restored
```

Backups include the local database and project files. Keep `apps/api/.env` separately. Restore into a new directory, copy the printed `DATABASE_URL` and `STORAGE_PATH` into your existing settings, and restart Florp.

## Develop and test

Use `./scripts/dev.sh` for frontend hot reload. The local API docs are at [localhost:8000/docs](http://localhost:8000/docs). Keep the current app and API on localhost.

```bash
(cd apps/api && uv run --locked pytest -q)
(cd apps/web && npm run build)
(cd apps/web && npx playwright install chromium && npm run test:ui)
(cd apps/web && npm run test:integration)
```

The integration suite runs a real API and production frontend with temporary storage and provider keys disabled.

- [Architecture](docs/ARCHITECTURE.md) and [contributor handoff](docs/codex-handoff.md)
- [Optional fixture detection weights](docs/FIXTURE_WEIGHTS.md) and [engine validation](docs/ENGINE_VALIDATION.md)
- [Production roadmap](docs/PRODUCTION_POC_PLAN.md), [whole-home capability roadmap](docs/ENVIZ_CAPABILITY_ROADMAP.md), and [issue #1](https://github.com/BeBarefoot/Florp/issues/1)
- [Project history](HISTORY.md)
