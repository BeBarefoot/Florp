# Florp rebuild implementation plan

Baseline: main `34adf6de0a11f8184b94edd85757dfaa24801288` (2026-10-28).
Source: recovered Research audit findings project discussion; this is a selective
reconstruction-layer redesign, retaining FastAPI/SQLite, perception, review,
React and Three.js. PR #4 supplies canonical graph primitives; PR #5 supplies
independent topology metrics and the non-gold 34-wall regression fixture.

## Invariants and release policy

Geometry is authoritative. Source images, detector evidence, editable graph,
confirmed scene and renders remain separate versions. Never infer physical door
widths, scale or floors merely to make a preview look complete. Windows retain
host, offset and dimensions. Every automatic modification is a reviewable
proposal with source revision and evidence; stale acceptance fails. Existing
layout APIs, extraction, review, exports and render behavior remain available.
No automatic migration of verified layouts and no overwriting historical graphs.

## Commit and PR sequence

1. Commit this plan and TEST_PLAN.md before implementation.
2. Phase 1 branch: canonical graph integration (stacked on the planning commit).
3. Phase 2 branch: global reconstruction (stacked on Phase 1 for isolated review).
4. Record commands, outcomes and outstanding empirical gates in each PR and
   docs/VALIDATION_RESULTS.md. Leave PRs reviewable; do not merge automatically.

## Phase 0: establish the baseline

Run the complete existing backend suite, Python compilation, frontend typecheck
and production build. Record failures separately from changes. Preserve the real
34-wall fixture unchanged: it is a regression case, not an accuracy reference.
Inspect current adapters and revision guards before extending them.

## Phase 1: canonical graph integration

- Add an explicit graph workspace to the blueprint editor. Load the latest
  revision or initialize from the saved layout with expected-version checking.
  Show stale status, validation errors and pending opening evidence.
- Draw walls and junctions from the persisted graph. Selecting a shared junction
  and moving it submits the existing atomic operation; display server results.
- Add append-only restoration of a historical revision, constrained to the same
  source layout and the latest revision. Undo must never delete history.
- Add a read-only geometry projection endpoint for graph-driven 2D/3D parity.
  Both previews consume the same graph revision. Refuse pending opening anchors;
  keep closed faces provisional and omit them from authoritative floors.
- Keep legacy workflows available; no implicit export into Layout.geometry.
  This opt-in integration is not approval of a production-wide migration.

Acceptance: source/revision concurrency checks; immutable history; all incident
walls move together; openings survive round trips; stale/invalid commands leave
no writes; graph 3D uses exactly the server projection; regression suite passes.

## Phase 2: global reconstruction proposals

- Operate on a whole canonical snapshot, preserving node and wall identity.
- Generate bounded missing-connection hypotheses between dangling junctions,
  including collinear continuations and perpendicular corners. Use source raster
  support as evidence; topology improvement alone cannot prove a wall exists.
- Evaluate candidates against the complete graph: crossing/overlap rejection,
  opening preservation, connected-component/dangling counts and closed faces.
  Rank deterministically; evaluate a compatible set incrementally so proposals
  cannot independently introduce conflicting geometry.
- Return individual alternatives, evidence scores, topology before/after and
  rejected/unsupported explanations. Keep no-evidence gaps unresolved.
- Accept an explicit subset on a fresh revision, recomputing from the server's
  source image and graph. Apply atomically as a new revision; never mutate the
  layout or mark inferred rooms/structure verified. UI supports preview and
  explicit acceptance; undo uses Phase 1 history.

Acceptance: broken-loop recovery with image support; blank-image negative;
competing/crossing connections; determinism; bounds; openings and source metadata
preserved; stale acceptance rejected; no preview writes; real fixture preserved.
This bounded deterministic solver is a first global reconstruction implementation,
not a claim of learned architectural inference or 90% real-world accuracy.

## Subsequent phases and dependencies

3. Room/conflict-first review: prioritize uncertainty, correction time and
   room-boundary conflicts using Phase 2 diagnostics.
4. Openings/scale: explicit hosts, dimension-chain calibration and unresolved
   evidence reconciliation; window-position/proportion parity is a hard gate.
5. Deterministic scene builder: graph-driven walls, supported floors and cutouts;
   production migration requires independently adjudicated benchmark parity.
6. Design/rendering: fixed geometry/camera iteration, no generative layout drift.
7. Production hardening: jobs, security, observability, backups and deployment.

Model/vector bake-off (Raster2Seq, HEAT, commercial alternatives) requires the
canonical benchmark contract, actual outputs, provenance and licensing review.
Do not train or change model dependencies on the strength of synthetic tests.

## Requirement-to-code matrix

| Requirement | Existing foundation | Planned extension | Gate |
|---|---|---|---|
| Shared editable geometry | plan_graph, graph_operations | graph workspace | API + frontend checks |
| Immutable revisions | PlanGraphRevision | restore/undo | stale/history tests |
| Shared 2D/3D truth | graph_adapter | revision projection | opening/geometry parity |
| Missing structure | local connectivity helpers | global_reconstruction | positive/negative topology tests |
| Traceable proposals | source layout revisions | source-bound preview/accept | atomicity + stale tests |
| Accuracy evidence | topology_metrics, benchmarks | full regression execution | gold corpus still required |

## Empirical release gates

At least ten distinct source-bound, independently adjudicated plans; wall
precision and recall >=90%; no missing exterior boundaries; <=5-minute correction
on >=80% of plans. Record image SHA, baseline and reference geometry, topology,
opening hosts, correction seconds and notes. The 34-wall snapshot and synthetic
fixtures do not establish these gates. Hands-on diagram QA and real model runs
must be reported as pending when unavailable, never counted as passes.
