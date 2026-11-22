# Florp

Turn a floor plan into an editable 2D drawing, walk through it in 3D, and try design ideas from a saved camera view.

Florp is a single-user app that runs on your computer. macOS is the target for local use, and CI runs on Linux. Import, editing, walkthroughs, furniture and floor finishes work without an API key. The installable phone app uses the same projects and local API. [Phone app plan](docs/PHONE_APP_PLAN.md)

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

From the web plan editor, select **Phone walkthrough** to save pending plan edits and open the tour directly. In **Overview**, tap an open floor spot to land there, or select **Add view** and tap the floor once to land and save that spot as a tour stop. In the walkthrough, use the on-screen arrows or WASD to move forward, backward and sideways. Drag to turn and walk. Hold Shift or an on-screen arrow while dragging to look up or down. Pinch or scroll to zoom. Open doors connect walkable rooms. Use **Save this view** to save your current position, heading and zoom. Sample and approximate-scale tours keep new stops for the current session only. If an older saved scene belongs to a previous plan revision, update it in the editor before saving new stops permanently.

For an AI still of your current walkthrough view, stop moving and select **Download view image** and **Download view prompt**. Upload the PNG and text together to your image generator. The prompt describes the camera pose, framing, room boundaries, wall and opening dimensions, stairs and placed objects in model coordinates. Calibrate the plan against a known measurement for real-world dimensions. A tour marked **Approximate scale** uses estimated distances.


[Preview the phone walkthrough library](docs/images/phone-library.png). The cover uses an illustrative interior photograph. [Photo source](https://images.unsplash.com/photo-1600210492486-724fe5c67fb0)

Florp’s smartphone app is a progressive web app (PWA) served by the same
production launcher as the desktop editor. From the repository root, after the
dependency installation above, run:

```bash
./scripts/start.sh
```

- **On the computer:** open `http://localhost:3000` in Chrome. Use the install
  icon in the address bar or **Install page as app** in the browser menu. Launch
  Florp from the installed shortcut to open your projects in a standalone window.
- **Android over USB:** enable USB debugging, connect the phone, accept its
  debugging prompt and run the following on the computer with Android Platform
  Tools installed. Open `http://localhost:3000` in Android Chrome and choose
  **Install app** or **Add to Home screen** from the menu.

  ```bash
  adb reverse tcp:3000 tcp:3000
  adb reverse tcp:8000 tcp:8000
  ```

- **iPhone simulator on Mac:** start an iPhone in Xcode Simulator, open
  `http://localhost:3000` in Safari, and choose **Share → Add to Home Screen**.
  For installation on a physical iPhone, use a trusted HTTPS origin for Florp
  with an HTTPS-accessible API. See the private Wi-Fi installation steps below. Service workers require HTTPS or localhost.

Open `/phone` to see **Your walkthroughs**. Select **New space**, enter a name, then choose **Upload plans** or **Take photo**. Tap a drawing to open its walkthrough.
Drag vertically to walk, horizontally to turn, and pinch to zoom. Use **Overview**
to orbit the floor. **Edit floor** opens the studio for calibration, saved cameras,
floor finishes and design renders. The app saves projects on the computer running Florp.
Offline launches show a reconnect screen. Editing, uploads and generation
require connectivity. The app does not queue offline render requests.

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
4. Open `https://192.168.1.23:8443` in Safari and use **Share → Add to Home
   Screen**. Enable **Open as Web App** if offered. Keep both Mac terminals open.

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

### Present a floor on a phone

Open **Explore sample tour** in the phone library to try a furnished two-room apartment.
Open any floor from the phone library to go straight into its 3D view. Newly
uploaded drawings are extracted when opened. Floors without a measured reference
show **Approximate scale**, and the viewer picks a clear starting point when
there is no saved camera. Use **Edit floor** for optional corrections, calibration
or named camera stops.
Drag up or down to walk, sideways to turn, and pinch or scroll to zoom. Choose **Overview** to orbit the model and tap a numbered
camera marker. **Play tour** advances through the saved views. **Share this tour**
creates a link to the current stop on your Florp host. Recipients need the same host
access as the presenter. When no clear interior starting point is available, the viewer opens in overview.
Use **Hide tour controls** for an uninterrupted view. When a completed design
render matches the camera and the saved scene and plan revisions, **Show saved
design** displays that image. **Return to 3D** restores the interactive view.

### Realistic 3D walkthroughs

**Use Three.js (the existing phone renderer) for the tour and Blender for asset preparation and lighting.** Start with the calibrated Florp GLB as the architectural reference. Keep the plan graph in Florp as the source for room boundaries, doors, windows and navigation.

1. Set the floor finish in Florp. For production materials, use physically based textures for timber, tile and paint, with colour, roughness and normal maps tiled at their real-world size. [Poly Haven textures](https://polyhaven.com/textures) · [ambientCG](https://ambientcg.com/)
2. Prepare properly licensed furniture and bathroom fixtures in Blender. Use a bed, wardrobe, toilet and vanity as the first set. Set metre units and a floor-level origin, simplify geometry, and export each asset as glTF/GLB. In Florp, a future rendering change is to use these meshes for the existing object types, matching their saved footprint, rotation and height.
3. Validate one room on a real phone. Bake static lighting in Blender, use environment lighting for reflections and compress textures with KTX2 and meshes with Meshopt before expanding the asset library. Load the scene and verify movement through its doors at eye level. [Blender glTF exporter](https://docs.blender.org/manual/en/latest/addons/import_export/scene_gltf2.html) · [glTF Transform](https://gltf-transform.dev/)

The live tour now uses locally bundled scanned floor textures with colour, surface normal and roughness maps. Original uses smooth concrete, warm oak uses parquet, dark slate uses slate, and pale limestone uses a warm-tinted mineral finish. Beds have rounded bedding and a duvet, toilets have a curved ceramic bowl, and shower screens use translucent glass. AI-generated stills can be attached to individual stops. A consistent view while walking comes from the textured 3D scene.

[Room presentation](docs/images/phone-showcase.png) · [Dollhouse with camera stops](docs/images/phone-dollhouse.png)

Floor texture sources are distributed under CC0 by Poly Haven. [Rectangular parquet](https://polyhaven.com/a/rectangular_parquet) · [Slate floor](https://polyhaven.com/a/slate_floor) · [Smooth concrete floor](https://polyhaven.com/a/smooth_concrete_floor) · [License](https://polyhaven.com/license)
