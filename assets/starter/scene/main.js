/* Starter motion film: 12 s, 1920x1080, 60 fps. Every frame is a pure function of t (no Date.now, no random without a seed).
   Pattern to copy: a TIMELINE of times, a cue sheet for sound, small functions that draw each thing from t. */
(function () {
  const R = EngineRuntime, { clamp, lerp, seg } = R, E = R.ease;
  const $ = (id) => document.getElementById(id);
  const DUR = 12;
  const ev = (t, t0, d) => seg(t, t0, t0 + d);
  const pop = (p) => E.backOut(p, 1.2);                     // about 5 % overshoot: UI size. Hero pop at most 1.9 (about 13 %).
  /* ---- timeline: every cut, tap and wipe time in one place. Snap these to the music beat grid once you have a bed. */
  const T = { h1: 0.15, card: 2.4, count0: 3.0, count1: 4.6, tap: 4.7, wipe: 6.6, h3: 7.0, end: 11.0 };
  const WORDS1 = [['Motion', 0.15], ['graphics', 0.4], ['in', 0.62], ['code.', 0.8]];
  const WORDS3 = [['Built', 7.0], ['by', 7.25], ['you.', 7.45]];
  /* ---- sound cue sheet: [time, semantic type]. The audio script maps each type to a real recorded sample. */
  const cues = [[0.0, 'room'], [0.15, 'pop'], [0.8, 'ping'], [T.card, 'whoosh'], [T.count0, 'tick'], [T.tap, 'press'], [T.wipe, 'wipe'], [T.h3, 'word'], [T.end, 'logo']].map(([t, type]) => ({ t, type }));
  const beats = [0, 0.8, T.card, T.tap, T.wipe, T.end].map((t) => ({ t, kind: 'reset' }));
  const mkWords = (host, words, accentFrom) => words.map(([txt], i) => { const s = document.createElement('span'); s.className = 'w' + (i >= accentFrom ? ' acc' : ''); s.textContent = txt; host.appendChild(s); return s; });
  let w1, w3;
  function setup() { w1 = mkWords($('h1'), WORDS1, 3); w3 = mkWords($('h3'), WORDS3, 2); }
  function bg(t) {                                           // one calm gradient plus two soft drifting lights: depth without noise
    const c = $('bg').getContext('2d'); c.clearRect(0, 0, 1920, 1080); c.fillStyle = '#F3F2EC'; c.fillRect(0, 0, 1920, 1080);
    [[0.3, 520, 'rgba(201,242,58,.28)'], [0.2, 640, 'rgba(190,170,240,.18)']].forEach(([f, r, col], i) => {
      const x = 960 + Math.sin(t * f + i * 2) * 420, y = 540 + Math.cos(t * f * 0.8 + i) * 220, g = c.createRadialGradient(x, y, 0, x, y, r);
      g.addColorStop(0, col); g.addColorStop(1, 'rgba(255,255,255,0)'); c.fillStyle = g; c.fillRect(0, 0, 1920, 1080);
    });
  }
  function words(arr, list, out, t) {                        // each word rises with a mask-like slide, all on transform
    arr.forEach((s, i) => { const p = ev(t, list[i][1], 0.45), q = E.expoOut(p), o = 1 - ev(t, out, 0.3);
      s.style.opacity = clamp(p * 4) * o; s.style.transform = `translateY(${(1 - q) * 60}px) scale(${0.9 + 0.1 * q})`; });
  }
  function render(t) {
    bg(t);
    words(w1, WORDS1, 2.2, t); words(w3, WORDS3, 11, t);
    const cp = pop(ev(t, T.card, 0.5)) * (1 - ev(t, T.wipe - 0.2, 0.3)), card = $('card');
    card.style.opacity = clamp(ev(t, T.card, 0.2)) * (1 - ev(t, T.wipe - 0.2, 0.3));
    card.style.transform = `translateY(${(1 - E.expoOut(ev(t, T.card, 0.6))) * 90}px) scale(${0.92 + 0.08 * cp})`;
    $('num').textContent = Math.round(lerp(0, 38, E.cubicInOut(ev(t, T.count0, T.count1 - T.count0))));     // numbers come from the scene's own data, never typed
    // the calm orb cursor: eases to the card, presses on the tap, leaves. It never jumps more than 45 px per frame.
    const a = ev(t, 3.2, 1.5), x = lerp(1500, 1180, E.cubicInOut(a)), y = lerp(900, 640, E.cubicInOut(a)), press = Math.max(0, Math.sin(clamp((t - T.tap + 0.1) / 0.3) * Math.PI));
    const out = ev(t, T.wipe - 0.4, 0.4), orb = $('orb'); orb.style.opacity = clamp(ev(t, 3.2, 0.3)) * (1 - out);
    orb.style.transform = `translate(${x - 30}px,${y - 30}px) scale(${1 - 0.14 * press})`;
    // a lime wipe that grows from the tap: a scene change that has a cause
    const wp = ev(t, T.wipe - 0.3, 0.5), top = $('bg').getContext('2d');
    if (wp > 0 && wp < 1.05) { top.fillStyle = '#C9F23A'; top.beginPath(); top.arc(x, y, lerp(20, 2300, E.expoOut(wp)), 0, 7); top.fill(); }
    if (t > T.wipe + 0.2) { top.fillStyle = '#C9F23A'; top.globalAlpha = 1 - ev(t, T.end - 0.6, 0.6); top.fillRect(0, 0, 1920, 1080); top.globalAlpha = 1; }
  }
  EngineRuntime.defineScene({ fps: 60, duration: DUR, width: 1920, height: 1080, fonts: ['700 120px "Inter Tight"', '600 56px "Inter Tight"'], grain: { opacity: 0.03, cell: 2, seed: 7, blend: 'multiply' }, cues, beats, setup, render });
})();
