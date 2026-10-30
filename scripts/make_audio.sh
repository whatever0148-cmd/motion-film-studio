#!/usr/bin/env bash
# Cue sheet + sounds (+ voice, music) -> mixed master -> film with sound. Usage: make_audio.sh <workspace> <silent.mp4> <out.mp4> [voice.wav] [music.wav]
set -euo pipefail
WS="${1:?workspace}"; SIL="${2:?silent video}"; OUT="${3:?output mp4}"; VOICE="${4:-}"; MUSIC="${5:-}"
PY="$WS/.venv/bin/python"; D="$(dirname "$OUT")/audio"; mkdir -p "$D"
DUR=$(ffmpeg -hide_banner -i "$SIL" 2>&1 | { sed -n 's/.*Duration: \([0-9:.]*\).*/\1/p' | awk -F: '{print $1*3600+$2*60+$3}'; } || true)
"$PY" "$WS/audio/make_sound_plan.py" --cues "$SIL.cues.json" --sounds "$WS/sounds" --out "$D/plan.json" --duration "$DUR" ${VOICE:+--voice "$VOICE"}
"$PY" -I "$WS/audio/mix_plan.py" "$D/plan.json" --out-dir "$D" ${MUSIC:+--music "$MUSIC"}
ffmpeg -v error -y -i "$SIL" -i "$D/master.wav" -map 0:v -map 1:a -c:v copy -c:a aac -b:a 256k -ar 48000 -shortest -movflags +faststart "$OUT"
echo "film with sound: $OUT"
