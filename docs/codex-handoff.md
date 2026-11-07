# Florp Codex handoff

GitHub: [BeBarefoot/Florp](https://github.com/BeBarefoot/Florp). Use this repository in a Codex Cloud environment; the repository and this note carry the implementation context. Local plans, API credentials, and the local database do not travel with a Git checkout.

## Setup

- API: in `apps/api`, run `uv sync`, then `uv run uvicorn app.main:app --reload --port 8000`.
- Web: in `apps/web`, run `npm ci`, then `npm run dev`.
- Check: `uv run pytest -q` in `apps/api`; `npm run build` and `npm run test:ui` in `apps/web`. Use `npx playwright install --with-deps chromium` on a compatible Linux test runner. No image key is needed to develop or test fixture review.
- Baseline at the prior camera/render merge: six Python failures in floor-plan extraction and one Playwright failure in an existing corner-move window-position assertion.

## Current work

- Floor-plan geometry and its calibration live in immutable PlanModel revisions. Scene revisions hold cameras and optional objects. 3D capture and depth, local export, and the render job flow already exist.
- Find fixtures on plan uses local symbol matching on the original image with calibration, wall and stair masks and room context. Review the numbered outlines and Insert or Dismiss each object. Saving the scene preserves accepted objects and dismissals.
- Next useful experiments: measure per-class recall and false matches on varied drafting styles; compare fixture footprints and orientation against manually reviewed plans. Keep personal scans out of Git.

## Image rendering research

- The hosted adapter is fal's depth-conditioned FLUX endpoint. If using fal credits, make an API key in the [fal dashboard](https://fal.ai/dashboard/keys) and set `IMAGE_API_KEY` in the backend's local `.env`. Never commit the value. fal's [research grant](https://fal.ai/grants) is an application, not a guaranteed free tier.
- For zero provider fees, try [ComfyUI Depth ControlNet](https://docs.comfy.org/tutorials/controlnet/depth-controlnet) locally with compatible model weights. Florp's export contains packed RGB24 millimetres, not a model-ready grayscale image; from `apps/api`, run `uv run python scripts/depth_for_comfy.py /path/to/florp-render-inputs.json control.png`. Use `control.png` as the depth input in ComfyUI (skip its depth-estimation step). A local adapter is a follow-up, not a replacement key for fal.
- Useful next task: “Read AGENTS.md and docs/codex-handoff.md. Add a no-key local depth adapter or local workflow export. Preserve camera geometry and keep the existing hosted path optional. Mock paid calls in tests.”
