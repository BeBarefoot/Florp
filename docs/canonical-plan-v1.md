# CanonicalPlan v1 — Experimental architecture migration

## Why this exists

Research on Florp's reviewed geometry identified a structural mismatch: independent
wall endpoints and separate room polygons can drift apart. Incremental snapping
improves small cases but is not a canonical model of architectural topology.

CanonicalPlan v1 is an **additive, opt-in foundation** for shared junctions, wall
edges, opening hosts, and rooms made from closed wall cycles. It does **not**
replace `Layout.geometry` or alter the public 2D/3D editor yet.

## Invariants

- Every wall edge references two shared node IDs; moving a node moves all its
  incident wall endpoints atomically.
- Crossing and T-junctions from the existing structural-graph extractor are
  represented as split edges, retaining `source_wall_id` for traceability.
- A room hypothesis is created only from an explicitly supported closed cycle.
  It is not verified merely because Shapely finds a polygon.
- Starter placeholder rectangle walls are not imported as architectural evidence.
- Door/window openings remain hosted; split operations remap a fully contained
  opening or refuse if the cut intersects it.
- Unresolved legacy opening anchors live in `pending_openings`; metric
  exports **refuse** to silently lose them.
- Missing metric scale is not guessed. New physical openings require confirmed
  scale. An unconfirmed legacy opening is not silently promoted.
- Edits return a new validated snapshot, never partially mutate the input.
- Graph revisions are append-only and never write `Layout.geometry`.

## Experimental REST API

- `POST /blueprints/{id}/canonical-plan/preview` — read-only conversion of
  latest saved layout and validation issues, **not saved**.
- `POST /blueprints/{id}/canonical-plan/revisions` with
  `{"expected_layout_version": N}` — initialize a graph snapshot explicitly.
- `GET /blueprints/{id}/canonical-plan/revisions/latest` — latest snapshot and
  whether the legacy layout has changed.
- `POST /blueprints/{id}/canonical-plan/revisions/{revision_id}/operations`
  — one atomic `GraphOperation` against the latest revision ID.

Operations: `move_junction`, `split_wall`, `remove_wall`, `add_wall`,
`attach_opening`. Example:

```json
{"kind":"move_junction","node_id":"junction-4","point":{"x":120,"y":80}}
```

422 means the proposed edit fails structural or opening validation; 409 means
the layout/revision changed and the client must refresh. An edit does not
automatically modify the legacy floor plan, UI, 3D model, or training labels.

## Migration and benchmark gates

1. Compare this graph representation against reviewed floor-plan exports.
   Record unsupported gaps, branching/intersection ambiguities, duplicate
   wall axes, room face count, and opening-host status. **A reviewed export is
   not ground truth simply because it has labels.**
2. Build independently adjudicated gold geometry on multiple distinct plans;
   use the existing `extraction_benchmark.py` for wall/room metrics and add
   topological metrics (junction F1, room adjacency, continuity, user edit time).
3. Resolve pending opening anchors and split-wall provenance without loss.
4. Expose a single graph-driven, undoable spatial edit interaction in 2D.
5. Only after the above, move 3D geometry reads to canonical graph exports
   behind an explicit feature gate with parity tests and rollback.

## Known v1 limitations

- Shared nodes are currently derived from the legacy wall centerline graph;
  there is no global architectural optimizer or evidence-weighted model yet.
- Node identifiers are stable across a persisted revision but source imports
  generate them from the legacy graph. Reimporting changed geometry may assign
  different IDs; cross-import identity reconciliation is future work.
- No beam/column, floor-level, stair, curved wall, layered wall-face or
  CAD/BIM representation.
- Polygonized closed contours can be wrong architectural rooms. Every face
  is a *hypothesis*, never a confirmed room.
- Legacy unresolved openings are preserved but cannot yet be automatically
  exported until they have an explicit edge host and confirmed dimensions.
- Frontend and existing `Viewer3D` still read the original saved layout;
  **no visual improvement should be claimed solely from this PR**.

Run `cd apps/api && uv run pytest -q tests/test_canonical_plan.py tests/test_canonical_plan_api.py`
and the full CI suite.

## Rebuild workspace and reconstruction additions

The blueprint page now exposes an opt-in **Canonical graph workspace**. Initialize
from the current saved layout, select a junction and edit its coordinates, undo
with append-only restoration, and view the same graph projection in 2D/3D.
Projection still refuses unresolved opening anchors and omits provisional floors.

- `GET /blueprints/{id}/canonical-plan/revisions/{revision}/geometry`
- `POST .../{revision}/restore` with `{"target_revision_id":"earlier-id"}`
- `POST .../{revision}/reconstruction/preview` with optional `max_gap_px` (6–200,
  default 80) and `min_support` (0.5–1, default 0.8)
- `POST .../{revision}/reconstruction/accept` with those same parameters,
  `preview_token` and a nonempty `candidate_ids` selection

Preview is read-only. Accept recomputes candidates against the current source
raster; changed image, parameters, layout or revision rejects stale acceptance.
The UI starts with no repairs selected and overlays proposals on the source image.
Conflicting selections fail atomically. Source SHA, settings and selected evidence
are stored with the accepted revision. See VALIDATION_RESULTS.md for tested scope
and the existing short-edge import blocker on the non-gold real-plan snapshot.

### Main editor handoff and short source subdivisions

`POST .../{revision}/draft` returns the current graph as an **unsaved** main-editor
geometry projection after checking both revision and source layout freshness.
The UI's **Use repaired graph in main 2D/3D draft** action refuses to overwrite
unsaved edits. Saving uses the existing versioned layout workflow. Pending opening
anchors still block projection, and old room polygons are not resurrected as floors.

Canonical edges are source-wall subdivisions: a legitimate intersection can leave
a nonzero fragment shorter than three pixels. These fragments are retained, while
zero-length edges remain invalid. User add/move commands retain their three-pixel
minimum. This resolves the real 34-wall fixture's prior canonical import failure
without changing its source coordinates or discarding provenance.
