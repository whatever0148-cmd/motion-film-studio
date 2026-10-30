# First-run interview and setup

Goal: leave the user knowing what they have, what is missing, and what is free. Keep each message short and numbered. Never ask them to paste secrets. Never suggest paid tools.

## 1. Check the machine (read-only)
Run `python3 scripts/doctor.py ~/motion-studio`. It reports Node 20+, ffmpeg, Chrome or Chromium, the installed engine, the Python venv, the number of reference videos and sounds.
- Missing Node: nodejs.org installer. Missing ffmpeg: `brew install ffmpeg` (Mac), `winget install ffmpeg` (Windows), `sudo apt install ffmpeg` (Linux). Missing Chrome: install Google Chrome (or set `CHROME_PATH` to a Chromium).
- Then `bash scripts/setup.sh ~/motion-studio` (copies the engine, installs npm packages and numpy). Only run installs the user agreed to.

## 2. Ask, then listen
Ask these as one numbered list and wait:
1. What is the video for and who should watch it? What should they do after? (one sentence)
2. Do you have reference videos you love (any motion design, ads, launch films)? If yes: put the files in `~/motion-studio/references/`. If you only have links, I can study a public video you paste (I download it only if you say yes).
3. Do you have sound effects, a voice, music? Options if not: see `sound-and-music.md`. I can set up a free sound library with you.
4. What real proof do you have for the screen (numbers, product screenshots, terminal output, hardware photos, your own face or voice)?
5. Where will it play: Instagram Reels or TikTok (9:16), YouTube or website (16:9)? 9:16 fills a phone; a 16:9 film on a phone is a small box.
6. Brand colours and font, or should I pick a calm house look (cream, ink, one bright accent)?

## 3. Tell them what you found, then propose
"You have X, you are missing Y, Y is free via Z, here is the plan in five lines. Say yes and I start." Do not start building before the yes.

## 4. If they have no references
Say it plainly: a reference video is the single biggest quality lever. Ask for 3 to 5 videos whose motion they like. Without them, use the house style in `craft-rules.md`.

## 5. Honesty rules for every report
- Scanners measure, they do not watch or listen. Say "measured", never "watched" or "listened" unless the human did.
- No guaranteed reach. Instagram publishes no ranking weights; the studio rules are tested heuristics.
- Free tools only; check every licence before using a sound, font or track in a public video.
