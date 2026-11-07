"""Local conversion of camera-aligned RGB24 millimetres to depth control."""
import numpy as np


def control_depth(rgb):
    mm = np.asarray(rgb, dtype=np.uint32) @ np.array([65536, 256, 1], dtype=np.uint32)
    hit = mm > 0
    if not hit.any() or mm.max() > 80000:
        raise ValueError("no valid packed Florp depth data")
    near, far = int(mm[hit].min()), int(mm[hit].max())
    result = np.zeros(mm.shape, np.uint8)
    # A constant-depth surface is foreground, not an empty black frame.
    result[hit] = 255 if near == far else np.rint(255 * (far - mm[hit]) / (far - near)).astype(np.uint8)
    return result, (near, far)
