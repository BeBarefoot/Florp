# Florp

Turn a floor plan into an editable 2D drawing, walk through it on a phone, and try design ideas before buying or renovating a home.

Florp currently runs as a local, single-user app on a Mac. The browser editor and installable phone app share the same projects. Uploads, extraction, manual edits, furniture, floor finishes and walkthroughs work without an API key. An image provider is optional.

## Run on your Mac

Install Node.js 22 and [uv](https://docs.astral.sh/uv/getting-started/installation/). The API uses Python 3.12, which uv can install when syncing. From the root of your Florp checkout, run:

```bash
(cd apps/api && uv sync --locked)
(cd apps/web && npm ci)
./scripts/start.sh
```

Wait for the build and startup to finish, then open [Florp at localhost:3000](http://localhost:3000). Keep the terminal open while using Florp. Press Ctrl+C to stop both servers. If Chrome reports **Connection refused**, run the launcher on the Mac where you’re using Chrome, check the terminal output, and make sure ports 3000 and 8000 are free.

To update, stop Florp, run `git pull --ff-only` from a clean local `main` checkout, then rerun the commands above. Optional settings belong in `apps/api/.env`. Keep your existing settings and use the [example configuration](.env.example) as a reference.

## Run and install the smartphone app

Start Florp on your Mac using the steps above. Open **Your walkthroughs** at `/phone`. Try **Explore sample tour**, or select **New space** and use **Upload plans** or **Take photo**. Tap a floor to extract and open it. From the web plan editor, **Phone walkthrough** saves pending plan edits and opens the same tour.

- **On your Mac:** open `http://localhost:3000/phone` in Chrome. Use the browser's install option to open Florp in its own window.
- **Android over USB:** use the [physical Android debugging guide](docs/ANDROID_DEBUG.md) to run Florp in Chrome and inspect it from your computer.
- **iPhone Simulator:** open `http://localhost:3000/phone` in the simulator's Safari. For a physical iPhone, use the HTTPS setup below.

Uploads and edits are stored on the Mac. Keep Florp running and connected while using the phone app. A shared tour link needs access to the same Florp host.

#### Install on a physical iPhone over private Wi-Fi

On your Mac, install Caddy and mkcert (`brew install caddy mkcert`). Replace
`192.168.1.23` below with the Mac’s Wi-Fi IP. Keep the Mac and iPhone on a
private network. The HTTPS gateway below requires an owner password for the app and API.

1. Stop the existing launcher and, from the Florp root, run
   `NEXT_PUBLIC_API_URL=/florp-api ./scripts/start.sh`. Keep it running.
2. Use `caddy hash-password` to generate a password hash and replace
   `REPLACE_WITH_CADDY_PASSWORD_HASH` below. Sign in as `owner` on the phone.
   In another terminal, create a certificate and start a single HTTPS endpoint
   for the app and API:

   ```bash
   mkdir -p ~/florp-local-tls && cd ~/florp-local-tls
   mkcert -install
   mkcert -cert-file florp.pem -key-file florp-key.pem 192.168.1.23
   cat > Caddyfile <<'EOF'
   {
       auto_https disable_redirects
   }
   https://192.168.1.23:8443 {
       tls florp.pem florp-key.pem
       basic_auth {
           owner REPLACE_WITH_CADDY_PASSWORD_HASH
       }
       handle_path /florp-api/* {
           reverse_proxy 127.0.0.1:8000
       }
       handle {
           reverse_proxy 127.0.0.1:3000
       }
   }
   EOF
   caddy run --config Caddyfile --adapter caddyfile
   ```

3. Run `mkcert -CAROOT` to locate the CA folder. Transfer **only**
   `rootCA.pem` to the iPhone. Install the downloaded profile in Settings,
   then enable its trust under **General → About → Certificate Trust Settings**.
4. Open `https://192.168.1.23:8443/phone` in Safari and use **Share → Add to Home
   Screen**. Enable **Open as Web App** if offered. Keep both Mac terminals open.

## Upload, correct and walk

1. **Upload.** Use PNG, JPEG, WebP or PDF. Florp imports the first page of each PDF, so export additional pages as separate files. The default limits are 20 MiB per upload and 45 megapixels after decoding.
2. **Check and correct.** Open **Edit floor** from the tour. Tap an existing wall, door or window to remove it, or choose a tool and tap both ends to add one. Use **Undo** to reverse an edit and **Done** to save and return to the tour. Select a window to set its measured width, height, sill, frame material, colour and pane count. Open **Full editor** for plan calibration and architecture review. The phone tour labels an uncalibrated draft **Approximate scale**. Review fixture suggestions individually before adding them.
3. **Recover a missing floor.** If no closed rooms were found, choose **Mark a walkable floor in the editor** from the tour. Select two opposite corners of a clear area on the source drawing. Place and aim a camera, then choose **Save scene** to save the floor area and view. For a three-sided room, open **Align walls** to search the original drawing for a faint fourth wall. Under **Suggested wall closures**, select a finding to see the proposed span. Choose **Add closing wall** or dismiss it. To draw a diagonal wall or door, tap its two ends. A hosted door stretches along its wall when you drag an end handle.
4. **Walk and save a view.** The phone tour opens at a clear room corner at full zoom-out when space allows. Drag to walk and turn, or move with two fingers, twist to turn, and pinch to zoom. On desktop, use WASD to move, swipe sideways on the trackpad to turn, or hold Shift while scrolling or dragging to look up or down. Choose **Corner view** to reset the framing in your current room. In **Overview**, swipe on a desktop trackpad to orbit or pinch to zoom. Tap the floor to land there, or choose **Add view** and tap a room to save a wide corner view. **Save this view** saves the current camera on a calibrated plan. Sample and approximate-scale tours keep new stops for the session. If the plan changed since the scene was saved, review and save the scene against the latest plan before saving permanent stops.
5. **Furnish and design.** In the phone tour, open **Finishes** to preview a floor material for the whole floor or an individual room. Choose a palette, set a colour and enter plank or tile dimensions. Saving a whole-floor finish keeps room overrides. In the full editor, place furniture and save the scene. **Capture view** and **Export render inputs** provide a camera-aligned preview, depth map and object mask. **Download view image** and **Download view prompt** export the phone view for an external image generator.

On a fresh extraction, Florp checks for soft edges and sharpens a working copy when needed. It looks for drawn car and bed symbols before calibration. In a closed room, a car suggests **Garage** and a bed suggests **Bedroom**. Outside a detected room, the symbol keeps its own label. Look for the tags in the plan editor or the phone tour’s **Overview**. Select a tagged room in the editor to change its name or type. Faint or unfamiliar symbols can go unrecognized.

**Detect yard** in the full editor refreshes the outdoor areas on an existing plan. Florp looks for shaded lawn and can trace adjacent warm-colored paving as a separate patio. Both surfaces appear in 2D, in the tour, and in GLB exports.

For plans with printed centimetre dimensions, optional local Tesseract can suggest scale (install it on macOS with `brew install tesseract`). When at least three dimension lines agree across both axes, **Review detected scale** highlights a reference and a second check on the original drawing. Confirm both spans to apply them, or measure a known distance manually.

For two levels, upload both files to the same project and choose **Identify floors, garden and stairs**. Confirm the suggested order and outlines, then **Save floor pair**. Each floor has its own calibrated editor and walkthrough. Select a stair to set **Up**, **Down**, or **Both** and check its rise. Stairs are rendered relative to the current floor. Open the other floor to tour it.

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

From `apps/api`, run `uv run --locked python -m app.extraction_coverage` to count and score corrected real-plan regressions under the gitignored `data/gold` directory. Use `--gold-root` for a separate private collection and `--output` for a private JSON report with per-case metrics and errors. CI publishes aggregate counts even when no reference plans are available. A separate frozen, independently reviewed release corpus can be supplied with `--release-manifest`. Corrected regression sources are excluded from that evaluation.

- [Architecture](docs/ARCHITECTURE.md) and [contributor handoff](docs/codex-handoff.md)
- [Optional fixture detection weights](docs/FIXTURE_WEIGHTS.md) and [engine validation](docs/ENGINE_VALIDATION.md)
- [Production roadmap](docs/PRODUCTION_POC_PLAN.md), [whole-home capability roadmap](docs/ENVIZ_CAPABILITY_ROADMAP.md), and [issue #1](https://github.com/BeBarefoot/Florp/issues/1)
- [Project history](HISTORY.md)

## Product roadmap

Florp is a self-serve app for homebuyers and homeowners. The first priority is the most accurate automatic extraction the source supports. When a draft needs help, the buyer should be able to repair it on the phone or ask the planned Pro chat assistant to propose a specific correction for approval.

The next milestone is to benchmark first-pass extraction on real plans and measure how often buyers can go from upload to a usable walkthrough without help. Use a five-minute correction budget for supported plans. Validate the phone repair flow before expanding to whole-home navigation and richer visual assets. [Accuracy and mobile roadmap](docs/ROADMAP_ACCURACY_MOBILE.md) · [Whole-home roadmap](docs/ENVIZ_CAPABILITY_ROADMAP.md)

The roadmap includes a Pro tier with AI chat, Unreal Engine graphics, advanced
modules, and support. Designer will ask what can move, compare measured layout
options, and export the approved design as an editable Florp variant. Feature access, scene compatibility, and job handling are
part of the initial infrastructure. A separate milestone lets buyers enter an
address and place the calibrated model on Google Maps.
[Product tiers and site placement](docs/ROADMAP_ACCURACY_MOBILE.md#product-tiers-and-site-placement)
