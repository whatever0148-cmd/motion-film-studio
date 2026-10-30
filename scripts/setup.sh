#!/usr/bin/env bash
# Sets up the motion studio workspace (default ~/motion-studio): engine, QA scanners, audio tools, Python venv. No paid tools.
set -euo pipefail
SK="$(cd "$(dirname "$0")/.." && pwd)"
WS="${1:-$HOME/motion-studio}"
mkdir -p "$WS"
cp -R "$SK/assets/engine" "$WS/direct-engine"; cp -R "$SK/assets/qa" "$WS/qa"; cp -R "$SK/assets/audio" "$WS/audio"; cp -R "$SK/assets/mockup" "$WS/mockup"
mkdir -p "$WS/projects" "$WS/references" "$WS/sounds"
[ -d "$WS/projects/starter" ] || cp -R "$SK/assets/starter" "$WS/projects/starter"
command -v node >/dev/null || { echo "MISSING node (need 20+): install from https://nodejs.org"; exit 2; }
command -v ffmpeg >/dev/null || { echo "MISSING ffmpeg: macOS 'brew install ffmpeg', Windows 'winget install ffmpeg', Linux 'sudo apt install ffmpeg'"; exit 2; }
(cd "$WS/direct-engine" && npm install --no-audit --no-fund)
PY=$(command -v python3.12 || command -v python3.11 || command -v python3)
"$PY" -m venv "$WS/.venv" && "$WS/.venv/bin/pip" install -q numpy
echo "ready: $WS"
echo "next: $PY $SK/scripts/doctor.py $WS"
