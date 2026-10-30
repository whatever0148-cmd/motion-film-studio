/*
 * engine-runtime.js  (Engine A browser runtime, no build step)
 *
 * Load with:  <script src="/direct-engine/runtime/engine-runtime.js"></script>
 * Defines window.EngineRuntime. EngineRuntime.defineScene(...) wires the
 * globals the renderer reads (CONTRACT.md section 2):
 *   window.__scene, __ready, __renderFrame(frame, fps), __safeBoxes(), __cues, __beats
 *
 * Rules this file follows so every frame is a pure function of t = frame / fps:
 *   no Date.now, no performance.now, no unseeded Math.random, no rAF loops.
 */
(function (global) {
  'use strict';

  // ---------------------------------------------------------------- RNG
  // mulberry32: tiny, fast, good enough for visuals. Returns floats in [0, 1).
  function rng(seed) {
    let a = (seed >>> 0) || 0x9e3779b9;
    const next = function () {
      a = (a + 0x6d2b79f5) >>> 0;
      let t = a;
      t = Math.imul(t ^ (t >>> 15), t | 1);
      t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
    next.range = (lo, hi) => lo + (hi - lo) * next();
    next.int = (lo, hi) => Math.floor(lo + (hi - lo + 1) * next());
    next.pick = (arr) => arr[Math.floor(next() * arr.length)];
    // Box-Muller normal(0, 1)
    next.gauss = () => {
      let u = 0;
      while (u === 0) u = next();
      const v = next();
      return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v);
    };
    return next;
  }

  // Stable 32-bit hash of a string, for deriving seeds from ids.
  function hashSeed(str) {
    let h = 2166136261 >>> 0;
    for (let i = 0; i < str.length; i++) {
      h ^= str.charCodeAt(i);
      h = Math.imul(h, 16777619);
    }
    return h >>> 0;
  }

  // ---------------------------------------------------------------- math
  const clamp = (x, lo = 0, hi = 1) => (x < lo ? lo : x > hi ? hi : x);
  const lerp = (a, b, t) => a + (b - a) * t;
  const invLerp = (a, b, x) => (a === b ? 0 : (x - a) / (b - a));
  const mapRange = (x, inA, inB, outA, outB, doClamp = true) => {
    let p = invLerp(inA, inB, x);
    if (doClamp) p = clamp(p);
    return lerp(outA, outB, p);
  };
  // Normalised progress of t through the window [a, b], clamped to 0..1.
  const seg = (t, a, b) => (b <= a ? (t >= b ? 1 : 0) : clamp((t - a) / (b - a)));

  // ---------------------------------------------------------------- easing
  const expoOut = (t) => (t >= 1 ? 1 : 1 - Math.pow(2, -10 * clamp(t)));
  const expoIn = (t) => (t <= 0 ? 0 : Math.pow(2, 10 * clamp(t) - 10));
  const expoInOut = (t) => {
    t = clamp(t);
    if (t === 0 || t === 1) return t;
    return t < 0.5 ? Math.pow(2, 20 * t - 10) / 2 : (2 - Math.pow(2, -20 * t + 10)) / 2;
  };
  const backOut = (t, s = 1.70158) => {
    const u = clamp(t) - 1;
    return 1 + (s + 1) * u * u * u + s * u * u;
  };
  const cubicOut = (t) => 1 - Math.pow(1 - clamp(t), 3);
  const cubicInOut = (t) => {
    t = clamp(t);
    return t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
  };

  /*
   * Analytic damped spring. Position goes 0 -> 1 (the target).
   * opts: {stiffness=170, damping=26, mass=1, velocity=0}
   *   velocity is the initial speed toward the target in units per second.
   * Returns position at time t (seconds). Closed form, no integration, so it is
   * exact for any t and safe to call out of order.
   */
  function spring(t, opts) {
    const o = opts || {};
    const k = o.stiffness != null ? o.stiffness : 170;
    const c = o.damping != null ? o.damping : 26;
    const m = o.mass != null ? o.mass : 1;
    const v0 = o.velocity != null ? o.velocity : 0;
    if (t <= 0) return 0;
    const w0 = Math.sqrt(k / m);
    const zeta = c / (2 * Math.sqrt(k * m));
    const d0 = 1; // displacement from target at t=0
    const dv0 = -v0; // derivative of displacement at t=0
    let d;
    if (zeta < 1) {
      const wd = w0 * Math.sqrt(1 - zeta * zeta);
      d = Math.exp(-zeta * w0 * t) * (d0 * Math.cos(wd * t) + ((dv0 + zeta * w0 * d0) / wd) * Math.sin(wd * t));
    } else if (zeta === 1) {
      d = Math.exp(-w0 * t) * (d0 + (dv0 + w0 * d0) * t);
    } else {
      const s = Math.sqrt(zeta * zeta - 1);
      const r1 = -w0 * (zeta - s);
      const r2 = -w0 * (zeta + s);
      const C2 = (dv0 - r1 * d0) / (r2 - r1);
      const C1 = d0 - C2;
      d = C1 * Math.exp(r1 * t) + C2 * Math.exp(r2 * t);
    }
    return 1 - d;
  }

  // Time (s) after which |position - 1| stays below eps. Found by scanning the envelope.
  function springSettleTime(opts, eps = 0.001) {
    const step = 1 / 240;
    let last = 0;
    for (let t = 0; t < 30; t += step) {
      if (Math.abs(1 - spring(t, opts)) > eps) last = t;
      else if (t - last > 0.25) return last + step;
    }
    return 30;
  }

  // Spring as a 0..1 ease for GSAP or seg(): progress p maps to spring time p * duration.
  // If duration is omitted the spring's own settle time is used. ease(1) === 1 exactly.
  function springEase(opts, duration) {
    const dur = duration != null ? duration : springSettleTime(opts);
    return (p) => (p >= 1 ? 1 : p <= 0 ? 0 : spring(p * dur, opts));
  }

  /*
   * Cubic bezier ease, same maths as CSS cubic-bezier(x1, y1, x2, y2).
   * Newton-Raphson with a bisection fallback (as in WebKit's UnitBezier).
   */
  function cubicBezier(x1, y1, x2, y2) {
    const cx = 3 * x1, bx = 3 * (x2 - x1) - cx, ax = 1 - cx - bx;
    const cy = 3 * y1, by = 3 * (y2 - y1) - cy, ay = 1 - cy - by;
    const sx = (u) => ((ax * u + bx) * u + cx) * u;
    const sy = (u) => ((ay * u + by) * u + cy) * u;
    const dsx = (u) => (3 * ax * u + 2 * bx) * u + cx;
    function solveX(x) {
      let u = x;
      for (let i = 0; i < 8; i++) {
        const e = sx(u) - x;
        if (Math.abs(e) < 1e-7) return u;
        const d = dsx(u);
        if (Math.abs(d) < 1e-6) break;
        u -= e / d;
      }
      let lo = 0, hi = 1;
      u = x;
      for (let i = 0; i < 40; i++) {
        const v = sx(u);
        if (Math.abs(v - x) < 1e-7) return u;
        if (x > v) lo = u; else hi = u;
        u = (lo + hi) / 2;
      }
      return u;
    }
    return (t) => (t <= 0 ? 0 : t >= 1 ? 1 : sy(solveX(t)));
  }

  // ---------------------------------------------------------------- box registry
  // Canvas-drawn text or hero shapes that QA must see. Cleared at the start of every frame.
  let registry = [];
  function registerBox(box) {
    if (!box) return;
    const b = {
      id: String(box.id || 'canvas-' + registry.length),
      kind: box.kind || 'text',
      x: +box.x || 0, y: +box.y || 0, w: +box.w || 0, h: +box.h || 0,
      fontPx: box.fontPx != null ? +box.fontPx : null,
      source: 'canvas',
    };
    if (box.opacity != null && box.opacity < 0.05) return;
    registry.push(b);
  }
  function clearBoxes() { registry = []; }

  function effectiveOpacity(el) {
    let op = 1;
    for (let n = el; n && n.nodeType === 1; n = n.parentElement) {
      const cs = getComputedStyle(n);
      if (cs.display === 'none') return 0;
      op *= parseFloat(cs.opacity);
      if (op < 0.001) return 0;
    }
    return op;
  }

  // Product of 2D transform scales on the element and its ancestors (informational).
  function effectiveScale(el) {
    let s = 1;
    for (let n = el; n && n.nodeType === 1; n = n.parentElement) {
      const tr = getComputedStyle(n).transform;
      if (tr && tr !== 'none') {
        try {
          const m = new DOMMatrixReadOnly(tr);
          s *= Math.sqrt(Math.abs(m.a * m.d - m.b * m.c));
        } catch (e) { /* ignore */ }
      }
    }
    return s;
  }

  // Smallest computed font-size among elements under el that directly hold visible text.
  function minTextFont(el) {
    let min = Infinity;
    const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
    let node;
    while ((node = walker.nextNode())) {
      if (!node.nodeValue || !node.nodeValue.trim()) continue;
      const host = node.parentElement;
      if (!host) continue;
      const cs = getComputedStyle(host);
      if (cs.display === 'none' || cs.visibility === 'hidden') continue;
      const fs = parseFloat(cs.fontSize);
      if (fs < min) min = fs;
    }
    if (min === Infinity) min = parseFloat(getComputedStyle(el).fontSize);
    return min;
  }

  const r1 = (v) => Math.round(v * 10) / 10;

  // Union of the painted glyph boxes of every visible, non-blank text node under el
  // (transforms included). Block wrappers and whitespace do not widen the box.
  function textRect(el) {
    let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
    const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
    const range = document.createRange();
    let node;
    while ((node = walker.nextNode())) {
      if (!node.nodeValue || !node.nodeValue.trim()) continue;
      const host = node.parentElement;
      if (host && effectiveOpacity(host) < 0.05) continue;
      range.selectNodeContents(node);
      for (const q of range.getClientRects()) {
        if (q.width < 0.5 || q.height < 0.5) continue;
        if (q.left < x0) x0 = q.left;
        if (q.top < y0) y0 = q.top;
        if (q.right > x1) x1 = q.right;
        if (q.bottom > y1) y1 = q.bottom;
      }
    }
    if (x0 === Infinity) return null;
    return { left: x0, top: y0, width: x1 - x0, height: y1 - y0 };
  }

  /*
   * safeBoxes(): every visible [data-safe="text|hero|ui"] element plus registered canvas boxes.
   *   x, y, w, h  CSS px of the painted box (transforms included). For text this is the union
   *               of the glyph line boxes (a Range over the contents), not the block width.
   *   fontPx      design type size: smallest computed font-size of the text inside (CSS px,
   *               before transforms). scale holds the transform scale for reference.
   * Elements whose effective opacity (through ancestors) is below 0.05 are left out.
   */
  function safeBoxes() {
    const out = [];
    const els = document.querySelectorAll('[data-safe]');
    els.forEach((el, i) => {
      const kind = el.getAttribute('data-safe');
      if (kind !== 'text' && kind !== 'hero' && kind !== 'ui') return;
      const cs = getComputedStyle(el);
      if (cs.visibility === 'hidden') return;
      const op = effectiveOpacity(el);
      if (op < 0.05) return;
      let r = null;
      if (kind === 'text') {
        r = textRect(el);
        if (!r) return; // no visible glyphs this frame
      }
      if (!r) r = el.getBoundingClientRect();
      if (r.width < 0.5 || r.height < 0.5) return;
      out.push({
        id: el.id || el.getAttribute('data-safe-id') || kind + '-' + i,
        kind,
        x: r1(r.left), y: r1(r.top), w: r1(r.width), h: r1(r.height),
        fontPx: kind === 'text' ? r1(minTextFont(el)) : r1(parseFloat(cs.fontSize)),
        scale: Math.round(effectiveScale(el) * 1000) / 1000,
        opacity: Math.round(op * 1000) / 1000,
        source: 'dom',
      });
    });
    for (const b of registry) out.push(Object.assign({}, b, { x: r1(b.x), y: r1(b.y), w: r1(b.w), h: r1(b.h) }));
    return out;
  }

  // ---------------------------------------------------------------- film grain
  /*
   * grain({opacity=0.08, cell=2, seed=7, blend='overlay', zIndex=9000})
   * Adds a full-frame canvas overlay. Its noise is re-drawn from rng(seed, frame) on every
   * __renderFrame, so it is deterministic. cell = size of one grain cell in CSS px.
   */
  let grainState = null;
  function grain(opts) {
    const o = Object.assign({ opacity: 0.08, cell: 2, seed: 7, blend: 'overlay', zIndex: 9000, parent: null }, opts || {});
    const sc = global.__scene || { width: 1080, height: 1920 };
    const cw = Math.max(1, Math.round(sc.width / o.cell));
    const ch = Math.max(1, Math.round(sc.height / o.cell));
    const cv = document.createElement('canvas');
    cv.width = cw; cv.height = ch;
    cv.className = 'engine-grain';
    Object.assign(cv.style, {
      position: 'absolute', left: '0px', top: '0px', width: sc.width + 'px', height: sc.height + 'px',
      pointerEvents: 'none', mixBlendMode: o.blend, opacity: String(o.opacity), zIndex: String(o.zIndex),
    });
    (o.parent || document.body).appendChild(cv);
    const ctx = cv.getContext('2d');
    const img = ctx.createImageData(cw, ch);
    grainState = { cv, ctx, img, seed: o.seed, opts: o };
    return {
      canvas: cv,
      setOpacity: (v) => { cv.style.opacity = String(v); },
      draw: (frame) => drawGrain(frame),
    };
  }
  function drawGrain(frame) {
    if (!grainState) return;
    const { ctx, img, seed } = grainState;
    const r = rng((seed * 2654435761 + frame * 40503 + 1) >>> 0);
    const d = img.data;
    for (let i = 0; i < d.length; i += 4) {
      // triangular distribution around mid-grey, overlay-neutral at 128
      const v = 128 + ((r() + r() - 1) * 110) | 0;
      d[i] = d[i + 1] = d[i + 2] = v;
      d[i + 3] = 255;
    }
    ctx.putImageData(img, 0, 0);
  }

  // ---------------------------------------------------------------- fonts / images
  // Loads every declared @font-face that covers basic Latin, plus any explicit specs.
  async function loadFonts(specs) {
    const jobs = [];
    if (document.fonts && document.fonts.forEach) {
      document.fonts.forEach((ff) => {
        const ur = (ff.unicodeRange || '').toUpperCase();
        const latin = !ur || ur === 'U+0-10FFFF' || /U\+0000-00FF|U\+0-FF\b|U\+0020-007F/.test(ur);
        if (latin && ff.status === 'unloaded') jobs.push(ff.load().catch((e) => console.error('[engine] font failed', ff.family, e && e.message)));
      });
    }
    for (const s of specs || []) jobs.push(document.fonts.load(s).catch((e) => console.error('[engine] font spec failed', s, e && e.message)));
    await Promise.all(jobs);
    await document.fonts.ready;
  }

  async function imagesReady() {
    const imgs = Array.from(document.images || []);
    await Promise.all(imgs.map((img) => (img.complete ? (img.decode ? img.decode().catch(() => {}) : null) : new Promise((res) => {
      img.addEventListener('load', res, { once: true });
      img.addEventListener('error', () => { console.error('[engine] image failed', img.src); res(); }, { once: true });
    }))));
  }

  function domReady() {
    if (document.readyState !== 'loading') return Promise.resolve();
    return new Promise((r) => document.addEventListener('DOMContentLoaded', r, { once: true }));
  }

  // ---------------------------------------------------------------- scene wiring
  /*
   * defineScene({fps, duration, width, height, setup, render, cues, beats, fonts, grain})
   *   setup:  async () => {}   build DOM / WebGL, load assets. Runs once, before __ready resolves.
   *   render: (t, frame, fps) => {}  put the page in the state for time t. May return a Promise.
   *   cues:   [{t, type, gain?, pan?, dur?}]   sound design cues
   *   beats:  [{t, kind}]                    retention beats for QA
   *   fonts:  ['800 120px "Inter Tight"', ...] extra font specs to force-load
   *   grain:  {opacity, cell, seed, blend} or false
   */
  function defineScene(cfg) {
    if (!cfg || typeof cfg.render !== 'function') throw new Error('defineScene needs a render(t, frame) function');
    const scene = {
      fps: cfg.fps || 60,
      duration: cfg.duration,
      width: cfg.width || 1080,
      height: cfg.height || 1920,
    };
    if (!(scene.duration > 0)) throw new Error('defineScene needs duration > 0 (seconds)');
    global.__scene = scene;
    global.__cues = Array.isArray(cfg.cues) ? cfg.cues.slice() : [];
    global.__beats = Array.isArray(cfg.beats) ? cfg.beats.slice() : [];
    global.__engineErrors = [];

    let lastFrame = -1;
    global.__ready = (async () => {
      await domReady();
      await loadFonts(cfg.fonts);
      if (cfg.grain) grain(cfg.grain);
      if (typeof cfg.setup === 'function') await cfg.setup();
      await imagesReady();
      await document.fonts.ready;
      return scene;
    })();
    global.__ready.catch((e) => {
      global.__engineErrors.push(String(e && e.stack || e));
      console.error('[engine] scene setup failed: ' + (e && e.stack || e));
    });

    global.__renderFrame = async (frame, fps) => {
      await global.__ready;
      const f = fps || scene.fps;
      const t = frame / f;
      clearBoxes();
      await cfg.render(t, frame, f);
      if (grainState) drawGrain(frame);
      lastFrame = frame;
      return { frame, t };
    };
    global.__safeBoxes = () => safeBoxes();
    global.__lastFrame = () => lastFrame;
    return scene;
  }

  global.EngineRuntime = {
    version: '1.0.0',
    rng, hashSeed,
    clamp, lerp, invLerp, mapRange, seg,
    ease: { expoOut, expoIn, expoInOut, backOut, cubicOut, cubicInOut, linear: (t) => clamp(t) },
    expoOut, backOut,
    spring, springEase, springSettleTime, cubicBezier,
    registerBox, clearBoxes, safeBoxes, effectiveOpacity,
    grain, drawGrain,
    loadFonts,
    defineScene,
  };
})(window);
