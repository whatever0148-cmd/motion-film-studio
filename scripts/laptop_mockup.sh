#!/usr/bin/env bash
# Puts a finished film on a green-screen laptop photo (9:16 social cut). Usage: laptop_mockup.sh <workspace> <laptop_green_screen.jpg> <film.mp4> <out.mp4> [screen_center_y default 650]
set -euo pipefail
WS="${1:?workspace}"; PLATE="${2:?photo}"; FILM="${3:?film}"; OUT="${4:?out}"; TY="${5:-650}"
abs() { python3 -c "import os,sys;print(os.path.abspath(sys.argv[1]))" "$1"; }
PLATE="$(abs "$PLATE")"; FILM="$(abs "$FILM")"; OUT="$(abs "$OUT")"; WS="$(abs "$WS")"
PY="$WS/.venv/bin/python"; W="$WS/mockup/work"; mkdir -p "$W"; cp "$PLATE" "$W/plate_src.jpg"; cd "$W"; cp ../gen9.py ../prep.py .
DUR=$(ffmpeg -hide_banner -i "$FILM" 2>&1 | { sed -n 's/.*Duration: \([0-9:.]*\).*/\1/p' | awk -F: '{print $1*3600+$2*60+$3}'; } || true)
echo "{\"dur\": $DUR, \"ty\": $TY, \"punch\": []}" > params.json
"$PY" prep.py plate_src.jpg && python3 gen9.py
ffmpeg -hide_banner -y -loop 1 -framerate 60 -i plate_clean.png -loop 1 -framerate 60 -i aux.png -i "$FILM" -filter_complex_script graph9.txt -map "[v]" -map 2:a? -t "$DUR" -r 60 \
  -c:v libx264 -preset medium -crf 18 -pix_fmt yuv420p -colorspace bt709 -color_primaries bt709 -color_trc bt709 -c:a copy -movflags +faststart "$OUT"
echo "mockup: $OUT"
