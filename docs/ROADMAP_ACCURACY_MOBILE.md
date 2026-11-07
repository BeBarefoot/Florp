# Accuracy-first mobile roadmap

Updated 7 November 2026. This is the entry point linked from
[issue #1](https://github.com/BeBarefoot/Florp/issues/1).

The authoritative work packages, target metrics, prerequisites, owner roles and
release evidence now live in [Production POC delivery plan](PRODUCTION_POC_PLAN.md).
The [architecture audit](ARCHITECTURE.md) distinguishes implemented features from
unverified product claims. Earlier roadmap versions remain in Git history.

1. A: Reproducible setup and supported-input contract.
2. B: Gate 1 — held-out extraction/fixture benchmarks and correction-time evidence.
3. C: Revision-specific verification, calibration and 2D/3D/export parity.
4. D: Mobile-first guided review, PWA and real-device usability.
5. E: Authorized live provider validation and output structural consistency.
6. F: Authentication, authorization, durable jobs, backup/restore and hosted pilot.

Shared-node geometry, saved cameras, capture, provider submission and object
editing already exist. Reliable one-pass extraction, automatic scale, generation
consistency and production readiness have not been established. CI success is
engineering evidence, not proof that Gate 1 passed.

**Current release decision: not ready for a trusted homeowner pilot.** Close the
measured gates before marking issue #1 complete. Continue local development and
clearly labelled draft previews in the meantime.
