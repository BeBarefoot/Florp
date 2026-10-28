# Rebuild validation results

## Baseline: main 34adf6d

- Backend: `uv run pytest -q` — 177 passed.
- Frontend: `npx tsc --noEmit` and `npm run build` — passed.
- Dependencies: uv sync and npm ci completed. npm reports existing deprecated
  three-mesh-bvh; no dependency upgrades included.

## Phase 1

- Backend full suite: 180 passed (one upstream TestClient deprecation warning).
- Python compileall: passed.
- Frontend: an initial JSX syntax error was caught by typecheck and fixed;
  final typecheck and production build results recorded in the PR.
- Added HTTP tests for projection/opening parity, shared-node movement,
  append-only undo, stale revisions/layouts, foreign targets and pending openings.
- Browser interaction QA, live model runs and independently adjudicated real-plan
  accuracy/correction-time gates remain unexecuted. No accuracy claim is made.

## Phase 1 remote validation

PR #6, remote head `5ef40e5846369f926e4a78e6106c84484740a52f`:
GitHub Actions Florp CI run 40665730050 completed successfully. Local final
frontend typecheck and production build also passed. The plan is the first
remote commit, `5beeb22c1c893d4e3f86bc4f36bde303ff1ca281`.

## Phase 2

Implemented bounded global ranking/compatibility selection of raster-supported
collinear continuations and perpendicular corners, immutable source-bound
preview/accept APIs, and an explicit checkbox/overlay review UI. Ranking prefers
straight repairs over equally supported corner hypotheses. Existing junctions,
wall identity, opening hosts/dimensions and unchanged room metadata are preserved.
Accepted inferred walls retain source wall IDs and the revision operation stores
the source raster SHA, parameters, token and selected evidence.

Validation:
- Full backend suite: 194 passed; one upstream TestClient deprecation warning.
- Python compileall: passed.
- Frontend typecheck and production build: passed.
- Positive cases: broken-loop closure, perpendicular corner, deterministic IDs,
  unchanged openings, append-only acceptance/undo and protected room metadata.
- Negative cases: blank raster/end-cap ink, long gaps, crossing existing walls,
  mutually crossing proposals, invalid parameters/dimensions, empty/duplicate/
  unknown selection, stale revision/layout and changed source image/parameters.
- Initial tests exposed ambiguous equal-score corner selection and an incorrect
  fixture-loader assumption; ranking and fixture loading were corrected.

### Existing real-plan import blocker

The preserved 34-wall snapshot imports two split edges shorter than the existing
3-pixel canonical validation minimum (`yolo-wall-33:edge:0` and
`yolo-wall-51:edge:0`). The new regression confirms reconstruction refuses this
invalid input without modifying it. The baseline topology benchmark allowed
inspection of this graph without requiring canonical validation. This is not a
new reconstruction success: explicit short-edge reconciliation is still needed
before that specific real snapshot can enter the canonical editing workflow.
No source edges or evidence were silently deleted to make a test pass.

### Remaining gates and scope limits

- The solver performs bounded whole-graph candidate ranking with greedy compatible
  selection; it is not an exhaustive optimizer, learned inference system or a
  solution for arbitrary missing room boundaries. It adds continuations/corners;
  it does not invent unsupported walls or move/merge existing junctions.
- Initial exact T/X intersections still use the existing import adapter. New
  endpoint-to-wall repairs, ambiguous overlaps and tiny-edge reconciliation need
  additional explicit graph operations and review.
- Raster support is dark-pixel coverage, not calibrated structural confidence;
  text/furniture can supply ink. All repairs require user selection.
- Real source raster/model QA, browser interaction QA, ten-plan gold benchmarking,
  >=90% wall metrics and correction-time targets are not validated here.
- Neither PR changes production defaults or automatically merges into main.

## Review-to-visible-geometry correction (after the user's screenshots)

The screenshots exposed a workflow gap: classification did not update geometry,
Save draft did not apply labels, and graph revisions could not feed the main
editor. The attached evaluation was only an unscored 21-wall baseline (17
components, 34 loose endpoints, no openings), not the 36-wall current draft.

Changes:
- Expose Apply reviewed walls + openings as the primary second step; distinguish
  classified detections from physical openings and allow opening-only application.
- Reassociate opening hints against the actual current draft instead of using
  stale model-proposal host IDs. Unresolved/ambiguous hosts remain unresolved.
- Show connected-geometry repair openly, and explicitly project a current graph
  revision into the main unsaved 2D/3D draft with stale/unsaved-edit guards.
- Resolve the previous 34-wall import blocker without deleting any source edges:
  canonical graph edges are subdivisions, so nonzero sub-3px fragments are valid.
  The 3px rule remains on user drawing/movement; zero-length edges are invalid.
  Existing legacy metric verification still reports very short walls for review.

Validation:
- 198 backend tests passed; Python compilation passed.
- Four Playwright browser tests passed against controlled API responses, covering
  opening-only apply/save, graph handoff, unsaved/stale protection, and explicit
  unresolved status. Actual backend routes have separate HTTP regression tests.
- Frontend typecheck and production build passed.
- Browser setup initially failed due to a truncated Chromium download. Playwright
  is pinned to 1.56.1; the download mirror succeeded and all four tests ran.
- No live-model rerun or complete-source reconstruction accuracy claim. Original
  source raster and current reviewed geometry are needed to measure the current
  screenshot case; the provided baseline is not its latest corrected geometry.

The earlier short-edge blocker is now resolved. Remaining architectural inference,
opening-host ambiguity, full-room reconstruction and gold-plan release gates are
not solved merely by making these workflows accessible.
