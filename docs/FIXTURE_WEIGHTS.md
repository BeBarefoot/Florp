# Local fixture weights

The default detector uses local synthetic symbol matching. Optional YOLO weights
can instead return reviewable object boxes with no external image service.

Candidate: https://huggingface.co/mudasir13cs/floorcad-yolov8n-detect
The publisher lists AGPL-3.0 and FloorPlanCAD-derived training. Its 35 labels
include bed, wardrobe, toilet, bath_tub and sink. The adapter maps sink to vanity;
other unsupported objects, architectural walls and openings are ignored. Boxes
estimate size using the saved calibration; front/back rotation must be reviewed.
These weights have not been benchmarked on this project's photographed plans.
Model, software and training-data rights must be evaluated for the intended use.

For trusted weights obtained from the publisher, install the optional runtime:

```sh
cd apps/api
uv sync --extra pretrained-yolo
```

Set `FIXTURE_YOLO_WEIGHTS=/absolute/path/to/trusted.pt` in the API environment,
restart, and click **Find fixtures on plan** in 3D. No checkpoint is downloaded
implicitly. Accept or dismiss each result; accepted objects can be moved,
resized, rotated or removed. Missing runtime/weights produce an explicit error.
Clear the setting to return to the default local matcher.

Alternative: https://github.com/CubiCasa/CubiCasa5k publishes icon-model weights,
but its repository LICENSE says CC BY-NC 4.0. It is not enabled by this change.
The existing Yytsi wall model does not detect fixtures.

# In-app image generation

Open 3D on a calibrated plan, place and aim a camera, and enter **Design prompt**.
Authorize the named provider's billable render, then **Generate preview**. It
captures the current view automatically, saves the scene, and displays the job
and resulting image. Capture and export remain available separately.
The API needs COMFY_API_KEY (Comfy Cloud) or IMAGE_API_KEY (fal), plus provider
model access and credit. No paid generation is performed by automated tests.
