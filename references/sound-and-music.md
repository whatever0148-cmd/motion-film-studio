# Sound, voice and music (free)

Sound is half of why a film feels expensive. Use **real recorded** sounds (clicks, cloth swishes, glass, paper, sub hits), not synthesised beeps.

## 1. Check what the user has
Count files in `<workspace>/sounds`. If empty, offer to build a library together. Ask permission before downloading anything and state the source and file size.

## 2. Free sound sources (check each licence before a public post)
- Kenney (kenney.nl) audio packs: CC0.
- Freesound (freesound.org): filter by licence "Creative Commons 0".
- Sonniss GameAudioGDC bundles: royalty free, read the licence text.
- OpenGameArt: licence varies per file, keep only CC0 or CC-BY and credit CC-BY in the caption.
Folder layout the scripts read: `sounds/<cue type>/*.wav` with types `pop whoosh wipe tick press ping thud thud-mid hit word riser bloom swell logo room glide zoom`. A cue type without a folder falls back to `sounds/any`. Collect 5 to 15 variants for each of: tick/click, swish (cloth, air), pop, glass ping, low thud, riser, room tone. Short (50 to 600 ms), dry, no reverb tails, no music.

## 3. Voice (free options, say which one you used in the caption if synthetic)
- Own recording: best. Quiet room, phone 20 cm from mouth, 150 to 175 words per minute, a breath every 2 to 3 s.
- Google AI Studio (Gemini text to speech, free tier), macOS `say` (offline), Piper (open source, offline). Direct it: short style string, CAPITALS for stress, three to six takes per block, pick by measured loudness and a listen by the human.
- Word timings matter: cut the visuals to the words. Aim lines at 3 to 7 words.
- Disclose a synthetic voice in the caption and use the platform's AI label toggle.

## 4. Music
Only a licence you can prove for social posting (royalty-free packs, your own, or none). A bed is optional; with a bed, fit its tempo so cuts land on the beat grid, put the drop on the key visual moment, and duck it under the voice.

## 5. Cue sheet rules
- Every meaningful visual change has a sound on its frame, and every sound has a visual change (no orphan sounds).
- Audio may be 0 to 17 ms late, never more than 15 ms early.
- Do not repeat the same sample twice in a row (the script cycles variants).
- Hits (`thud`, `hit`) carry mids above 500 Hz so they survive a phone speaker: `make_sound_plan.py` layers a mid transient from `sounds/thud-mid` (or `pop`) under every hit.
- A riser ends on the beat it leads into (`align: end`). Silence before a payoff is a tool.

## 6. Mix (done by `make_audio.sh`)
Four stems: 1 sub and impacts (not ducked), 2 foley mids (ducked about 2 dB), 3 air and bed (ducked 12 dB or more by the voice), 4 voice. Master -14 LUFS integrated, true peak -1 dBTP or lower, measured with ebur128; check with `qa/sound_qa.py` (add `--payoffs t1,t2` for the hit times). Known quirk: sound_qa's sync check measures soft-attack samples loosely; a median offset near 0 ms with a high p90 is a measurement artefact, report it, do not chase it forever.
