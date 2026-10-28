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
