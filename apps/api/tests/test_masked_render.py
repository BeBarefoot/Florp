import io

import numpy as np
from PIL import Image

from app.masked_render import composite_edit, encoded, prepare_edit
from app.local_comfy import workflow


def test_edge_object_crop_preserves_surroundings_and_occlusion(tmp_path):
    mask = np.zeros((768, 1024, 3), dtype=np.uint8)
    mask[200:500, :60] = (0, 3, 232)
    mask[300:320, 12:40] = (0, 0, 1)
    preview = np.full_like(mask, 47)
    edit, depth, source = prepare_edit(mask, preview, mask[:, :, 2], 1000)
    assert edit["box"][0] == 0
    assert Image.open(io.BytesIO(depth)).size == Image.open(io.BytesIO(source)).size == edit["size"]
    assert all(side % 8 == 0 for side in edit["size"])
    graph = workflow("depth.png", "oak", 123, "source.png")
    assert graph["latent"]["class_type"] == "VAEEncode"
    for filename, data in [("mask.png", mask), ("preview.png", preview)]:
        Image.fromarray(data).save(tmp_path / filename)
    patch = encoded(Image.new("RGB", edit["size"], "red"))
    result = np.asarray(Image.open(io.BytesIO(composite_edit(tmp_path, edit, patch))))
    selected = mask[:, :, 2] == 232
    assert np.all(result[selected] == [255, 0, 0])
    assert np.array_equal(result[~selected], preview[~selected])
