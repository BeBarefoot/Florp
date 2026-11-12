#!/usr/bin/env bash
# Build and run the local production UI; reuse the checked process lifecycle.
set -euo pipefail
exec bash "$(dirname -- "${BASH_SOURCE[0]}")/dev.sh" --production
