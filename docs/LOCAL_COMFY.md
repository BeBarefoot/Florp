# Local generation on an Apple Silicon Mac

For the user's M5 / 48 GB Mac, start with SDXL base plus an SDXL depth ControlNet,
1024×768, one image and 20 steps. This is a practical starting configuration, not
measured M5 latency or quality. Model files require several GB of disk space.
No API subscription, cloud key or per-image provider fee is required. Model
licenses still apply; open weights do not mean unrestricted commercial rights.

## Install on your Mac

1. Install a current Apple Silicon build of [ComfyUI](https://www.comfy.org/download).
   Choose its models directory and configure its local server to listen on
   `127.0.0.1:8188`. Florp's own API uses port 8000; avoid using that port for ComfyUI.
2. Download [SDXL base 1.0](https://huggingface.co/stabilityai/stable-diffusion-xl-base-1.0)
   from the model publisher, review its license and place `sd_xl_base_1.0.safetensors`
   in ComfyUI's `models/checkpoints` directory.
3. Install the SDXL-compatible `diffusers_xl_depth_full.safetensors` depth model
   from [the ControlNet collection](https://huggingface.co/lllyasviel/sd_control_collection)
   in `models/controlnet`. Check its model/source license. An SD 1.5 ControlNet is
   not interchangeable with an SDXL ControlNet. Restart or refresh ComfyUI so both
   models appear in its loaders.
4. Set these values in Florp's `apps/api/.env`:

   ```dotenv
   IMAGE_PROVIDER=local-comfy
   LOCAL_COMFY_URL=http://127.0.0.1:8188
   LOCAL_COMFY_CHECKPOINT=sd_xl_base_1.0.safetensors
   LOCAL_COMFY_CONTROLNET=diffusers_xl_depth_full.safetensors
   ```

   Filenames must match the loader choices, including any model subfolders.
   Existing cloud keys can remain configured; explicit `local-comfy` selects local
   generation. Exported shell variables override `.env`. Restart Florp after changes.
5. Keep ComfyUI running, start Florp with `./scripts/start.sh`, open a calibrated
   plan, place/aim a camera, enter a design prompt, select the local-generation
   checkbox and click **Generate preview**. Review the result beside the capture.

Only core ComfyUI nodes are used. No custom node pack or depth-estimation model
is needed: Florp supplies depth from the exact saved camera. The workflow uses
SDXL text encoding, depth ControlNet, Euler sampling and the checkpoint's VAE.
The same frame dimensions are required on output; local downloads are bounded.

## Behavior and troubleshooting

- Florp checks `/object_info` for the configured models before uploading depth or
  submitting `/prompt`. A configured provider in settings does not establish that
  ComfyUI is running, models are installed or GPU execution works.
- Submissions upload only depth and prompt to the loopback server, without cloud
  credentials. They never fall back to a paid provider. Results use `/history`
  and `/view`; saved receipt polling resumes while both applications are running.
- Do not restart/clear ComfyUI history during a queued job. Its history is not a
  durable provider receipt store. Lost submission responses are not automatically
  resubmitted, because standard ComfyUI has no cloud-style idempotency guarantee.
- Missing models: check exact filenames and loader lists. Memory/device errors:
  inspect ComfyUI's terminal and use its supported Apple Silicon settings. No
  checkpoint download or GPU tuning is performed automatically by Florp.
- Keep other heavy GPU apps closed for initial tests. First model loading can be
  slower. Florp allows up to an hour for local queued/running jobs; check ComfyUI's
  queue before explicitly retrying a timed-out job.

The API protocol, errors, provider routing and UI are tested with mocks. This
cloud workspace does not have the user's M5 GPU. Real Mac installation, speed and
image drift must be measured there. Depth conditioning guides architecture but
cannot guarantee that generated walls/openings match the measured scene.
