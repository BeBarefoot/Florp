import base64
import io
import json

import numpy as np
import pytest
from PIL import Image

from app.depth import control_depth
from scripts.depth_for_comfy import convert


def test_depth_preserves_background_and_constant_foreground():
    rgb = np.array([[[0, 0, 0], [0, 3, 232], [0, 7, 208]]], dtype=np.uint8)
    control, limits = control_depth(rgb)
    assert limits == (1000, 2000)
    assert control.tolist() == [[0, 255, 0]]
    assert control_depth(rgb[:, :2])[0].tolist() == [[0, 255]]
    with pytest.raises(ValueError):
        control_depth(np.zeros((2, 2, 3), dtype=np.uint8))
    with pytest.raises(ValueError):
        control_depth(np.full((2, 2, 3), 255, dtype=np.uint8))


def test_local_bundle_keeps_camera_and_metric_capture(tmp_path):
    buf = io.BytesIO()
    Image.new('RGB', (12, 8), (0, 3, 232)).save(buf, format='PNG')
    url = 'data:image/png;base64,' + base64.b64encode(buf.getvalue()).decode()
    capture = tmp_path / 'capture.json'
    metadata = dict(view={'yaw': 27, 'pitch': -10}, planRevision=7,
                    frame={'width': 12, 'height': 8}, prompt='Oak', maskIds={'1': 'Structure'})
    capture.write_text(json.dumps(dict(metadata, depth=url, mask=url, preview=url)))
    output = tmp_path / 'bundle'
    convert(capture, output, bundle=True)
    manifest = json.loads((output / 'manifest.json').read_text())
    assert all(manifest[k] == v for k, v in metadata.items())
    assert manifest['depthRangeMm'] == [1000, 1000]
    assert (output / 'depth.png').read_bytes() == buf.getvalue()
    assert Image.open(output / 'control.png').getpixel((0, 0)) == 255
    with pytest.raises(FileExistsError):
        convert(capture, output, bundle=True)
