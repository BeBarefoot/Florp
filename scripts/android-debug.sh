#!/usr/bin/env bash
# Connect Android Chrome to the two local Florp development servers over USB.
set -euo pipefail
if [[ "$#" -gt 1 ]]; then
  echo 'Usage: scripts/android-debug.sh [device-serial]' >&2
  exit 2
fi
command -v adb >/dev/null || { echo 'Install Android SDK Platform-Tools and put adb on PATH.' >&2; exit 1; }
device=(adb)
if [[ "$#" -eq 1 ]]; then device+=(-s "$1"); fi
if [[ "$("${device[@]}" get-state)" != 'device' ]]; then
  echo 'Connect and unlock one Android device, then accept its USB debugging prompt. Run adb devices -l to check.' >&2
  exit 1
fi
if ! curl --fail --silent --show-error --max-time 30 http://localhost:3000/phone >/dev/null ||
   ! curl --fail --silent --show-error --max-time 10 http://localhost:8000/health >/dev/null; then
  echo 'Start both local Florp servers with ./scripts/dev.sh and wait until they are ready.' >&2
  exit 1
fi
"${device[@]}" reverse tcp:3000 tcp:3000
"${device[@]}" reverse tcp:8000 tcp:8000
"${device[@]}" reverse --list
echo 'Open http://localhost:3000/phone in Chrome on Android.'
echo 'For remote DevTools, open chrome://inspect/#devices in desktop Chrome.'
