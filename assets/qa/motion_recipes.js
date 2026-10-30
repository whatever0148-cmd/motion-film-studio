/* motion_recipes.js: pure-function-of-time recipes that fit Engine A and lib.js (no state, no Date, no Math.random).
   Load after engine-runtime.js and lib.js; exposes window.MC (or module.exports in Node for tests).
   Every function takes t in seconds and returns a number or small object. Numbers trace to the dossier: ~/EmpireBrain/studio/brain/knowledge/motion-craft/dossier.md */
(function (root) {
  const clamp = (x, a = 0, b = 1) => Math.min(b, Math.max(a, x));
  const lerp = (a, b, u) => a + (b - a) * u;
  const seg = (t, a, b) => (b <= a ? (t >= b ? 1 : 0) : clamp((t - a) / (b - a)));

  /* ---- 1. state of a damped spring (position and velocity) in closed form. x goes from x0 toward target with initial velocity v0. */
  function springState(tau, x0, v0, target, k, c, m) {
    k = k == null ? 170 : k; c = c == null ? 26 : c; m = m == null ? 1 : m;
    if (tau <= 0) return { x: x0, v: v0 };
    const w0 = Math.sqrt(k / m), z = c / (2 * Math.sqrt(k * m)), d0 = x0 - target;
    let d, dv;
    if (z < 1) { const wd = w0 * Math.sqrt(1 - z * z), e = Math.exp(-z * w0 * tau), A = d0, B = (v0 + z * w0 * d0) / wd, cs = Math.cos(wd * tau), sn = Math.sin(wd * tau);
      d = e * (A * cs + B * sn); dv = e * ((-z * w0) * (A * cs + B * sn) + wd * (-A * sn + B * cs)); }
    else if (z === 1) { const e = Math.exp(-w0 * tau), B = v0 + w0 * d0; d = e * (d0 + B * tau); dv = e * (B - w0 * (d0 + B * tau)); }
    else { const s = Math.sqrt(z * z - 1), r1 = -w0 * (z - s), r2 = -w0 * (z + s), C2 = (v0 - r1 * d0) / (r2 - r1), C1 = d0 - C2; d = C1 * Math.exp(r1 * tau) + C2 * Math.exp(r2 * tau); dv = C1 * r1 * Math.exp(r1 * tau) + C2 * r2 * Math.exp(r2 * tau); }
    return { x: target + d, v: dv };
  }
  /* springChain: a value that chases a list of targets [{t, v}] and keeps its velocity when the target changes (no direction snap, no restart).
     Pure: replays the chain analytically from the first key. Use for a cursor, a camera, a counter, any thing whose goal moves.
     settle: below this distance (in value units) and speed the value is snapped to the target so the spring tail never crawls (0.25 px default). */
  function springChain(t, keys, opt) {
    opt = opt || {}; const k = opt.k, c = opt.c, m = opt.m, eps = opt.settle == null ? 0.25 : opt.settle;
    let x = keys[0].v, v = 0, tt = keys[0].t;
    if (t <= tt) return { x, v };
    for (let i = 0; i < keys.length; i++) {
      const tgt = keys[i].v, tEnd = i + 1 < keys.length ? keys[i + 1].t : Infinity, tau = Math.min(t, tEnd) - tt;
      const s = springState(tau, x, v, tgt, k, c, m);
      if (t < tEnd) { return (Math.abs(s.x - tgt) < eps && Math.abs(s.v) < eps * 4) ? { x: tgt, v: 0 } : s; }
      x = s.x; v = s.v; tt = tEnd;
    }
    return { x, v };
  }
  /* ---- 2. waypoints without stopping: monotone cubic Hermite (Fritsch-Carlson). C1 continuous, never overshoots a key, passes through at speed. keys: [{t, v}] */
  function waypoints(t, keys) {
    const n = keys.length; if (t <= keys[0].t) return keys[0].v; if (t >= keys[n - 1].t) return keys[n - 1].v;
    const d = [], m = [];
    for (let i = 0; i < n - 1; i++) d.push((keys[i + 1].v - keys[i].v) / (keys[i + 1].t - keys[i].t));
    m.push(0); for (let i = 1; i < n - 1; i++) m.push(d[i - 1] * d[i] <= 0 ? 0 : (d[i - 1] + d[i]) / 2); m.push(0);   // 0 slope at both ends = eased in and out
    for (let i = 0; i < n - 1; i++) { if (d[i] === 0) { m[i] = 0; m[i + 1] = 0; } else { const a = m[i] / d[i], b = m[i + 1] / d[i], h = Math.hypot(a, b); if (h > 3) { const s = 3 / h; m[i] = s * a * d[i]; m[i + 1] = s * b * d[i]; } } }
    let i = 0; while (t > keys[i + 1].t) i++;
    const h = keys[i + 1].t - keys[i].t, u = (t - keys[i].t) / h, u2 = u * u, u3 = u2 * u;
    return (2 * u3 - 3 * u2 + 1) * keys[i].v + (u3 - 2 * u2 + u) * h * m[i] + (-2 * u3 + 3 * u2) * keys[i + 1].v + (u3 - u2) * h * m[i + 1];
  }
  /* ---- 3. minimum-jerk ease (smootherstep): zero speed and acceleration at both ends, peak speed 1.875x average. Use for camera dollies and slow travel. */
  const minJerk = (u) => { u = clamp(u); return u * u * u * (u * (u * 6 - 15) + 10); };
  /* ---- 4. stagger: delay of item i of n. The step shrinks so the whole cascade never exceeds `cap` seconds (default 0.4 s), and never exceeds `step` (default 0.05 s). */
  function stagger(i, n, step, cap) { step = step == null ? 0.05 : step; cap = cap == null ? 0.4 : cap; return i * Math.min(step, n > 1 ? cap / (n - 1) : step); }
  /* ---- 5. overshoot budget: backOut constant s for a wanted overshoot fraction (10 % = 1.70158). Solves numerically; use instead of guessing s. */
  function backS(overshoot) { let lo = 0, hi = 8; for (let i = 0; i < 40; i++) { const s = (lo + hi) / 2; let p = 0; for (let u = 0; u <= 1; u += 0.002) { const q = u - 1; p = Math.max(p, 1 + (s + 1) * q * q * q + s * q * q); } if (p - 1 < overshoot) lo = s; else hi = s; } return (lo + hi) / 2; }
  /* ---- 6. idle float that is exactly zero at the moment a move starts and ends: multiply the idle by a window so there is no step when the idle begins. */
  const idle = (t, amp, period, phase, t0) => amp * Math.sin(2 * Math.PI * (t / period) + (phase || 0)) * seg(t, t0 || 0, (t0 || 0) + 0.5);
  /* ---- 7. synchronised group: derive every member from ONE progress value so siblings can never disagree on easing or duration. */
  const group = (t, t0, d, ease) => (i, n, lag) => ease(seg(t, t0 + stagger(i, n, lag == null ? 0.04 : lag), t0 + stagger(i, n, lag == null ? 0.04 : lag) + d));
  /* ---- 8. shutter: motion-blur streak length in px for a speed in px/s at 60 fps. Gaussian sigma that matches a box of that length is 0.29 x length. */
  const streak = (speedPxS, shutterDeg, fps) => speedPxS * ((shutterDeg == null ? 180 : shutterDeg) / 360) / (fps || 60);
  const blurSigma = (lenPx) => 0.2887 * lenPx;
  /* ---- 9. dither: triangular noise of +-amp code values, new every frame, for canvas gradients. Call after drawing the gradient. rng is EngineRuntime.rng(seed). */
  function dither(ctx, w, h, rng, amp) {
    amp = amp == null ? 1 : amp; const im = ctx.getImageData(0, 0, w, h), d = im.data;
    for (let i = 0; i < d.length; i += 4) { const n = Math.round((rng() + rng() - 1) * amp); d[i] += n; d[i + 1] += n; d[i + 2] += n; }
    ctx.putImageData(im, 0, 0);
  }
  const API = { clamp, lerp, seg, springState, springChain, waypoints, minJerk, stagger, backS, idle, group, streak, blurSigma, dither };
  if (typeof module !== 'undefined' && module.exports) module.exports = API; else root.MC = API;
})(typeof window !== 'undefined' ? window : globalThis);
