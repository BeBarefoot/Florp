"""Convert Florp depth to grayscale or a no-key local ComfyUI input bundle."""
import argparse
import base64
import io
import json
from pathlib import Path

import numpy as np
from PIL import Image
from app.depth import control_depth


def decode_png(value):
    if not value.startswith("data:image/png;base64,"):
        raise ValueError("expected exported PNG data URL")
    return base64.b64decode(value.split(",", 1)[1], validate=True)


def convert(capture, output, bundle=False):
    metadata = None
    if capture.suffix.lower() == ".json":
        metadata = json.loads(capture.read_text(encoding="utf-8"))
        raw = decode_png(metadata["depth"])
    else:
        raw = capture.read_bytes()
    with Image.open(io.BytesIO(raw), formats=["PNG"]) as image:
        rgb = np.asarray(image.convert("RGB"))
    result, limits = control_depth(rgb)
    if not bundle:
        Image.fromarray(result).save(output, format="PNG")
        return
    if metadata is None:
        raise ValueError("bundle requires exported JSON with camera metadata")
    images = {name: decode_png(metadata[name]) for name in ("mask", "preview")}
    for data in images.values():
        with Image.open(io.BytesIO(data), formats=["PNG"]) as image:
            image.load()
            if image.size != (rgb.shape[1], rgb.shape[0]):
                raise ValueError("capture images must have matching dimensions")
    output.mkdir(parents=True, exist_ok=False)
    Image.fromarray(result).save(output / "control.png", format="PNG")
    (output / "depth.png").write_bytes(raw)
    for name, data in images.items():
        (output / f"{name}.png").write_bytes(data)
    manifest = {k: v for k, v in metadata.items() if k not in ("depth", "mask", "preview")}
    manifest.update(depthRangeMm=limits, controlEncoding="8-bit grayscale; near bright, far/background dark")
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    (output / "prompt.txt").write_text(metadata.get("prompt", ""), encoding="utf-8")
    (output / "README.txt").write_text(
        "Load control.png directly into a local ComfyUI Depth ControlNet workflow. Skip depth estimation.\n"
        "Use compatible base-model and depth-ControlNet weights; weights are not included.\n"
        "Keep captured dimensions and framing; preview.png is the camera reference.\n"
        "manifest.json preserves camera, plan revision, depth range and mask IDs.\n"
        "mask.png contains packed object IDs, not an inpainting mask. No provider is contacted.\n"
        "Generated images are suggestions; verify alignment against the reference.\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--bundle", action="store_true", help="write inputs and metadata to a new directory")
    args = parser.parse_args()
    try:
        convert(args.capture, args.output, args.bundle)
    except (ValueError, KeyError, OSError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
