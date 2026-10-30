# Engine A scene contract (HTML, Canvas, CSS rendered frame by frame by Chrome)

## Layout of a project
```
<workspace>/projects/<name>/scene/index.html   (loads the runtime, fonts, then main.js)
<workspace>/projects/<name>/scene/main.js      (one defineScene call)
<workspace>/projects/<name>/out/               (renders, cue sheet, safe-zone sidecar)
```
Copy `assets/starter` as the start. The page must load `/direct-engine/runtime/engine-runtime.js` (the render server maps `/direct-engine` and `/projects` to the workspace) and fonts from `/direct-engine/node_modules/@fontsource/<family>/<weight>.css` (installed by setup: inter, inter-tight, space-grotesk, jetbrains-mono, anton, archivo, caveat, instrument-serif, permanent-marker).

## defineScene
```js
EngineRuntime.defineScene({
  fps: 60, duration: 38.6, width: 1920, height: 1080,      // 1080 x 1920 for 9:16
  fonts: ['700 120px "Inter Tight"'],                      // waits for these before frame 0
  grain: { opacity: 0.035, cell: 2, seed: 7, blend: 'multiply' },
  cues: [{ t: 0.15, type: 'pop' }, ...],                   // sound cue sheet
  beats: [{ t: 0, kind: 'interrupt' }, { t: 2.1, kind: 'reset' }],
  setup() { /* build DOM once */ }, render(t) { /* draw frame at time t seconds */ },
});
```
Helpers on `EngineRuntime`: `clamp, lerp, seg(t, a, b)` (0..1 progress), `rng(seed)`, `ease.expoOut/cubicInOut/cubicOut/backOut(t, s)`, `spring(t, {stiffness, damping})`. Elements tagged `data-safe="text|hero|ui"` are checked against the safe zone.

## Purity rules (these stop glitches)
- Every frame is a pure function of `t = frame / fps`. No `Date.now`, `performance.now`, `Math.random` without a seed (`rng(seed)`), `requestAnimationFrame` loops, CSS animations or transitions, or video elements.
- The renderer seeks, so state kept between frames breaks parallel workers. Compute everything from `t`.
- An element at `scale(0)` has an empty rectangle: aim cursors at its parent.
- Frames are captured at device scale 2 and encoded to the target size. Sub-pixel details under 1 px shimmer.
- Targets read from the DOM (`getBoundingClientRect`) return nothing when a card is `display:none`: end the mover before the card hides.

## Render
- Stills (cheap look check): `--scale 1 --workers 1 --stills 3.0,6.2 --stills-out <dir>`; open the PNGs.
- Dry render at `--scale 1` must finish with zero errors, then the final at `--scale 2 --workers 4` (a 38 s film took about 2 to 3 minutes on an M2).
- The render writes `<out>.cues.json` (your cue sheet), `.render.json` and `.safezone.json` next to the video.
- Common failures: `Waiting failed` means the scene did not call `defineScene` (a JavaScript syntax error: run `node --check main.js`; a `//` comment at the end of a one-line statement swallows the rest of the line).

## Patterns that worked
- A TIMELINE object holding every cut, tap and wipe time; the cue sheet and the visuals both read it.
- Word-by-word headlines in three reveal families (smear, mask, pop) so neighbours never move the same way.
- Cards: pop in on the cut (spring), camera pushes per card (scale about 1.1 to 1.3, with focus point), rack focus (blur the groups that are not the focus), recede under the next wipe.
- Data panels drawn from real data (JSON in the scene folder), counters computed from it.
