#!/usr/bin/env node
// sample_scene.mjs: step an Engine A scene frame by frame and record how every animated element moves.
// Read-only: loads the scene in headless Chrome through a local static server, calls window.__renderFrame(frame, fps),
// and writes one JSON series per element: x,y,w,h (stage px, through every transform), opacity, blur (px), scale-ish.
// Usage: node sample_scene.mjs --scene ~/EmpireBrain/studio/reels/<slug>/scene/index.html --from 0 --to 600 [--step 1] [--out series.json] [--sel "#stage *"]
// Then:  node motion_lint.mjs series.json
import fs from 'node:fs'; import fsp from 'node:fs/promises'; import http from 'node:http'; import os from 'node:os'; import path from 'node:path';
import { createRequire } from 'node:module';
const STUDIO = process.env.MOTION_STUDIO || path.resolve(path.dirname(new URL(import.meta.url).pathname), '..');   // the workspace root (qa/ sits beside direct-engine/)
const require = createRequire(path.join(STUDIO, 'direct-engine/package.json'));
const puppeteer = require('puppeteer-core');
const A = {}; for (let i = 2; i < process.argv.length; i += 2) A[process.argv[i].replace(/^--/, '')] = process.argv[i + 1];
if (!A.scene) { console.error('need --scene <index.html>'); process.exit(2); }
const sceneFile = fs.realpathSync(path.resolve(A.scene.replace(/^~(?=$|\/)/, os.homedir())));
const studioReal = fs.realpathSync(STUDIO);
if (!sceneFile.startsWith(studioReal + path.sep)) { console.error('scene must live under ' + studioReal); process.exit(2); }
const fps = +(A.fps || 60), from = +(A.from || 0), step = +(A.step || 1);
const MIME = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.json': 'application/json', '.svg': 'image/svg+xml', '.png': 'image/png', '.jpg': 'image/jpeg', '.woff2': 'font/woff2', '.woff': 'font/woff', '.ttf': 'font/ttf', '.wav': 'audio/wav', '.mp3': 'audio/mpeg' };
const server = http.createServer(async (req, res) => {
  try { const rel = decodeURIComponent(new URL(req.url, 'http://x').pathname); const f = path.resolve(studioReal, '.' + rel);
    if (!f.startsWith(studioReal)) { res.writeHead(403).end(); return; }
    let st = await fsp.stat(f).catch(() => null); if (!st) { res.writeHead(404).end(); return; }
    res.writeHead(200, { 'content-type': MIME[path.extname(f)] || 'application/octet-stream', 'cache-control': 'no-store' }); fs.createReadStream(f).pipe(res);
  } catch (e) { res.writeHead(500).end(String(e)); }
});
await new Promise((r) => server.listen(0, '127.0.0.1', r));
const url = `http://127.0.0.1:${server.address().port}/${path.relative(studioReal, sceneFile).split(path.sep).map(encodeURIComponent).join('/')}`;
const browser = await puppeteer.launch({ executablePath: A.chrome || [process.env.CHROME_PATH, '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', '/usr/bin/google-chrome', '/usr/bin/chromium', '/usr/bin/chromium-browser'].find((c) => c && fs.existsSync(c)), headless: true, defaultViewport: null, args: ['--disable-gpu-rasterization', '--force-color-profile=srgb', '--hide-scrollbars', '--mute-audio', '--autoplay-policy=no-user-gesture-required'] });
try {
  const page = await browser.newPage(); await page.setViewport({ width: +(A.w || 1920), height: +(A.h || 1080), deviceScaleFactor: 1 });
  page.on('pageerror', (e) => console.error('page error:', e.message));
  await page.goto(url, { waitUntil: 'load', timeout: 90000 });
  await page.waitForFunction(() => window.__ready && typeof window.__renderFrame === 'function', { timeout: 90000 });
  const sc = await page.evaluate(async () => { const s = await window.__ready; return window.__scene || s; });
  const to = +(A.to || Math.round((sc.duration || 10) * fps));
  const sel = A.sel || '#stage *';
  // pick every element that is animated by inline style (the engine sets transform/opacity/filter inline), plus canvases are ignored
  await page.evaluate(async (sel) => { await window.__renderFrame(0, 60); window.__els = []; document.querySelectorAll(sel).forEach((e, i) => { if (e.tagName === 'CANVAS') return; const s = e.getAttribute('style') || ''; if (/transform|opacity|filter|left|top|display/.test(s) || e.classList.contains('w')) { e.__mid = window.__els.length; window.__els.push(e); } }); }, sel);
  const nEl = await page.evaluate(() => window.__els.length);
  console.error(`scene ${path.basename(path.dirname(sceneFile))}: ${nEl} animated elements, frames ${from}..${to} step ${step}`);
  const meta = await page.evaluate(() => window.__els.map((e, i) => { const t = (e.textContent || '').trim().slice(0, 24); return { i, id: e.id || '', cls: (e.className && e.className.baseVal === undefined ? e.className : '').toString().slice(0, 40), tag: e.tagName.toLowerCase(), text: e.children.length ? '' : t, fontPx: parseFloat(getComputedStyle(e).fontSize) || 0, hasText: !!(e.childNodes.length && [...e.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim())) }; }));
  const series = meta.map((m) => ({ ...m, x: [], y: [], w: [], h: [], op: [], blur: [], frames: [] }));
  const BATCH = 30;
  for (let f = from; f < to; f += step * BATCH) {
    const frames = []; for (let k = 0; k < BATCH && f + k * step < to; k++) frames.push(f + k * step);
    const rows = await page.evaluate(async (frames, fps) => {
      const out = []; const sr = document.getElementById('stage').getBoundingClientRect();
      for (const fr of frames) { await window.__renderFrame(fr, fps); const row = [];
        for (const e of window.__els) { const cs = getComputedStyle(e); if (cs.display === 'none' || cs.visibility === 'hidden' || e.getClientRects().length === 0) { row.push(null); continue; } const r = e.getBoundingClientRect(); let op = 1; for (let n = e; n && n.id !== 'stage'; n = n.parentElement) op *= parseFloat(getComputedStyle(n).opacity); const m = /blur\(([\d.]+)px\)/.exec(cs.filter); row.push([r.left - sr.left, r.top - sr.top, r.width, r.height, op, m ? +m[1] : 0]); }
        out.push(row); }
      return out; }, frames, fps);
    rows.forEach((row, k) => row.forEach((v, i) => { if (!v) return; const s = series[i]; s.frames.push(frames[k]); s.x.push(+v[0].toFixed(3)); s.y.push(+v[1].toFixed(3)); s.w.push(+v[2].toFixed(3)); s.h.push(+v[3].toFixed(3)); s.op.push(+v[4].toFixed(3)); s.blur.push(+v[5].toFixed(2)); }));
  }
  const outFile = A.out ? path.resolve(A.out.replace(/^~(?=$|\/)/, os.homedir())) : null;
  const doc = { scene: sceneFile, fps, step, from, to, series: series.filter((s) => s.frames.length > 2) };
  if (outFile) { fs.writeFileSync(outFile, JSON.stringify(doc)); console.error('wrote ' + outFile); } else process.stdout.write(JSON.stringify(doc));
} finally { await browser.close(); server.close(); }
