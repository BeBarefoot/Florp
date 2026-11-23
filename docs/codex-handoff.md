# Florp contributor handoff

Florp is a local, single-user app for buyers and homeowners to turn plans into editable, walkable models. Prioritize first-pass accuracy, then give the buyer touch-friendly repair tools and a chat assistant that proposes corrections for approval. The repair assistant is planned.

- [Run and test Florp](../README.md#develop-and-test). Use the locked Python and Node dependencies. The repository carries source and synthetic fixtures. Local projects, source drawings, databases and provider keys stay in the owner's workspace.
- [Architecture](ARCHITECTURE.md). PlanModel revisions own structural geometry and calibration. Scene revisions own cameras, objects and finishes. Shared 3D meshes and exports derive from the saved model. Drafts and buyer-approved revisions have distinct states.
- [Accuracy-first roadmap](ROADMAP_ACCURACY_MOBILE.md) and [release gates](PRODUCTION_POC_PLAN.md). Work next on independent real-plan annotations, first-pass accuracy, phone correction time and tests on physical phones. Keep held-out plans out of tuning and private drawings out of Git.
- [Phone flow](PHONE_APP_PLAN.md). The viewer supports direct entry, touch movement, dollhouse landing and saved views. Use **Edit floor** for structural corrections. The missing-floor shortcut creates a walkable zone and guides camera placement.
- [Fixture detection](FIXTURE_WEIGHTS.md). The default matcher runs locally on the source drawing. Optional trusted weights produce suggestions for individual approval, including orientation checks.
- [Local ComfyUI and capture bundle](LOCAL_COMFY.md). Local generation needs a compatible model setup. Comfy Cloud and fal are optional hosted providers. Keep credentials server-side and mock billable calls in tests.
- [Project history](../HISTORY.md) and [issue #1](https://github.com/BeBarefoot/Florp/issues/1) record implementation and release evidence.
