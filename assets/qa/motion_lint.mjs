#!/usr/bin/env node
// motion_lint.mjs: the "weird animation lint". Reads series from sample_scene.mjs (or any {series:[{id,cls,text,hasText,frames,x,y,w,h,op,blur}], fps}).
// It looks at numbers only (position, size, opacity, blur per frame). It cannot judge taste; it finds what makes motion look broken.
// Usage: node motion_lint.mjs series.json [--max-overshoot 0.12] [--movers 4] [--ignore "bokeh|star"] [--json out.json] [--all]
import fs from 'node:fs';
const argv = process.argv.slice(2); const file = argv.find((a) => !a.startsWith('--'));
const O = { 'max-overshoot': 0.12, movers: 4, ignore: '', hold: 1.4 }; for (let i = 0; i < argv.length; i++) if (argv[i] === '--all') O.all = true; else if (argv[i].startsWith('--') && argv[i + 1] && !argv[i + 1].startsWith('--')) O[argv[i].slice(2)] = argv[++i];
if (!file) { console.error('usage: node motion_lint.mjs series.json'); process.exit(2); }
const doc = JSON.parse(fs.readFileSync(file, 'utf8')); const fps = doc.fps || 60, step = doc.step || 1;
const ign = O.ignore ? new RegExp(O.ignore, 'i') : null; const maxOv = +O['max-overshoot'];
const F = []; // findings
const T = (f) => +(f / fps).toFixed(2);
const add = (id, sev, s, f0, f1, msg, val) => F.push({ id, sev, el: label(s), t0: T(f0), t1: T(f1), msg, val });
const label = (s) => (s.id ? '#' + s.id : '') + (s.cls ? '.' + String(s.cls).trim().split(/\s+/).join('.') : '') + (s.text ? ` "${s.text}"` : '') + ` [${s.i}]`;
const sgn = (x, e = 0) => (x > e ? 1 : x < -e ? -1 : 0);
const median = (a) => { if (!a.length) return 0; const b = [...a].sort((x, y) => x - y); return b[b.length >> 1]; };

// split a series into runs of consecutive sampled frames (display none breaks a run)
function runs(s) { const out = []; let a = 0; const vis = (k) => s.op[k] >= 0.02; for (let k = 1; k <= s.frames.length; k++) if (k === s.frames.length || s.frames[k] - s.frames[k - 1] !== step || vis(k) !== vis(k - 1)) { if (k - a >= 4 && vis(a)) out.push([a, k]); a = k; } return out; }
const per = (1 / step); // samples per frame, for velocity in px per frame
const SPEEDS = []; // for the mover count: {frame -> [{vx,vy,area,i}]}
const moverAt = new Map();

