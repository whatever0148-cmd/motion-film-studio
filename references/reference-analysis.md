# Study a reference video (turn "I love this" into numbers)

Use this when the user has videos they like. Ask for permission before downloading anything from a link, and only from public pages. Local files need no download.

## Measure (ffmpeg only)
```
# size, fps, duration
ffmpeg -hide_banner -i ref.mp4
# cuts per minute: count scene changes
ffmpeg -i ref.mp4 -vf "select='gt(scene,0.30)',showinfo" -f null - 2>&1 | grep -c pts_time
# first 3 seconds at 6 fps, as a contact sheet to LOOK at
ffmpeg -ss 0 -t 3 -i ref.mp4 -vf "fps=6,scale=320:-1,tile=6x3" -frames:v 1 hook.png
# one frame per scene change (what each scene looks like)
ffmpeg -i ref.mp4 -vf "select='gt(scene,0.30)',scale=480:-1" -vsync vfr scene_%03d.png
# loudness and loudest moments
ffmpeg -i ref.mp4 -af ebur128=peak=true -f null - 2>&1 | grep -E "I:|Peak"
```
Then run the studio scanners on the reference (`qa/flaw_scan.py`, `qa/skip_audit.py`): time to first change, first-second energy, event cadence, text sizes. Look at the contact sheets and write down:
1. Palette (3 dominant colours, sampled from stills), font feel, text size relative to the frame.
2. Hook: what is on frame 0, what changes first, when the first words appear.
3. Rhythm: cuts per minute, typical gap between events, where the biggest moment is.
4. Motion character: eases (snappy or floaty), how elements enter and exit, what the camera does, how scene changes are caused.
5. Sound: where hits and risers sit, whether there is a voice, how loud the bed is.
Save the findings to `<workspace>/references/<name>.md` so the next video reuses them. Say plainly what was measured and what is your reading of the frames.

## Use it
Turn the numbers into the scene's TIMELINE and look: copy the rhythm and the structure, never copy the artwork, text or brand of someone else's video.
