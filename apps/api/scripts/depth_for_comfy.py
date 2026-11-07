"""Convert Florp's exported packed depth into a grayscale control image."""
import argparse
import base64
import io
import json
from pathlib import Path

import numpy as np
from PIL import Image


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture", type=Path, help="florp-render-inputs.json or an exported depth.png")
    parser.add_argument("output", type=Path, help="output grayscale PNG")
    args = parser.parse_args()

    if args.capture.suffix.lower() == ".json":
        depth = json.loads(args.capture.read_text(encoding="utf-8"))["depth"]
        if not depth.startswith("data:image/png;base64,"):
            parser.error("expected Florp's exported depth PNG data URL")
        source = io.BytesIO(base64.b64decode(depth.split(",", 1)[1], validate=True))
    else:
        source = args.capture
    with Image.open(source, formats=["PNG"]) as image:
        rgb = np.asarray(image.convert("RGB"), dtype=np.uint32)
    mm = rgb @ np.array([65536, 256, 1], dtype=np.uint32)
    hit = mm > 0
    if not hit.any() or mm.max() > 80000:
        parser.error("no valid packed Florp depth data")
    near, far = int(mm[hit].min()), int(mm[hit].max())
    result = np.zeros(mm.shape, np.uint8)
    result[hit] = np.rint(255 * (far - mm[hit]) / max(1, far - near)).astype(np.uint8)
    Image.fromarray(result).save(args.output, format="PNG")


if __name__ == "__main__":
    main()
