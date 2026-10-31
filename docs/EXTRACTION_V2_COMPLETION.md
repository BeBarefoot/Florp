# Extraction accuracy v2 — implementation handoff

The remaining implementation checklist is complete. Validation for this handoff
is automated only. The user will perform the next real-plan app evaluation;
this document does not assert pixel-perfect extraction or measured real-plan
accuracy from synthetic tests.

## Completed work

| Item | Implementation and automated coverage |
| --- | --- |
| Classified-gap reconstruction | Only overlapping runs or classified opening evidence join a collinear gap. Repeated copies of partial evidence cannot add up to a full opening. Plain passages remain open. |
| Thickness outliers | Pieces outside 0.6–1.6 times the run median are replaced by the median before length weighting. At least three pieces identify an outlier. Parallel clustering is also protected against a single bloated width. |
| Extension and stubs | Extensions sample ink across the wall thickness, require longitudinal support, and respect their reach limit. Tiny isolated stubs are removed; short piers remain. Horizontal and vertical cases are covered. |
| Full worker integration | A synthetic raster with hatch, window rails, a thin partition, dimensions and site context passes through `build()` and `reconstruct()`. The test checks geometry, hosting, two rooms and exclusion of external objects. |
| Pale photographed hatch | Local paper chroma compensates color casts. Directional closing fuses hatch along a wall without growing it across its thickness. Parallel drawn outlines and local tint corroborate faded bands. Neutral window rails/stair strokes are suppressed in colored plans. Remeasured widths are capped more conservatively. |
| Garden/site context | Repeated long architectural bands provide a conservative crop when a closed footprint is unavailable or attached site leaders corrupt it. Attached side walls are retained beside window rows. This crop does not invent wall geometry. |
| Thin partitions | Long multi-pixel dark bands attached to structural cores survive even when they are too rare to form a width-histogram peak. Single-stroke decorative lines remain excluded. |
| Door/window/garage review | Door evidence supports 45°, 60° and 90° leaf positions. A garage needs repeated overhead-door dashes, not just a wide blank gap. Garages remain proposals. Opening spans stay tied to the physical wall gap. |
| Building-outline UI | Toggle, drag/release request and hinge-flip persistence are browser-tested. Pending edits are saved as a revision before outline re-extraction. Crossing or out-of-bounds polygons are rejected without replacing the saved model. |
| Approval threshold tuning | A local profile builder uses reviewed gold cases and empirical precision/sample requirements. Insufficient support disables automatic approval for that kind. Profiles are opt-in, validated and never activate themselves. |
| Gold/scoring integrity | Orphan opening predictions count as false positives. Inflated predicted thickness cannot widen its own scoring tolerance. Source hashes guard snapshots, existing snapshots require explicit replacement and are archived, and empty thresholds cannot silently disable readiness targets. Garage F1 is included. |
| Legacy opening path | `cv_openings.py` is explicitly deprecated and retained for compatibility. Production extraction calls `openings.detect`; the compatibility helper is referenced only by its legacy test. |

The source image, user reference length and saved revision history remain the
basis of the editor. One physical measurement changes derived units, not pixel
coordinates. Re-extraction does not certify scale or infer structure beyond a
cropped source.

## Automated validation

- API compile check: passed.
- Backend: **358 passed, 1 skipped**. The skip is the real-plan gold regression
  because `data/gold` has no reviewed cases in this workspace.
- TypeScript: passed.
- `npm run build`: passed.
- Playwright: **28 passed**, using an independently selected free local port.
- Playwright supports `FLORP_TEST_PORT` and never attaches to a different
  already-running app. It sets the admin flag for legacy workflow tests.

There is an existing Starlette/httpx test-client deprecation warning. It does
not fail the suite. macOS hardware performance and real-plan output quality
were not manually tested for this handoff.

## User app evaluation

Pull `main`, restart the API and web app using the README's normal commands,
then upload a source or use **Re-extract from drawing** on the tool rail for an existing
plan. Saved geometry is not silently re-extracted just by opening it.

The revised deterministic path is the default. Leave
`WORKSPACE_SEMANTIC_SOURCE` and `WORKSPACE_SEMANTIC_WEIGHTS` empty to evaluate it;
setting those selects the separate optional semantic evaluator instead.

Check the three original plans, correct geometry where necessary, set one known
length, approve/reject the proposed openings and save. Correcting the building
outline triggers a new extraction inside it and keeps prior saved revisions.

The remaining empirical question is how accurately this version handles those
real plans. Confidence scores remain heuristic evidence until reviewed cases
are available; they are not measured probabilities.

## Record reviewed references and tune approval thresholds

These commands operate on saved editor revisions. They do not train a model,
download checkpoints, or automatically promote an extraction provider.

From `apps/api`, after completing the source review:

```bash
uv run python scripts/snapshot_gold.py --blueprint <id1> --name case1
uv run python scripts/snapshot_gold.py --blueprint <id2> --name case2
uv run python scripts/snapshot_gold.py --blueprint <id3> --name case3
```

Each snapshot stores its source, geometry, revision and source hash under the
gitignored `data/gold/` directory. Proposed openings must be decided first.
`--replace` archives the previous snapshot instead of silently discarding it.

To record a comparison for each case:

```bash
uv run python scripts/evaluate_workspace.py \
  --image data/gold/case1/preview.png --gold data/gold/case1 \
  --output data/evaluations/case1 --debug
```

The regression readiness minimums are wall precision/recall of 0.9 and
per-kind door/window/garage F1 of 0.8. `--update-thresholds` can ratchet those
minimums upward; it cannot lower them to hide a poor baseline.

To produce an approval-threshold profile:

```bash
uv run python scripts/calibrate_openings.py \
  --gold-root data/gold --output data/opening-confidence.json
```

The builder requires at least three unique source cases. By default it requires
at least ten supported examples at 0.95 empirical precision for each kind. A
kind without sufficient support gets threshold `1.01`, which leaves its
openings for review. This is precision on the supplied cases, not a guarantee
for unseen plans.

To explicitly activate the resulting profile, set this in the API environment
and restart it:

```dotenv
OPENING_CONFIDENCE_PROFILE=/absolute/path/to/data/opening-confidence.json
```

Leave it empty to use the default conservative evidence thresholds. Garages,
unhosted proposals and ambiguous hosts always require review. An invalid
profile returns a configuration error and preserves the saved model. No gold
scores, manual-review attestations or calibrated thresholds were fabricated
for this handoff.
