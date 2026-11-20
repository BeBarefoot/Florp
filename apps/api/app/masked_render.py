"""Crop local image edits in camera coordinates and preserve the other pixels."""
import io

import numpy as np
from PIL import Image


def encoded(image):
    out = io.BytesIO()
    image.save(out, format="PNG")
    return out.getvalue()


def selected_pixels(rgb, mask_id):
    color = [(mask_id >> 16) & 255, (mask_id >> 8) & 255, mask_id & 255]
    return np.all(rgb == color, axis=-1)


def prepare_edit(mask, preview, depth, mask_id):
    selected = selected_pixels(mask, mask_id)
    ys, xs = np.nonzero(selected)
    if xs.size < 24:
        raise ValueError("The selected object is too small or hidden in this view")
    height, width = mask.shape[:2]
    # Keep surrounding surfaces visible to the sampler. Use at least a small
    # square of context for narrow objects, including those at the frame edge.
    def span(indices, limit):
        length = min(limit, max(192, int(indices.max() - indices.min()) + 65))
        start = max(0, min(limit - length, (int(indices.max()) + int(indices.min()) - length) // 2))
        return start, start + length

    left, right = span(xs, width)
    top, bottom = span(ys, height)
    box = (left, top, right, bottom)
    factor = min(1, 768 / max(right - left, bottom - top))
    size = tuple(max(64, round(length * factor / 8) * 8) for length in (right - left, bottom - top))

    def crop(array, resample):
        return encoded(Image.fromarray(array).crop(box).resize(size, resample))

    return ({"box": box, "size": size, "maskId": mask_id},
            crop(depth, Image.Resampling.NEAREST), crop(preview, Image.Resampling.LANCZOS))


def composite_edit(folder, edit, generated):
    with Image.open(folder / "preview.png") as src:
        result = src.convert("RGB")
    with Image.open(folder / "mask.png") as ids:
        selection = selected_pixels(np.asarray(ids.convert("RGB")), edit["maskId"])
    box = tuple(edit["box"])
    mask = Image.fromarray(selection).crop(box)
    with Image.open(io.BytesIO(generated)) as partial:
        patch = partial.convert("RGB").resize(mask.size, Image.Resampling.LANCZOS)
    result.paste(patch, box, mask)
    return encoded(result)
