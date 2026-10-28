# Florp rebuild test strategy

Baseline and scope: see FLORP_REBUILD_PLAN.md. Tests are layered and preserve the
existing extraction, review, calibration, evaluation and rendering contracts.

## Reproducible baseline and regression commands

- `cd apps/api && uv sync --frozen`
- `uv run python -m compileall -q app scripts tests`
- `uv run pytest -q`
- `cd apps/web && npm ci --no-audit --no-fund`
- `npx tsc --noEmit`
- `npm run build`

Use temporary SQLite databases for API tests and synthetic image fixtures for
reconstruction tests. No paid provider, model download or private credential is
required for deterministic CI. Existing provider mocks remain regression coverage,
not evidence of live model quality.

## Phase 1 contract tests

1. Initialize from a saved layout and read a projection of a specific revision.
2. Move a shared junction: all incident endpoints update, unrelated walls and
   opening dimensions remain identical, source snapshot stays unchanged.
3. Restore a parent: a new revision contains the historical graph, with current
   parent linkage and explicit restore metadata; older rows remain untouched.
4. Reject stale revision IDs, changed source layouts and cross-blueprint restore
   targets; verify row counts and saved layout are unchanged after rejection.
5. Projection refuses pending openings and does not invent floor polygons.
6. Frontend typecheck/build: graph workspace and legacy editor coexist; server
   errors are visible and controls disabled during pending mutations.
7. Manual UI: initialize, select/move junction, undo, preview 3D, reload, then
   edit legacy layout and verify stale graph controls reject further writes.

## Phase 2 solver tests

- Supported gap closes a broken boundary; derived room remains unverified.
- Blank raster and weak evidence do not create walls.
- Long gaps, image bounds, overlapping and crossing candidates are rejected.
- Complete source graph is unchanged by preview; stable ordering/IDs on reruns.
- Compatible-set selection does not allow individually valid but mutually
  conflicting proposals to cross or overlap.
- Openings retain their exact host/offset/width/height/sill and source evidence;
  new edges retain inference/evidence provenance.
- API preview writes no rows. Accept subset creates exactly one revision.
- Unknown IDs, duplicate IDs and empty selection fail without a partial write.
- Changed graph/layout/source raster rejects acceptance or recomputed mismatch.
- Undo restores original topology through an append-only revision.
- Existing real 34-wall regression fixture remains unchanged and non-gold.

## Validation reporting

For every implementation PR report baseline SHA, commit, commands, exact totals,
failures, fixes and rerun outcomes. Separate executed tests from unavailable UI,
model, licensing and real-plan evaluation. A green CI run does not satisfy the
empirical accuracy or correction-time release gates. Include remaining limits
in the PR description and docs/VALIDATION_RESULTS.md.

## Browser regression coverage: review-to-draft handoff

`cd apps/web && npm ci && npx playwright install chromium && npm run test:ui`
starts a local Next dev server. Four browser tests use controlled API responses
(no external models): opening-only review application and saved payload, graph
handoff and unsaved-edit protection, stale graph rejection, and visible unresolved
opening status. Backend HTTP tests independently exercise the actual projection
and host-reassociation handlers. These are workflow tests, not model accuracy or
photorealistic 3D visual-quality tests. CI runs this as a separate browser job.
