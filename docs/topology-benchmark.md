# Canonical topology benchmark — reference and regression contracts

## Purpose

The existing `extraction_benchmark.py` checks raster-coordinate wall F1 and
union room IoU. This additional experiment measures whether inferred walls
**connect to the correct junctions and enclose the correct separate rooms**.

The benchmark is not a structural solver. It measures progress against a
separately verified reference and does not modify local saved plans.

## Gold reference policy

A `TopologyCase` contains the original preview SHA256, provider, graph,
and a `gold_standard` flag. Only independently adjudicated references are
eligible for scoring; a detector-reviewed wall export is **not** automatically
ground truth. Use exact original image pixels and preserve independent plans
in training/validation/holdout partitions. Record annotation/review provenance
outside the prediction itself.

The compact fixture
`apps/api/tests/fixtures/reviewed_34_wall_snapshot.json` is a *regression
case*, not gold. It reproduces the user's observed 34 approved walls and
21 classified opening labels but zero geometrically confirmed openings,
no room polygons, and unknown scale. It must not be used to quote model
precision, recall or user time saved.

## CLI

```bash
cd apps/api
uv run python -m app.topology_metrics \
  --image /path/to/original-preview.png \
  --truth /path/to/independently-verified-topology.json \
  --prediction /path/to/proposed-topology.json \
  --output /tmp/topology-result.json \
  --tolerance-px 5
```

The source image bytes and dimensions must match the gold reference; the
prediction case must carry the same source hash and pixel coordinate frame.
Read-only output includes junction F1, undirected adjacency-edge F1,
per-room polygon IoU-match F1 (threshold 0.5), opening host accuracy, and
graph health. Do not combine these into a single synthetic quality score.

## Next experimental decision

Compare present Florp YOLO/Yytsi fusion + conservative topology,
global polygon prediction, and a structured commercial baseline (subject
to licensing/privacy terms) on the **same independent reference set**.
Predefine acceptance thresholds and review-time measurement before evaluating;
do not tune on the holdout. Require meaningful topology/room improvement
and fewer manual corrections before changing production inference.

Human review must remain diagram-first; no model output is promoted
to verified physical scale or 3D structure by benchmark scores alone.
