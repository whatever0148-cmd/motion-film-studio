# Craft rules (look, motion, text, opening)

## Look (calm, premium, not template)
- 3 colours plus ink: background, one bright accent, one soft secondary, ink for text. Soft radial light pools drifting slowly, a few bokeh discs, a light vignette. Depth beats decoration.
- One focal object per scene and it is the fastest mover. At most three regions move at once.
- Cards: radius 28 to 36 px, soft large shadow, never harsh outlines. Small labels are texture.
- Backgrounds change on scene cuts only; a wipe grows out of the thing that caused it (a tapped tile, a mascot, a button), never slides in from nowhere.

## Opening (the first 3 seconds decide the retention graph)
- Frame 0 is composed and finished: a specific image, not a logo, not black.
- Visible change by 0.35 s, a moving first second (mean frame change 1.2 or more), an event in each 1.5 s window of the first 3 s.
- The first line is 4 to 6 words, readable with sound off.
- A hook that states the surprise ("This sounds made up.") then proves it in the next scene.

## Rhythm
- A visible event at least every 2.6 s (a cut, a wipe, a tap that changes the screen, a count lock). Taps and cuts land on the music beat grid when there is music.
- Where a long hold is needed, add a purposeful beat-locked event: a ring that grows from the focal object, a camera thump of 3 percent, a dip of 12 to 16 percent brightness for 0.3 s. Do not add events that distract from the focal object.
- One proof peak at 55 to 75 percent of the film (a number, a result, a moment worth a screenshot) and one new open loop around 60 to 70 percent.

## Motion
- Animate `transform` and `opacity` only; never `top`, `left`, `width`, `font-size`. No `will-change` on text.
- Easing: expo out for entries, cubic in-out for travel. Springs: damping ratio at least 0.6. Overshoot at most 10 percent for UI, 15 percent for a hero pop. Never two eases joined with different speeds.
- Stagger words 0.12 to 0.25 s. Anticipation then settle on every hero element.
- Nothing moves more than 45 px per frame. A cursor or any mover must be continuous: if a target disappears (its card is hidden) end the mover, do not jump to a guessed spot.
- The cursor is a calm circular orb with a soft shadow; it presses (scale 0.86) on a tap and the UI answers on the same frame.
- Motion blur or a short ghost trail on anything faster than 600 px per second.

## Text
- Must-read text at least 54 px in a 1920 wide frame (about 11 pt on a phone). Headlines 100 to 120 px. Smaller text is texture only.
- Contrast: body text 4.5:1. Small accent text 3:1 at least: a bright lime accent such as #86B50A on cream is 2.2:1 and fails; use #719808 (3.0:1) or #597807 (4.55:1), or use the bright accent only at 100 px or larger.
- Keep text inside the safe zone (the renderer reports violations). Show counts as `Math.round(lerp(...))` from the scene's own data.

## Surface and polish
- Grain: subtle (opacity 0.03 to 0.04, cell 2). Full-frame noise multiplies encoded bits and looks muddy after Instagram recompression.
- Avoid hairlines under 2 px and fine gradients without dither (banding after recompression).
- Dark scenes are fine; keep the focal object brighter than the surroundings.
