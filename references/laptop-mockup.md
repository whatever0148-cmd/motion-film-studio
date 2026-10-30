# Put the film on a real laptop screen (green screen photo to 9:16 reel)

This makes the film look like it plays on the creator's own laptop. It uses one green-screen photo, a chroma matte, a perspective warp of the film into the screen and a virtual camera. Everything is ffmpeg and numpy.

## Shooting the plate (tell the user, numbered)
1. On the laptop open a pure green full-screen image (#00FF00, any "green screen" page), brightness about 70 percent, turn off auto-brightness and night shift.
2. Photograph from a slight angle in portrait, the whole laptop (screen and keyboard) inside the frame with margin on all sides, camera steady, tap to focus on the screen, no fingers over the screen.
3. A hand on the trackpad is fine. Avoid a bright window directly behind the camera (it paints big glare on the glass, which the pipeline keeps as realistic reflections).
4. One sharp photo beats handheld video here: the virtual camera adds the slow push-in and a tiny sway.

## Run
`bash scripts/laptop_mockup.sh ~/motion-studio photo.jpg film.mp4 out_9x16.mp4 [screen_center_y]`
It runs `prep.py` (green matte, four screen corners from the matte extremes, despill, glare map) then `gen9.py` (ffmpeg graph) then encodes 1080x1920.

## What the graph does
- Film (16:9) is padded into a 16:10 panel with black bars like a real full-screen player, warped into the screen quad with ffmpeg `perspective`, and masked by the feathered matte (3 px inset to hide rounded corners and bezel).
- Surround: despilled, darkened curves, lowered saturation, vignette; a second slightly blurred copy is blended in by a mask that grows away from the screen (shallow depth of field), so the screen is the sharp bright focus.
- Real glare from the photo is screened back over the film at 35 percent; a faint tinted spill of the film lights the body; subtle grain.
- Virtual camera: slow push-in, a quick settle in the first second, tiny handheld sway, optional thumps (`mockup/work/params.json` key `punch`: beat times in seconds).
- The photo is padded above and below with a blurred, darkened stretch, feathered so no seam shows.

## Pitfalls already solved (do not re-learn them)
- ffmpeg `eq` on planar RGB (`gbrp`) treats blue and red as chroma: colours shift magenta. Convert to `yuv444p` before `eq` or `hue`, back to `rgb24` after.
- `perspective` needs planar input: `format=gbrp`, `sense=destination`, expressions use `in` (frame number) not `t`.
- `maskedmerge` wants all three inputs in `gbrp`.
- `extractplanes` needs a planar input format.
- Keep a screen glow tint low: a screen-blend of a mostly cream film reads as a milky white haze.
- Check frames at several times before the full render (a full 38 s render takes 10 to 20 minutes); render in the background and do not interrupt it.
- Instagram wants the film audio kept (`-c:a copy`).
