# Prove it: scanners and the fix loop

Run `bash scripts/scan_all.sh <workspace> <film.mp4> [payoff times] [WxH]` after every render. A scan measures; the human still watches and listens.

| Scanner | What it measures | Pass line |
|---|---|---|
| `qa/flaw_scan.py` | flashes, frozen frames, size and fps, first visible change, first-second energy, event gaps, loudness, true peak, safe zone, font size | verdict PASS (P0 none; every P1 fixed or waived with a reason) |
| `qa/skip_audit.py` | what a scroller feels: blank frame 0, first change by 0.35 s, first-second energy at least 1.2, an event in each 1.5 s window of the first 3 s, gaps of 2.6 s or less, text size in phone points, level jumps | no P0 or P1 |
| `qa/sound_qa.py` | -14 LUFS, true peak, phone-speaker prominence of hits (500 Hz high-pass), clipping, silence gaps, level steps, sync | PASS |
| `qa/motion_lint.mjs` | teleports (W01), kinks, ringing, overshoot, too many movers | zero P0 and zero teleports |

Run motion lint: `node qa/sample_scene.mjs --scene <index.html> --from 0 --to <frames> --out series.json` then `node qa/motion_lint.mjs series.json`.

## Fix order (rescan after each group)
1. Dead opening (frame 0 blank, no change by 0.35 s, weak first second): add a beat-locked ring, a settle push, a pop of the hero object from frame 0.
2. Teleports: end the mover before its target disappears, average a steeply jumping follow-point over 0.2 s, end ripples with their card.
3. Event gaps: a beat-locked ring, camera thump, or a real new event; never a distraction.
4. Sound: hit mids, ducking depth, level steps, true peak.
5. Text: at least 54 px for must-read text, accent ink contrast, safe zone.
6. Motion hygiene: overshoot caps, no layout properties, no `will-change` on text.
7. Then a final render at `--scale 2`, assemble the audio, scan everything again.

## Known quirks (report them, do not hide them)
- A mono down-mix can show false clipping; clipping is measured on the stereo channels.
- The flat-contrast check is weak on pastel scenes (informational).
- The event detector reads luminance only: a chroma-only pulse (a colour change with the same brightness) is not counted as an event; a 12 to 17 percent brightness dip is.
- A smaller screen share (a film inside a laptop in a 9:16 frame) lowers the measured energy; judge those by the retention graph after posting.
- Lint also reports reversals as "overshoot" when a word exits in the opposite direction; check before fixing.
