# Florp Codex handoff

GitHub: [BeBarefoot/Florp](https://github.com/BeBarefoot/Florp). Use this repository in a Codex Cloud environment; the repository and this note carry the implementation context. Local plans, API credentials, and the local database do not travel with a Git checkout.

## Setup

- API: in `apps/api`, run `uv sync --locked`, then `uv run --locked uvicorn app.main:app --reload --port 8000`.
- Web: in `apps/web`, run `npm ci`, then `npm run dev`.
- Check: `uv run pytest -q` in `apps/api`; `npm run build` and `npm run test:ui` in `apps/web`. Use `npx playwright install --with-deps chromium` on a compatible Linux test runner. No image key is needed to develop or test fixture review.
- PR #51 repaired the prior six extraction failures and stale browser assertions. PR #52 validation: 405 backend passes, 1 skip; 34 browser passes; all three GitHub checks passed. These do not establish held-out accuracy.

## Delivery source of truth

Read [Architecture](ARCHITECTURE.md) and [Production POC plan](PRODUCTION_POC_PLAN.md)
for the audited implementation and gates through issue #1. Start with input-contract
work and frozen benchmark preparation. Do not restart graph/camera/render features
as if absent; verify and harden them. No held-out accuracy or live render QA is claimed.

## Current work

- Floor-plan geometry and its calibration live in immutable PlanModel revisions. Scene revisions hold cameras and optional objects. 3D capture and depth, local export, and the render job flow already exist.
- Find fixtures on plan uses local symbol matching on the original image with calibration, wall and stair masks and room context. Review the numbered outlines and Insert or Dismiss each object. Saving the scene preserves accepted objects and dismissals.
- Next useful experiments: measure per-class recall and false matches on varied drafting styles; compare fixture footprints and orientation against manually reviewed plans. Keep personal scans out of Git.

## Image rendering research

- Hosted adapters are Comfy Cloud v2 and fal's depth-conditioned FLUX endpoint. If using fal credits, make an API key in the [fal dashboard](https://fal.ai/dashboard/keys) and set `IMAGE_API_KEY` in the backend's local `.env`. Never commit the value. fal's [research grant](https://fal.ai/grants) is an application, not a guaranteed free tier.
- For zero provider fees, try [ComfyUI Depth ControlNet](https://docs.comfy.org/tutorials/controlnet/depth-controlnet) locally with compatible model weights. Florp's export contains packed RGB24 millimetres, not a model-ready grayscale image; from `apps/api`, run `uv run python scripts/depth_for_comfy.py /path/to/florp-render-inputs.json control.png`. Use `control.png` as the depth input in ComfyUI (skip its depth-estimation step). A local adapter is a follow-up, not a replacement key for fal.
- Useful next task: “Read AGENTS.md and docs/codex-handoff.md. Add a no-key local depth adapter or local workflow export. Preserve camera geometry and keep the existing hosted path optional. Mock paid calls in tests.”

## Local depth workflow and photo normalization

Export render inputs from the camera view, then from `apps/api` run:

```bash
uv run python scripts/depth_for_comfy.py /path/to/florp-render-inputs.json /path/to/new-bundle --bundle
```

The bundle includes grayscale `control.png`, original metric depth, preview,
object-ID mask, prompt and a manifest preserving camera and plan revision.
Load control directly into a compatible local ComfyUI Depth ControlNet workflow,
skipping depth estimation. Keep the captured dimensions and framing. Model
weights and a ComfyUI installation are separate prerequisites; this export does
not submit a job or contact a provider. Hosted rendering remains optional.

Fixture matching now normalizes slow paper illumination before stroke extraction.
Synthetic regression checks cover a shadowed, faint, blurred JPEG symbol and
blank shaded paper. This is not measured recall on real photographs, nor perspective
rectification: calibrate the source and review each suggestion individually.

## Generate a design from a camera view

In the 3D image section: place and aim a camera, enter a **Design prompt**, click
**Capture view**, check the provider consent box, then **Generate preview**.
The app saves the scene, submits the depth and prompt, polls the job and displays
the result beside the measured capture. Each variant retains its camera/plan
revision. Style text can name individual visible rooms and fixtures, for example
“warm brown bedroom, black bathroom tiles and a gold toilet”. A bathroom behind
a wall needs its own camera; prompts do not reveal hidden rooms or edit geometry.
Image models can still deviate from geometry; inspect the overlay.

Set a replacement `COMFY_API_KEY` securely on the API server and restart it.
`IMAGE_PROVIDER=auto` prefers Comfy Cloud when its key exists; `comfy` or `fal`
explicitly selects a provider. The optional fal path still uses `IMAGE_API_KEY`.
Comfy Cloud requires an active subscription and credits. Keys stay on the server.
No generation is submitted without the existing in-app consent checkbox.

The adapter uses [Comfy API v2](https://docs.comfy.org/api-reference/v2/overview)
and the core FLUX Depth LoRA graph from
[Comfy's official template](https://github.com/Comfy-Org/workflow_templates/blob/main/templates/flux_depth_lora_example.json),
with depth estimation and resizing omitted. The 1024×768 captured metric depth
is normalized locally and uploaded as an asset. No local GPU, model downloads
or separate ComfyUI installation is needed for this cloud path. Model filenames
are configurable via `COMFY_UNET`, `COMFY_DEPTH_LORA`, `COMFY_CLIP`, `COMFY_T5`,
and `COMFY_VAE`; defaults are in `.env.example` and require matching models on
Comfy Cloud. Rejected workflows give a configuration error. The integration is
tested with mocked uploads, jobs, downloads and in-app generation; live account
model availability and visual quality require a separately authorized live test.

Allow HTTPS to `cloud.comfy.org` and the signed image-storage destination returned
by its asset-content endpoint. Authentication is sent only to the Cloud API;
downloads from signed storage do not receive the API key. Submission is not retried
automatically after an uncertain response: check the Comfy dashboard first.

## Fixture weights and simpler scene editing

See `docs/FIXTURE_WEIGHTS.md` for the optional trusted local YOLO adapter and
published model/license research. FIXTURE_YOLO_WEIGHTS selects it; the default
remains local symbol matching. Predictions require individual review and manual
orientation checks. An object list provides selection/removal even for obscured
objects, with undo. The design prompt is visible before camera placement;
Generate preview now captures automatically after provider consent. No live
billable generation or checkpoint accuracy benchmark was performed for this work.

## Autonomous engine regression work

See [Engine validation](ENGINE_VALIDATION.md) for analytical Python/TypeScript room
and 3D metric fixtures, semantic split/merge coverage, contextual fixture filtering
and the auto-capture visibility-facts fix. Full backend baseline is now 413 passes,
1 skip. Real-world recognition accuracy remains unmeasured; follow the POC gates.
