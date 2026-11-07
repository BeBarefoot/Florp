# Autonomous engine validation — 7 November 2026

This executes the autonomous phase in [the POC plan](PRODUCTION_POC_PLAN.md).
No private plans, paid render calls, downloaded checkpoints or new training data
were needed. This is synthetic engineering evidence, not a model accuracy benchmark.

## What was tested and improved

| Area | Evidence / action | Limit |
|---|---|---|
| Source pixels → metric rooms → 3D | Shared analytical fixtures consumed by Python and TypeScript: equal/unequal wall thickness, moved partition, merged room. Verify inset polygons/bounds/areas, 1 cm/px calibration and 3D wall lengths/thickness. | Four orthogonal synthetic cases; not a general extraction benchmark or complete mesh-volume proof. |
| Room adjustments | Move retains label/type/ceiling. Split and merge mark ambiguous semantics for review; merged room does not silently inherit a bedroom label. | No new room-recognition model; labels still require user review. |
| Item discovery | Optional local YOLO suggestions now reject centers outside an explicit building outline, boxes with >25% wall/tread overlap, and same-class duplicates with IoU >.5. Tests retain distinct objects and prove no geometry mutation. | Heuristic thresholds; axis-aligned footprint and uncertain orientation. No measured recall gain; a narrow/misaligned outline can remove a real candidate. Default matcher remains unchanged. |
| Auto-capture generation | Reproduced a prompt missing a visibly captured bed. Build submitted visibility facts from the actual new capture rather than pre-capture React state. Browser regression checks visible-bed facts and unchanged depth/camera. | Mocked provider completion; no live output quality claim. |

The fixture suppression thresholds are review heuristics, not calibrated confidence.
Do not automatically accept candidates or label an undetected object absent.

## Reproduce

```sh
cd apps/api
uv run pytest -q tests/test_geometry_contract.py tests/test_fixture_context.py tests/test_scene_api.py
uv run pytest -q
```

```sh
cd apps/web
npm ci
npx playwright install chromium
npm run test:ui
npx tsc --noEmit
npm run build
```

Full backend result: **413 passed, 1 skipped**. Focused browser regressions:
**6 passed**, including auto-capture and shared geometry cases. The PR's GitHub
checks provide final full-browser and production-build evidence. No architectural
accuracy gate is closed by these tests.

## Next evidence and user input

No user input was needed for this phase. To improve the recognition model against
real deployment needs, obtain consented full plan examples across intended styles,
one known measurement each, and independently checked walls/openings/rooms/items.
Include incorrect suggestions, missing fixtures and empty regions, not just accepted
objects. Keep project-disjoint held-out data untouched while tuning.

Confirm supported styles and intended commercial usage before choosing checkpoints.
The optional FloorCAD checkpoint is not installed or activated by these tests.
Live generation QA needs an explicit provider spending cap and authorization; keep
credentials in server settings. Then run Gates B/E of the POC plan. Do not fine-tune
or claim production accuracy from synthetic stencils and these four geometry cases.
