"""Full synthetic raster → worker → canonical graph regression."""

import cv2
import numpy as np
from shapely.geometry import LineString, Point as ShapePoint
from shapely.ops import unary_union
from app.workspace_worker import build
from app.plan_reconstruct import reconstruct
from test_ink_layers import hatch_band


def test_hatched_plan_dimensions_context_and_window_through_full_worker(
    tmp_path, monkeypatch
):
    from app import workspace_worker

    # Optional detector availability must not change this evidence-only case.
    monkeypatch.setattr(workspace_worker, "_detector_boxes", lambda *args: ([], False))
    image = np.full((480, 800, 3), 235, np.uint8)
    for box in [
        (150, 90, 300, 104),
        (360, 90, 600, 104),
        (150, 360, 600, 374),
        (150, 90, 164, 374),
        (586, 90, 600, 374),
    ]:
        hatch_band(image, *box, step=6, color=(200, 190, 228))
    hatch_band(image, 380, 104, 387, 360, step=5, color=(190, 180, 220))
    # Actual window rails occupy the top gap. Text and site objects do not.
    for y in (92, 97, 102):
        cv2.line(image, (300, y), (360, y), (55, 55, 55), 1)
    for x in range(150, 600, 16):
        cv2.line(image, (x, 50), (x + 7, 50), (70, 70, 180), 1)
    cv2.putText(
        image, "450", (330, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (70, 70, 180), 1
    )
    cv2.rectangle(image, (35, 400), (110, 445), (30, 30, 30), 8)
    for x in range(660, 760, 18):
        cv2.circle(image, (x, 230), 8, (30, 80, 35), 2)
    file = tmp_path / "synthetic.png"
    cv2.imwrite(str(file), image)
    document = build(file)
    model = reconstruct(document, "synthetic")
    assert model.envelope
    assert not model.scale.reference and model.scale.meters_per_pixel is None
    assert model.walls
    nodes = {n.id: n for n in model.nodes}
    lines = [
        LineString([(nodes[w.a].x, nodes[w.a].y), (nodes[w.b].x, nodes[w.b].y)])
        for w in model.walls
    ]
    network = unary_union(lines)
    for point in [(210, 97), (470, 97), (157, 230), (593, 230), (240, 367), (383, 230)]:
        assert network.distance(ShapePoint(point)) < 8
    assert all(
        130 <= min(nodes[w.a].x, nodes[w.b].x) <= max(nodes[w.a].x, nodes[w.b].x) <= 620
        for w in model.walls
    )
    assert not any(min(nodes[w.a].y, nodes[w.b].y) > 390 for w in model.walls)
    windows = [o for o in model.openings if o.kind == "window"]
    assert len(windows) == 1
    assert abs(windows[0].width_px - 60) < 10
    assert windows[0].host_wall_id in {w.id for w in model.walls}
    assert len(model.rooms) == 2
