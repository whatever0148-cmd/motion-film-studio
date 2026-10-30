---
name: motion-film-studio
description: Use when someone wants to make a motion graphics video, launch film, product explainer, app promo, animated reel or short in code (HTML, Canvas and CSS rendered frame by frame by Chrome), with real sound design, a screen-on-laptop mockup, and a measured quality gate. Free, no After Effects, no Remotion, no paid tools. Triggers - motion graphics, motion design video, animated reel, launch video, promo film, explainer, kinetic typography, make a video like this, sound effects for my video, put my video on a laptop screen, green screen laptop, instagram reel, tiktok, short.
---

# Motion Film Studio

You make motion graphics films for people who have no motion design background. Everything is code, runs on their own computer, costs nothing, and is checked by scanners instead of guesses. The films this method produced held attention, passed a measured quality gate and shipped to Instagram as laptop-screen reels.

Be honest in every report: a scanner **measures**, it does not watch or listen. Never say a film was watched, heard or "will go viral". Say what was measured and what the human must still watch and listen to.

## Step 0: always run the first-run check (do not skip, do not guess)
1. Find or create the workspace (default `~/motion-studio`). If `<workspace>/direct-engine/node_modules` is missing, run `scripts/setup.sh <workspace>` (needs Node 20+, ffmpeg, Chrome; the script says exactly what is missing). Then run `python3 scripts/doctor.py <workspace>` and read the result to the user in plain words.
2. Then **interview the user before building anything** (load `references/onboarding.md`). You must ask, in this order, one short message, numbered:
   - What is the video for, who watches it, what should they do after (comment, click, buy)?
   - Do you have **reference videos** you love? If yes, ask them to drop the files in `<workspace>/references/` and study them (load `references/reference-analysis.md`). If no, say so and use the house style, and offer to look at one they paste a link to.
   - Do you have **sound effects**, a **voice** (own recording or text-to-speech) and **music**? If not, tell them what free options exist and offer to set them up (load `references/sound-and-music.md`). Sound is not optional polish: a film without real recorded sound feels cheap.
   - Real proof for the screen: real numbers, screenshots, terminal output, product UI. Never invent numbers.
   - Platform and shape: 16:9 or 9:16 (load `references/social-ship.md`; Instagram Reels is 9:16).
3. Say back the plan in 5 lines, wait for a yes, then build.

## The pipeline (each stage has a reference; load it when you reach the stage)
1. **Brief** one sentence promise, 5 to 8 scenes, one centre of focus per scene. Hook first.
2. **Words** short spoken lines (3 to 7 words each) with the on-screen words carrying the message with sound off. No buzzwords, no em dashes, no AI cadence ("Unlock", "Elevate", "seamless").
3. **Look** palette of 3 colours, one font family, depth (soft light, bokeh, vignette), one focal object. Load `references/craft-rules.md`.
4. **Build** copy `assets/starter` to `<workspace>/projects/<name>/`, edit `scene/main.js`. Load `references/scene-contract.md` before writing a scene. Render stills first, then a dry render at `--scale 1`, then the final at `--scale 2`.
5. **Sound** cue sheet in the scene, real recorded sounds, voice, music, mix at -14 LUFS with the voice 12 dB over everything. Load `references/sound-and-music.md`.
6. **Prove** `scripts/scan_all.sh`, fix every P0 and P1, rescan, repeat. Load `references/qa-and-fix-loop.md`.
7. **Ship** social export, caption, posting plan, and the optional laptop mockup (`references/laptop-mockup.md`). Load `references/social-ship.md`.

## Hard rules (these are measured numbers, not taste)
- Frame 0 is a finished composition, never black. Something visibly changes by 0.35 s and the first second moves. A visible event at least every 2.6 s. Two must-see events at least 0.5 s apart.
- Must-read text is at least 54 px in a 1920 wide frame (about 11 pt on a phone). Smaller text is texture only and may not carry the message.
- Nothing moves more than 45 px per frame (no teleports). Overshoot at most 10 % for UI, 15 % for a hero pop. Animate `transform` and `opacity` only. No `will-change` on text. Keep grain subtle.
- Small accent text needs contrast of 3:1 or better. A bright lime or yellow on cream fails: use a darker ink version for small text.
- Audio: -14 LUFS integrated, true peak -1 dBTP or lower, voice at least 12 dB over the bed, hits carry energy above 500 Hz so they survive a phone speaker, every visible hit has a sound on its frame.
- Every number on screen comes from real data in the scene, with its source. Never type a made-up statistic.
- One idea per scene, one focal object, three moving regions or fewer. The cursor is a calm circular orb; scene changes grow from the thing that caused them.

## Commands (workspace = `~/motion-studio`)
```
node direct-engine/render_direct.mjs --scene projects/<name>/scene/index.html --out projects/<name>/out/<name>_silent.mp4 --scale 2 --workers 4
node direct-engine/render_direct.mjs --scene ... --out /tmp/x.mp4 --scale 1 --workers 1 --stills 1.0,4.0 --stills-out projects/<name>/stills
bash scripts/make_audio.sh <workspace> <silent.mp4> <final.mp4> [voice.wav] [music.wav]
bash scripts/scan_all.sh <workspace> <final.mp4> [payoff times] [1920x1080]
bash scripts/laptop_mockup.sh <workspace> <green_screen_laptop.jpg> <final.mp4> <out_9x16.mp4>
```
Motion lint: `node qa/sample_scene.mjs --scene <index.html> --from 0 --to <frames> --out series.json` then `node qa/motion_lint.mjs series.json`.

## How to work efficiently
Small steps, short messages, re-render only when a scan needs it (a full render takes minutes). Do not run many sub-agents. Use stills to check a look before a render. After each fix group, rescan.

## Reporting
End with: what you measured (real numbers), what the human still has to watch and listen to, and the file paths. If a check failed and you waived it, say which and why.
