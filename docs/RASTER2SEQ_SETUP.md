# Raster2Seq in-app model comparison (experimental)

Official model: https://github.com/Cornell-VAILab/Raster2Seq

## Important licensing and environment constraints

- Raster2Seq **source** is MIT licensed; the officially released **pretrained weights** (including `hf:cubicasa5k`) are **CC BY-NC 4.0**. Do **not** enable them in Florp's commercial/SaaS production runtime without separate commercial permission.
- Upstream `predict.py` expects an NVIDIA/CUDA-compatible Linux environment. It creates CUDA timing events even when `--device cpu` is supplied, so a CPU-only or native macOS run is **not supported as-is**.
- This implementation creates no new project/layout version. It only draws the predicted room polygons on top of the existing blueprint. It does **not** infer metric dimensions, door/window geometry, verified walls, or 3D solids.
- Zero Raster2Seq model inference has been run on the user's blueprints by this integration until a properly configured isolated runtime executes it.

## Install isolated Raster2Seq environment (Linux + CUDA)

Do not install upstream dependencies into `apps/api`; the compiled PyTorch/Detectron2 dependencies can conflict with Florp.

Follow the **official upstream installation** exactly:

```bash
git clone https://github.com/Cornell-VAILab/Raster2Seq.git
cd Raster2Seq
conda create -n raster2seq python=3.10 -y
conda activate raster2seq
pip install torch==2.3.1 torchvision==0.18.1 torchaudio==2.3.1 --index-url https://download.pytorch.org/whl/cu118
pip install -r requirements.txt
(cd models/ops && sh make.sh)
(cd diff_ras && python setup.py build develop)
```

The first inference with `hf:cubicasa5k` resolves/downloads the published model from
https://huggingface.co/haopt/Raster2Seq ; permission to use the downloaded weights remains noncommercial. A CUDA GPU and enough GPU memory are required. The exact local command from upstream is `bash tools/predict_cc5k.sh`; the Florp adapter uses the same model flags, a single blueprint, `batch_size=1`, and `num_workers=0`.

Configure `apps/api/.env` **on the machine that runs FastAPI and hosts the isolated CUDA runtime**:

```dotenv
RASTER2SEQ_ENABLED=true
RASTER2SEQ_ROOT=/absolute/path/to/Raster2Seq
RASTER2SEQ_PYTHON=/absolute/path/to/miniconda3/envs/raster2seq/bin/python
RASTER2SEQ_DEVICE=cuda
RASTER2SEQ_CHECKPOINT=hf:cubicasa5k
RASTER2SEQ_TIMEOUT_SECONDS=600
```

A laptop-hosted FastAPI backend cannot invoke a CUDA interpreter installed on a *different* cloud machine with local file paths. For a cloud GPU, deploy the API worker alongside this model, or add an authenticated remote inference service; do not mount an arbitrary remote shell.

## Run a comparison

1. Upload a PNG/JPG/PDF plan in Florp. PDF uploads already use the stored raster preview.
2. Click **Compare Raster2Seq rooms (experimental)**.
3. Orange dashed polygons appear over the original plan.
4. Toggle **Show Raster2Seq room polygons**; compare them with the blue/purple YOLO + Yytsi structural evidence (run the separate **Compare YOLO + Yytsi** action).
5. The new inference writes **no** approved geometry, floor/room version, opening, or 3D component.

When the experimental runtime is disabled or missing, the API returns a descriptive `424 Failed Dependency`, shown next to the button. Check `GET /extraction/raster2seq/status` before testing.

## Underlying adapter contract

The official Raster2Seq inference saves
`output_dir/**/jsons/plan.json` as a list of entries with
`image_id`, `segmentation`, `category_id`, and `id`.
The adapter decodes nested or flat polygon coordinates; rejects malformed or
nonfinite values; and removes trailing duplicate corners.
It undoes upstream `ResizeAndPad`: scale=`min(256/w,256/h)`, integer truncated resized dimensions, and centered white padding.
Coordinates are mapped back to the original stored preview resolution and clipped to its bounds.

The endpoint includes original image SHA-256, exact dimensions, source layout version, checkpoint name, and `saved:false`. It does not convert room polygon boundaries directly into load-bearing wall solids. Results are hypotheses until independently reviewed.

## Tests and verification

```bash
cd apps/api
uv sync
uv run pytest -q tests/test_raster2seq_adapter.py
uv run pytest -q
```

`CI green` confirms integration syntax and deterministic behavior, not actual pretrained inference. To claim a meaningful model benchmark, run checkpoint inference on your real floor plans and compare room topology and wall completeness against manually verified ground truth. See [EXTRACTION_BENCHMARK.md](EXTRACTION_BENCHMARK.md) for the common JSON metric format.

**Production decision gate:** do not replace YOLO-first or ship the NC checkpoint as a commercial service until the measured accuracy, runtime cost, and licensing conditions have been resolved.
