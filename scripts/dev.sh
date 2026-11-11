#!/usr/bin/env bash
# Run from any directory. Dependencies are installed separately with locked versions.
set -euo pipefail
repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
command -v uv >/dev/null || { echo 'Install uv, then follow README setup.' >&2; exit 1; }
command -v npm >/dev/null || { echo 'Install Node.js 22, then follow README setup.' >&2; exit 1; }
[[ -d "$repo_root/apps/api/.venv" && -d "$repo_root/apps/web/node_modules" ]] || {
  echo 'Install dependencies first: (cd apps/api && uv sync --locked) and (cd apps/web && npm ci)' >&2
  exit 1
}
pids=()
cleanup() {
  trap - EXIT INT TERM
  for pid in "${pids[@]}"; do kill "$pid" 2>/dev/null || true; done
  wait || true
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
(cd "$repo_root/apps/api" && exec uv run --locked uvicorn app.main:app --host 127.0.0.1 --port 8000) &
pids+=("$!")
(cd "$repo_root/apps/web" && exec node node_modules/next/dist/bin/next dev --hostname 127.0.0.1 --port 3000) &
pids+=("$!")
echo 'Starting Florp at http://localhost:3000 (API http://localhost:8000). Keep this terminal open; Ctrl+C stops both.'
# Portable to macOS Bash 3: stop the companion if either process exits.
while kill -0 "${pids[0]}" 2>/dev/null && kill -0 "${pids[1]}" 2>/dev/null; do sleep 1; done
exit 1