for (const s of doc.series) {
  if (ign && ign.test(`${s.id} ${s.cls} ${s.text}`)) continue;
  const rs = runs(s);
  // pop-in: first visible frame of a run (not the first sample of the film) already visible and large
  for (const [a, b] of rs) {
    const f0 = s.frames[a];
    if (a === 0 && f0 > (doc.from || 0)) {} // element became visible after display:none
    const area = s.w[a] * s.h[a];
    if (f0 > (doc.from || 0) + step && s.op[a] > 0.35 && area > 120 * 120 && s.frames[a] - (a ? s.frames[a - 1] : -99) !== step) add('W10', 'P2', s, f0, f0, `appears in one frame at opacity ${s.op[a].toFixed(2)} (hard pop-in of a ${Math.round(s.w[a])}x${Math.round(s.h[a])} px element; fine only as a declared hard cut)`, s.op[a]);
    const n = b - a;
    const cx = [], cy = [], op = s.op.slice(a, b), bl = s.blur.slice(a, b), w = s.w.slice(a, b), h = s.h.slice(a, b);
    for (let k = a; k < b; k++) { cx.push(s.x[k] + s.w[k] / 2); cy.push(s.y[k] + s.h[k] / 2); }
    const vx = [0], vy = [0], sp = [0];
    for (let k = 1; k < n; k++) { vx.push((cx[k] - cx[k - 1]) * per); vy.push((cy[k] - cy[k - 1]) * per); sp.push(Math.hypot(vx[k], vy[k])); }
    const fr = (k) => s.frames[a + k];
    // record movers for the simultaneity check
    for (let k = 1; k < n; k++) if (sp[k] > 3 && s.w[a + k] * s.h[a + k] >= 3600 && op[k] > 0.2) { const key = fr(k); if (!moverAt.has(key)) moverAt.set(key, []); moverAt.get(key).push({ vx: vx[k], vy: vy[k], i: s.i }); }
    // W01 teleport: a one-frame jump that its neighbours do not share
    for (let k = 2; k < n - 2; k++) {
      const nb = median([sp[k - 2], sp[k - 1], sp[k + 1], sp[k + 2]]);
      if (sp[k] > 60 && sp[k] > 8 * (nb + 1) && sp[k - 1] < 0.4 * sp[k] && sp[k + 1] < 0.4 * sp[k]) add('W01', (op[k] > 0.5 && s.w[a + k] * s.h[a + k] >= 900) ? 'P0' : 'P1', s, fr(k - 1), fr(k), `one-frame jump of ${sp[k].toFixed(0)} px while the frames around it move ${nb.toFixed(1)} px`, sp[k]);
    }
    // W14 opacity: one-frame jump, and flash (up and down within 4 frames)
    for (let k = 1; k < n; k++) {
      const d = op[k] - op[k - 1];
      if (Math.abs(d) > 0.45 && s.w[a + k] * s.h[a + k] > 200 * 200) {
        const back = k + 3 < n ? op.slice(k + 1, k + 4).some((v) => Math.abs(v - op[k - 1]) < 0.12) : false;
        add(back ? 'W14' : 'W10', back ? 'P0' : 'P2', s, fr(k - 1), fr(k), back ? `opacity flash: ${op[k - 1].toFixed(2)} to ${op[k].toFixed(2)} and back within 4 frames` : `opacity jumps ${op[k - 1].toFixed(2)} to ${op[k].toFixed(2)} in one frame on a large element`, d);
      }
      if (Math.abs(bl[k] - bl[k - 1]) > 6) add('W15', 'P1', s, fr(k - 1), fr(k), `blur radius jumps ${bl[k - 1]} to ${bl[k]} px in one frame (blur pop)`, bl[k] - bl[k - 1]);
      const dw = Math.abs(w[k] - w[k - 1]) / Math.max(1, w[k - 1]), dh = Math.abs(h[k] - h[k - 1]) / Math.max(1, h[k - 1]);
      if (Math.max(dw, dh) > 0.5 && w[k] * h[k] > 200 * 200 && op[k] > 0.3 && op[k - 1] > 0.3) add('W01', 'P1', s, fr(k - 1), fr(k), `size changes ${(100 * Math.max(dw, dh)).toFixed(0)} % in one frame while visible`, Math.max(dw, dh));
    }
    // moves: runs where speed > 0.6 px/frame
    let k = 1;
    while (k < n) {
      if (sp[k] <= 0.6) { k++; continue; }
      let e = k; let still = 0;
      while (e < n && still < 4) { if (sp[e] <= 0.6) still++; else still = 0; e++; }
      e -= still; if (e <= k) { k = e + 1; continue; }
      const seg = sp.slice(k, e), peak = Math.max(...seg), dur = e - k;
      const x0 = cx[k - 1], y0 = cy[k - 1], x1 = cx[e - 1], y1 = cy[e - 1], D = Math.hypot(x1 - x0, y1 - y0);
      const rest = e + 6 <= n ? true : false;
      const visible = Math.min(...op.slice(k - 1, e)) > 0.9;
      if (D > 25 && dur >= 4) {
        const ux = (x1 - x0) / D, uy = (y1 - y0) / D;
        // W04 overshoot (along the travel axis) when the move ends at rest
        if (rest) {
          let ex = 0; for (let m = k - 1; m < Math.min(n, e + 24); m++) ex = Math.max(ex, (cx[m] - x1) * ux + (cy[m] - y1) * uy);
          const tail = []; for (let m = e; m < Math.min(n, e + 24); m++) tail.push(Math.hypot(cx[m] - x1, cy[m] - y1));
          const final = tail.length ? [cx[Math.min(n - 1, e + 12)], cy[Math.min(n - 1, e + 12)]] : [x1, y1];
          const D2 = Math.hypot(final[0] - x0, final[1] - y0);
          let ov = 0; for (let m = k - 1; m < Math.min(n, e + 24); m++) ov = Math.max(ov, ((cx[m] - final[0]) * (final[0] - x0) + (cy[m] - final[1]) * (final[1] - y0)) / (D2 || 1));
          if (D2 > 25 && ov / D2 > maxOv) add('W04', s.hasText ? 'P1' : 'P2', s, fr(k), fr(Math.min(n - 1, e + 24)), `overshoot ${(100 * ov / D2).toFixed(0)} % of a ${D2.toFixed(0)} px move (limit ${(100 * maxOv).toFixed(0)} %)`, ov / D2);
        }
        // W03 reversals along travel while moving: count sign changes of the along-travel velocity
        let rev = 0, lastS = 0, pos = 0, ext = 0, lastExt = 0; const alongV = []; for (let m = k; m < Math.min(n, e + 24); m++) alongV.push(vx[m] * ux + vy[m] * uy);
        // a reversal counts when the along-travel velocity flips sign with at least 0.5 px/frame on both sides and the back-swing is at least 1.5 px
        let swing = 0; for (let m = 0; m < alongV.length; m++) { const sg = sgn(alongV[m], 0.5); if (sg && lastS && sg !== lastS) { if (Math.abs(swing) >= 1.5) rev++; swing = 0; } if (sg) lastS = sg; swing += alongV[m]; }
        if (rev >= 3) add('W03', 'P1', s, fr(k), fr(Math.min(n - 1, e + 24)), `ringing: direction reverses ${rev} times in one move (springs under-damped, or two tweens fight)`, rev);
        // W02 velocity kink inside a move
        const da = []; for (let m = k + 1; m < e; m++) da.push(Math.hypot(vx[m] - vx[m - 1], vy[m] - vy[m - 1]));
        const md = median(da);
        for (let m = k + 3; m < e - 3; m++) { const d = da[m - k - 1]; if (d > 4 * md + 3 && d > 0.3 * peak && sp[m] > 2 && sp[m - 1] > 3) { add('W02', 'P1', s, fr(m - 1), fr(m + 1), `velocity kink: speed changes ${d.toFixed(1)} px/frame in one step (typical ${md.toFixed(2)}); two eases joined without matching speed`, d); break; } }
        // W06 hard start: a fully visible element leaves rest at more than 10 px/frame in its first moving frame (no anticipation)
        if (visible && sp[k] > 10 && sp[k - 1] < 0.6 && dur >= 6) add('W06', 'P2', s, fr(k - 1), fr(k + 1), `takes off at ${sp[k].toFixed(1)} px/frame from rest while fully visible (no anticipation or ramp); fine for an entrance that fades in`, sp[k]);
        // W05 hard stop (arrives at speed then stops dead)
        if (rest && dur >= 6 && sp[e - 1] / peak > 0.3 && sp[e - 1] > 3 && visible) add('W05', 'P1', s, fr(e - 2), fr(e), `stops dead: last-frame speed ${sp[e - 1].toFixed(1)} px/frame is ${(100 * sp[e - 1] / peak).toFixed(0)} % of peak`, sp[e - 1] / peak);
        // W07 linear
        if (dur >= 18 && D > 100 && peak > 2) { const ms = median(seg); const near = seg.filter((v) => Math.abs(v - ms) < 0.1 * ms).length / seg.length; if (near > 0.7) add('W07', 'P1', s, fr(k), fr(e), `linear: ${(100 * near).toFixed(0)} % of frames within 10 % of one speed over ${(dur / fps).toFixed(2)} s (robotic; ambient drift under 90 px/s is exempt)`, near); }
        // W09 too fast to read
        const bmax = Math.max(...bl.slice(k - 1, e));
        if (peak > 45 && bmax < 3 && s.w[a + k] * s.h[a + k] > 40 * 40 && Math.max(...op.slice(k - 1, e)) > 0.4) add('W09', peak > 110 ? 'P1' : 'P2', s, fr(k), fr(e), `${peak.toFixed(0)} px/frame (${(peak * fps).toFixed(0)} px/s) with blur under 3 px: strobing, the eye sees a jump (add blur along the path or slow down)`, peak);
        if (s.hasText && peak > 28 && Math.max(...op.slice(k - 1, e)) > 0.6 && (s.fontPx || 0) >= 20) add('W09', 'P2', s, fr(k), fr(e), `text moves ${peak.toFixed(0)} px/frame; unreadable while moving, keep type under about 25 px/frame unless it is a smear on purpose`, peak);
      }
      k = e + 1;
    }
    // W08 text at rest: micro jitter, and slow crawl
    if (s.hasText) {
      let m = 0;
      while (m < n - 20) {
        let e2 = m; while (e2 < n && sp[e2] < 0.5) e2++;
        if (e2 - m >= 20) {
          const xs = cx.slice(m, e2), ys = cy.slice(m, e2); let flips = 0, ls = 0; for (let q = 1; q < xs.length; q++) { const sg = sgn(xs[q] - xs[q - 1], 0.004) || sgn(ys[q] - ys[q - 1], 0.004); if (sg && ls && sg !== ls) flips++; if (sg) ls = sg; }
          const rngx = Math.max(...xs) - Math.min(...xs), rngy = Math.max(...ys) - Math.min(...ys), r = Math.max(rngx, rngy);
          if (flips >= 4 && r > 0.04 && r < 2) add('W08', 'P1', s, fr(m), fr(e2 - 1), `text jitters ${r.toFixed(2)} px with ${flips} direction flips while "at rest" (idle float plus snap, or competing transforms); shimmer in the video`, r);
        }
        m = e2 + 1;
      }
    }
  }
}
// W12 too many independent things moving at once: cluster movers by velocity
const hot = []; for (const [f, arr] of [...moverAt.entries()].sort((a, b) => a[0] - b[0])) { const cl = new Set(arr.map((m) => Math.round(m.vx / 3) + ',' + Math.round(m.vy / 3))); if (cl.size > +O.movers) hot.push([f, cl.size]); }
if (hot.length) { let a = hot[0][0], b = a, mx = hot[0][1]; const flush = () => F.push({ id: 'W12', sev: (b - a) / fps > 0.5 ? 'P1' : 'P2', el: 'frame', t0: T(a), t1: T(b), msg: `up to ${mx} independent large movers at once (limit ${O.movers}); one focal point is lost`, val: mx }); for (let q = 1; q < hot.length; q++) { if (hot[q][0] - b <= step * 3) { b = hot[q][0]; mx = Math.max(mx, hot[q][1]); } else { flush(); a = b = hot[q][0]; mx = hot[q][1]; } } flush(); }
// W13 dead hold: no large mover and no opacity change for longer than --hold seconds
{ const from = doc.from || 0, to = doc.to || 0; const act = new Set([...moverAt.keys()]); let run = 0, start = from; for (let f = from; f < to; f += step) { if (act.has(f)) { if (run / fps > +O.hold) F.push({ id: 'W13', sev: 'P2', el: 'frame', t0: T(start), t1: T(f), msg: `no large element moves for ${(run / fps).toFixed(1)} s (hold limit ${O.hold} s; check micro-motion, see video-flaw-scanner F06)`, val: run / fps }); run = 0; start = f; } else run += step; } }
// merge: same rule at the same moment on several elements is ONE event (a card and its children, a cursor and its ghosts)
const order = { P0: 0, P1: 1, P2: 2 };
const groups = new Map();
for (const f of F) { const k = f.id + '|' + Math.round(f.t0 * 10); const g = groups.get(k); if (!g) groups.set(k, { ...f, n: 1, els: [f.el] }); else { g.n++; g.els.push(f.el); if (order[f.sev] < order[g.sev]) g.sev = f.sev; if (Math.abs(f.val) > Math.abs(g.val)) { g.val = f.val; g.msg = f.msg; } } }
const out = [...groups.values()].map((g) => ({ ...g, el: g.n > 1 ? `${g.els[0].slice(0, 30)} +${g.n - 1} more` : g.els[0] })).sort((a, b) => a.t0 - b.t0);
const sev = { P0: 0, P1: 0, P2: 0 }; out.forEach((f) => sev[f.sev]++);
const byRule = {}; out.forEach((f) => { byRule[f.id] = byRule[f.id] || { P0: 0, P1: 0, P2: 0 }; byRule[f.id][f.sev]++; });
const show = O.all ? out : out.filter((f) => f.sev !== 'P2').slice(0, 60);
for (const f of show) console.log(`${f.sev} ${f.id} ${String(f.t0).padStart(6)}-${String(f.t1).padEnd(6)} ${f.el.slice(0, 44).padEnd(44)} ${f.msg}`);
if (out.length > show.length) console.log(`... ${out.length - show.length} more events (P2 hidden or over 60; use --all)`);
console.log('\nby rule:', Object.entries(byRule).sort().map(([k, v]) => `${k} P0:${v.P0} P1:${v.P1} P2:${v.P2}`).join(' | '));
console.log(`SUMMARY events P0=${sev.P0} P1=${sev.P1} P2=${sev.P2}  elements=${doc.series.length} frames=${doc.from}..${doc.to}  verdict=${sev.P0 ? 'FAIL' : sev.P1 ? 'REVIEW (fix or waive each P1 with a reason)' : 'PASS'}`);
if (O.json) fs.writeFileSync(O.json, JSON.stringify({ summary: sev, byRule, findings: out }, null, 1));
process.exit(sev.P0 ? 1 : 0);
