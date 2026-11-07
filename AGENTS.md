# Florp

Florp converts calibrated floor plans into editable 2D geometry, 3D scenes and optional styled renders. Start with [the Codex handoff](docs/codex-handoff.md) and the README.

- Keep extraction local and deterministic. The plan graph is the source of truth; scene objects and generated images do not change walls or openings.
- Preserve window position and size. Treat uncertain fixture symbols as suggestions for individual review. Never add them automatically.
- Keep .env files, keys, plan scans, and runtime databases out of Git. Tests should use synthetic or approved fixtures and mock paid image calls.
- For implementation tasks, run focused automated tests and report any baseline failures. Don't submit paid renders unless explicitly authorized.
