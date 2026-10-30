#!/usr/bin/env bash
# Runs every scanner on a finished film. Usage: scan_all.sh <workspace> <film.mp4> [payoff times, comma separated, default none] [WxH default 1920x1080]
set -uo pipefail
WS="${1:?workspace}"; V="${2:?film.mp4}"; PAY="${3:-}"; SIZE="${4:-1920x1080}"
PY="$WS/.venv/bin/python"; [ -x "$PY" ] || PY=python3
W="${SIZE%x*}"; H="${SIZE#*x}"; echo "{\"width_height\":[$W,$H]}" > /tmp/_spec.json
CUES="${V%.mp4}.cues.json"; [ -f "$V.cues.json" ] && CUES="$V.cues.json"
echo "== flaw_scan"; "$PY" -I "$WS/qa/flaw_scan.py" "$V" --spec /tmp/_spec.json 2>&1 | grep -E "Verdict|first visible|first-second|max gap|loudness|\| P[01]" 
echo "== skip_audit"; "$PY" -I "$WS/qa/skip_audit.py" "$V" --out-dir "$(dirname "$V")" 2>&1 | grep -E "skip_audit|first_|max_event|\[P" | cut -c1-200
echo "== sound_qa"; "$PY" -I "$WS/qa/sound_qa.py" "$V" ${PAY:+--payoffs "$PAY"} 2>&1 | grep -E "FAIL|VERDICT|LUFS|dBTP"
