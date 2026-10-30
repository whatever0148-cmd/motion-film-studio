#!/usr/bin/env node
/*
 * render_direct.mjs  (Engine A: frame-exact Chromium renderer + encoder)
 *
 * node ~/EmpireBrain/studio/direct-engine/render_direct.mjs \
 *   --scene <scene dir or index.html> --out <file.mp4> \
 *   [--fps 60] [--duration <s>] [--scale 2] [--workers 4] \
 *   [--codec h264|hevc] [--bitrate 18M] [--audio <wav>] [--keep-frames] [--frames-dir <dir>] \
 *   [--stills 0.2,5,13 --stills-out <dir>] [--from <frame> --to <frame>]
 *
 * Extensions (see CONTRACT.md "engine builder additions"):
 *   --capture jpeg|png   frame format (default jpeg q95, measured faster; see README)
 *   --jpeg-quality 95    --webgl-fallback swiftshader   --ready-timeout 90   --frame-timeout 60
 *   --bench-capture N    time N frames with jpeg and with png, print the numbers, exit
 *   --chrome <path>      Chrome binary (default: /Applications/Google Chrome.app)
 *   --raster cpu|gpu     page raster (default cpu: measured deterministic; gpu raster was not)
 *
 * No Remotion. Every frame is window.__renderFrame(i, fps) then one CDP capture.
 */
import http from 'node:http';
import fs from 'node:fs';
import fsp from 'node:fs/promises';
import path from 'node:path';
import os from 'node:os';
import { spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import puppeteer from 'puppeteer-core';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const STUDIO = path.resolve(HERE, '..');
const DEFAULT_CHROME = [process.env.CHROME_PATH, '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', '/Applications/Chromium.app/Contents/MacOS/Chromium', '/usr/bin/google-chrome', '/usr/bin/google-chrome-stable', '/usr/bin/chromium', '/usr/bin/chromium-browser', 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe', 'C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe'].find((c) => c && fs.existsSync(c)) || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
const FFMPEG_CANDIDATES = [path.join(os.homedir(), '.local/bin/ffmpeg'), '/opt/homebrew/bin/ffmpeg', '/usr/local/bin/ffmpeg', 'ffmpeg'];
const SAFE_ZONE_9x16 = { x0: 120, x1: 960, y0: 280, y1: 1380 };
const SAFE_ZONE_16x9 = { x0: 192, x1: 1728, y0: 108, y1: 972 }; // 10% title-safe, CONTRACT agents addition
const MIN_FONT_PX = 28;
const SAFE_SAMPLE_EVERY = 6;
const EFFECTIVE_HOLD_S = 0.5; // on-screen (scaled) type under MIN_FONT_PX this long is a violation

// ------------------------------------------------------------------ args
function parseArgs(argv) {
  const flags = new Set(['keep-frames', 'help']);
  const a = {};
  for (let i = 0; i < argv.length; i++) {
    const k = argv[i];
    if (!k.startsWith('--')) throw new Error(`unexpected argument "${k}"`);
    const key = k.slice(2);
    if (flags.has(key)) { a[key] = true; continue; }
    const v = argv[i + 1];
    if (v === undefined || v.startsWith('--')) throw new Error(`--${key} needs a value`);
    a[key] = v; i++;
  }
  return a;
}
const usage = `usage: node render_direct.mjs --scene <dir|index.html> --out <file.mp4>
  [--fps 60] [--duration s] [--scale 2] [--workers 4] [--codec h264|hevc] [--bitrate 18M]
  [--audio wav] [--keep-frames] [--frames-dir dir] [--stills 0.2,5 --stills-out dir]
  [--from frame --to frame]  (frames from..to-1, --to is exclusive)
  [--capture jpeg|png] [--jpeg-quality 95] [--webgl-fallback swiftshader]
  [--ready-timeout 90] [--frame-timeout 60] [--bench-capture N] [--chrome path]
  [--browsers 0|1]  (0 = one Chrome per worker, default; 1 = one Chrome, workers as tabs)
  [--raster cpu|gpu]  (page raster; cpu default = deterministic, WebGL is on the GPU either way)
  [--safe-zone x0,x1,y0,y1]  (default 9:16 120,960,280,1380; 16:9 192,1728,108,972)`;

function parseBitrate(s) {
  const m = /^(\d+(?:\.\d+)?)([kKmM]?)$/.exec(String(s));
  if (!m) throw new Error(`bad --bitrate "${s}" (use e.g. 18M)`);
  const n = parseFloat(m[1]);
  const u = m[2].toLowerCase();
  return u === 'm' ? n * 1e6 : u === 'k' ? n * 1e3 : n;
}
const fmtRate = (bps) => (bps % 1e6 === 0 ? `${bps / 1e6}M` : `${Math.round(bps / 1e3)}k`);

function findFfmpeg() {
  for (const c of FFMPEG_CANDIDATES) {
    if (c === 'ffmpeg' || fs.existsSync(c)) return c;
  }
  return 'ffmpeg';
}

// ------------------------------------------------------------------ static server
const MIME = {
  '.html': 'text/html; charset=utf-8', '.htm': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8', '.mjs': 'text/javascript; charset=utf-8', '.cjs': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8', '.json': 'application/json; charset=utf-8', '.map': 'application/json; charset=utf-8',
  '.txt': 'text/plain; charset=utf-8', '.md': 'text/plain; charset=utf-8', '.csv': 'text/csv; charset=utf-8',
  '.svg': 'image/svg+xml', '.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.gif': 'image/gif',
  '.webp': 'image/webp', '.avif': 'image/avif', '.ico': 'image/x-icon', '.bmp': 'image/bmp',
  '.woff': 'font/woff', '.woff2': 'font/woff2', '.ttf': 'font/ttf', '.otf': 'font/otf',
  '.wasm': 'application/wasm', '.glsl': 'text/plain; charset=utf-8', '.vert': 'text/plain; charset=utf-8', '.frag': 'text/plain; charset=utf-8',
  '.wav': 'audio/wav', '.mp3': 'audio/mpeg', '.m4a': 'audio/mp4', '.ogg': 'audio/ogg',
  '.mp4': 'video/mp4', '.webm': 'video/webm', '.mov': 'video/quicktime',
  '.glb': 'model/gltf-binary', '.gltf': 'model/gltf+json', '.bin': 'application/octet-stream', '.hdr': 'application/octet-stream',
  '.ktx2': 'image/ktx2',
};

function startServer(root) {
  const server = http.createServer(async (req, res) => {
    try {
      const u = new URL(req.url, 'http://127.0.0.1');
      let rel = decodeURIComponent(u.pathname);
      if (rel === '/favicon.ico') { res.writeHead(204).end(); return; }
      let file = path.resolve(root, '.' + rel);
      if (file !== root && !file.startsWith(root + path.sep)) { res.writeHead(403).end('forbidden'); return; }
      let st = await fsp.stat(file).catch(() => null);
      if (st && st.isDirectory()) { file = path.join(file, 'index.html'); st = await fsp.stat(file).catch(() => null); }
      if (!st || !st.isFile()) { res.writeHead(404, { 'content-type': 'text/plain' }).end('not found: ' + rel); server.emit('miss', rel); return; }
      const type = MIME[path.extname(file).toLowerCase()] || 'application/octet-stream';
      res.writeHead(200, { 'content-type': type, 'content-length': st.size, 'cache-control': 'no-store', 'access-control-allow-origin': '*' });
      if (req.method === 'HEAD') { res.end(); return; }
      fs.createReadStream(file).pipe(res);
    } catch (e) {
      res.writeHead(500).end(String(e));
    }
  });
  return new Promise((resolve) => server.listen(0, '127.0.0.1', () => resolve(server)));
}

// ------------------------------------------------------------------ helpers
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
function withTimeout(p, ms, msg) {
  let to;
  return Promise.race([p, new Promise((_, rej) => { to = setTimeout(() => rej(new Error(msg)), ms); })]).finally(() => clearTimeout(to));
}
function run(cmd, args, { quiet = true } = {}) {
  return new Promise((resolve, reject) => {
    const p = spawn(cmd, args, { stdio: ['ignore', 'pipe', 'pipe'] });
    let out = '', err = '';
    p.stdout.on('data', (d) => { out += d; });
    p.stderr.on('data', (d) => { err += d; if (!quiet) process.stderr.write(d); });
    p.on('error', reject);
    p.on('close', (code) => (code === 0 ? resolve({ out, err }) : reject(Object.assign(new Error(`${cmd} exited ${code}\n${err.slice(-3000)}`), { out, err }))));
  });
}
function imageSize(buf) {
  if (buf[0] === 0x89 && buf[1] === 0x50) return { w: buf.readUInt32BE(16), h: buf.readUInt32BE(20) };
  let i = 2;
  while (i < buf.length) {
    if (buf[i] !== 0xff) { i++; continue; }
    const marker = buf[i + 1];
    const len = buf.readUInt16BE(i + 2);
    if (marker >= 0xc0 && marker <= 0xc3) return { h: buf.readUInt16BE(i + 5), w: buf.readUInt16BE(i + 7) };
    i += 2 + len;
  }
  return null;
}

function checkBoxes(boxes, frame, t, zone) {
  const violations = [];
  const fontViolations = [];
  let minFont = Infinity;
  for (const b of boxes) {
    if (b.kind === 'text' && b.fontPx != null) {
      minFont = Math.min(minFont, b.fontPx);
      if (b.fontPx < MIN_FONT_PX) fontViolations.push({ frame, t, id: b.id, fontPx: b.fontPx });
    }
    if (zone && (b.kind === 'text' || b.kind === 'hero')) {
      const tol = 0.5;
      const over = {
        left: Math.max(0, zone.x0 - b.x), right: Math.max(0, b.x + b.w - zone.x1),
        top: Math.max(0, zone.y0 - b.y), bottom: Math.max(0, b.y + b.h - zone.y1),
      };
      if (over.left > tol || over.right > tol || over.top > tol || over.bottom > tol) {
        violations.push({ frame, t: +t.toFixed(4), id: b.id, kind: b.kind, box: { x: b.x, y: b.y, w: b.w, h: b.h }, overflow_px: over });
      }
    }
  }
  return { violations, fontViolations, minFont };
}

// ------------------------------------------------------------------ main
async function main() {
  const args = parseArgs(process.argv.slice(2));
  if (args.help || !args.scene) { console.log(usage); process.exit(args.help ? 0 : 2); }

  const t0 = Date.now();
  // scene path
  let sceneFile = path.resolve(args.scene.replace(/^~(?=$|\/)/, os.homedir()));
  if (fs.existsSync(sceneFile) && fs.statSync(sceneFile).isDirectory()) sceneFile = path.join(sceneFile, 'index.html');
  if (!fs.existsSync(sceneFile)) throw new Error(`scene not found: ${sceneFile}`);
  const studioReal = fs.realpathSync(STUDIO);
  const sceneReal = fs.realpathSync(sceneFile);
  if (!sceneReal.startsWith(studioReal + path.sep)) throw new Error(`scene must live under ${studioReal} (got ${sceneReal})`);
  const sceneUrlPath = '/' + path.relative(studioReal, sceneReal).split(path.sep).map(encodeURIComponent).join('/');

  const stillsMode = !!args.stills;
  const benchN = args['bench-capture'] ? parseInt(args['bench-capture'], 10) : 0;
  if (!stillsMode && !benchN && !args.out) throw new Error('--out <file.mp4> is required (or use --stills / --bench-capture)');
  const outFile = args.out ? path.resolve(args.out.replace(/^~(?=$|\/)/, os.homedir())) : null;

  const scale = args.scale ? parseFloat(args.scale) : 2;
  let workers = args.workers ? parseInt(args.workers, 10) : 4;
  const codec = (args.codec || 'h264').toLowerCase();
  if (!['h264', 'hevc'].includes(codec)) throw new Error('--codec must be h264 or hevc');
  const bitrate = parseBitrate(args.bitrate || '18M');
  const capture = (args.capture || 'jpeg').toLowerCase();
  if (!['jpeg', 'png'].includes(capture)) throw new Error('--capture must be jpeg or png');
  const jpegQ = args['jpeg-quality'] ? parseInt(args['jpeg-quality'], 10) : 95;
  const readyTimeout = (args['ready-timeout'] ? parseFloat(args['ready-timeout']) : 90) * 1000;
  const frameTimeout = (args['frame-timeout'] ? parseFloat(args['frame-timeout']) : 60) * 1000;
  const chromePath = args.chrome || DEFAULT_CHROME;
  const fallback = args['webgl-fallback'];
  if (fallback && fallback !== 'swiftshader') throw new Error('--webgl-fallback only supports "swiftshader"');
  if (args.audio && !fs.existsSync(path.resolve(args.audio))) throw new Error(`--audio file not found: ${args.audio}`);
  const ffmpeg = findFfmpeg();

  // server + browser
  const server = await startServer(studioReal);
  const port = server.address().port;
  const misses = [];
  server.on('miss', (p) => misses.push(p));
  const sceneUrl = `http://127.0.0.1:${port}${sceneUrlPath}`;

  const chromeArgs = fallback === 'swiftshader'
    ? ['--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist']
    : ['--use-angle=metal', '--enable-gpu', '--ignore-gpu-blocklist'];
  // Page raster (text, CSS, 2D canvas compositing). WebGL stays on the GPU either way.
  // cpu (default): Skia software raster. Measured byte-identical frames across runs and workers.
  // gpu: GPU raster. Measured NOT deterministic: text under a changing transform scale differed
  // between runs by up to 58 code values on single pixels (glyph/text-blob cache state).
  const raster = (args.raster || 'cpu').toLowerCase();
  if (!['cpu', 'gpu'].includes(raster)) throw new Error('--raster must be cpu or gpu');
  chromeArgs.push(raster === 'gpu' ? '--enable-gpu-rasterization' : '--disable-gpu-rasterization');
  chromeArgs.push(
    '--enable-webgl', '--disable-background-timer-throttling', '--disable-renderer-backgrounding',
    '--disable-backgrounding-occluded-windows', '--force-color-profile=srgb', '--hide-scrollbars', '--mute-audio',
    '--no-first-run', '--no-default-browser-check', '--disable-extensions', '--autoplay-policy=no-user-gesture-required',
    '--disable-features=Translate,BackForwardCache,MediaRouter,OptimizationHints',
  );
  const launchChrome = () => puppeteer.launch({
    executablePath: chromePath, headless: true, args: chromeArgs,
    ignoreDefaultArgs: ['--disable-gpu'], protocolTimeout: Math.max(180000, frameTimeout * 2),
    defaultViewport: null,
  });
  // --browsers 0 (default) = one Chrome per worker (parallel JPEG encode + readback, measured faster);
  // --browsers 1 = all workers as tabs of one Chrome.
  const browserMode = args.browsers != null ? parseInt(args.browsers, 10) : 0;
  const browser = await launchChrome();
  const browsers = [browser];
  let chromeVersion = await browser.version();
  const errors = [];
  let shuttingDown = false;
  const cleanup = async () => {
    shuttingDown = true;
    await Promise.all(browsers.map(async (b) => {
      const proc = b.process();
      await withTimeout(b.close(), 10000, 'browser.close timed out').catch((e) => {
        console.warn(`[render] ${e.message}; killing Chrome`);
        try { proc && proc.kill('SIGKILL'); } catch { /* already gone */ }
      });
    }));
    server.closeAllConnections?.();
    server.close();
  };
  process.on('SIGINT', async () => { await cleanup(); process.exit(130); });

  try {
    // GPU probe on a blank page
    const probe = await browser.newPage();
    const gl = await probe.evaluate(() => {
      const c = document.createElement('canvas');
      const g = c.getContext('webgl2') || c.getContext('webgl');
      if (!g) return { ok: false };
      const ext = g.getExtension('WEBGL_debug_renderer_info');
      return {
        ok: true, webgl2: !!c.getContext && g instanceof WebGL2RenderingContext,
        renderer: ext ? g.getParameter(ext.UNMASKED_RENDERER_WEBGL) : g.getParameter(g.RENDERER),
        vendor: ext ? g.getParameter(ext.UNMASKED_VENDOR_WEBGL) : g.getParameter(g.VENDOR),
        maxTex: g.getParameter(g.MAX_TEXTURE_SIZE),
      };
    });
    await probe.close();
    if (!gl.ok) console.warn('[render] WARNING: no WebGL context in this Chrome. Try --webgl-fallback swiftshader.');
    const software = gl.ok && /swiftshader|llvmpipe|software/i.test(gl.renderer || '');

    // ------------------------------------------------------------ page factory
    async function openWorker(id, vw, vh) {
      let host = browser;
      if (id > 0 && browserMode !== 1) { host = await launchChrome(); browsers.push(host); }
      const page = await host.newPage();
      page.setDefaultTimeout(readyTimeout);
      page.on('pageerror', (e) => { const m = `[scene w${id}] page error: ${e.message}`; errors.push(m); console.error(m); });
      page.on('console', (msg) => {
        if (msg.type() === 'error') { const m = `[scene w${id}] console error: ${msg.text()}`; errors.push(m); console.error(m); }
      });
      page.on('requestfailed', (r) => { if (!shuttingDown) { const m = `[scene w${id}] request failed: ${r.url()} ${r.failure()?.errorText || ''}`; errors.push(m); console.error(m); } });
      page.on('response', (r) => { if (r.status() >= 400) { const m = `[scene w${id}] HTTP ${r.status()} ${r.url()}`; errors.push(m); console.error(m); } });
      await page.setViewport({ width: vw, height: vh, deviceScaleFactor: scale });
      const cdp = await page.createCDPSession();
      await cdp.send('Emulation.setFocusEmulationEnabled', { enabled: true }).catch(() => {});
      await cdp.send('Page.setWebLifecycleState', { state: 'active' }).catch(() => {});
      await page.goto(sceneUrl, { waitUntil: 'load', timeout: readyTimeout });
      await withTimeout(page.waitForFunction(() => window.__ready && typeof window.__renderFrame === 'function', { timeout: readyTimeout }), readyTimeout + 1000,
        `scene never defined window.__ready / window.__renderFrame within ${readyTimeout / 1000}s (${sceneUrl})`).catch((e) => {
        throw new Error(`${e.message}\nDoes the scene load /direct-engine/runtime/engine-runtime.js and call EngineRuntime.defineScene?`);
      });
      const sc = await withTimeout(page.evaluate(async () => { const s = await window.__ready; return window.__scene || s; }), readyTimeout,
        `window.__ready did not resolve within ${readyTimeout / 1000}s. Check fonts, images and setup() in ${sceneFile}`);
      return { id, page, cdp, scene: sc, vw, vh };
    }

    async function renderAndCapture(w, frame, fps, fmt) {
      await withTimeout(w.page.evaluate((f, r) => window.__renderFrame(f, r), frame, fps), frameTimeout, `__renderFrame(${frame}) timed out after ${frameTimeout / 1000}s`);
      // two rAF ticks so the compositor has painted the new state
      await w.page.evaluate(() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(() => r()))));
      // Chrome 156 headless captures at CSS size unless the clip carries the scale;
      // clip.scale = deviceScaleFactor gives true device pixels (verified 1-px column test).
      const clip = { x: 0, y: 0, width: w.vw, height: w.vh, scale };
      const params = fmt === 'png'
        ? { format: 'png', clip, fromSurface: true, captureBeyondViewport: false, optimizeForSpeed: true }
        : { format: 'jpeg', quality: jpegQ, clip, fromSurface: true, captureBeyondViewport: false, optimizeForSpeed: true };
      const { data } = await w.cdp.send('Page.captureScreenshot', params);
      return Buffer.from(data, 'base64');
    }

    // first worker tells us the scene size and timing
    let first = await openWorker(0, 1080, 1920);
    let scene = first.scene;
    if (!scene || !scene.width || !scene.height || !scene.duration) throw new Error(`window.__scene is incomplete: ${JSON.stringify(scene)}`);
    if (scene.width !== 1080 || scene.height !== 1920) {
      await first.page.close();
      first = await openWorker(0, scene.width, scene.height);
      scene = first.scene;
    }
    const fps = args.fps ? parseFloat(args.fps) : (scene.fps || 60);
    const duration = args.duration ? parseFloat(args.duration) : scene.duration;
    const totalFrames = Math.round(duration * fps);
    let zone = scene.width === 1080 && scene.height === 1920 ? SAFE_ZONE_9x16
      : scene.width === 1920 && scene.height === 1080 ? SAFE_ZONE_16x9 : null;
    if (args['safe-zone']) {
      const z = String(args['safe-zone']).split(',').map(Number);
      if (z.length !== 4 || z.some((v) => !Number.isFinite(v))) throw new Error('--safe-zone needs x0,x1,y0,y1');
      zone = { x0: z[0], x1: z[1], y0: z[2], y1: z[3] };
    }
    const cuesBeats = await first.page.evaluate(() => ({ cues: window.__cues || [], beats: window.__beats || [] }));

    const gpuLine = `${gl.renderer || 'none'}${software ? '  (SOFTWARE)' : ''}`;
    console.log(`[render] chrome ${chromeVersion} | WebGL: ${gpuLine}`);
    console.log(`[render] scene ${path.relative(studioReal, sceneReal)} ${scene.width}x${scene.height} @${fps}fps ${duration}s = ${totalFrames} frames, scale ${scale}`);

    // ------------------------------------------------------------ bench mode
    if (benchN) {
      const res = {};
      for (const fmt of ['jpeg', 'png']) {
        await renderAndCapture(first, 0, fps, fmt); // warm
        const s = Date.now();
        let bytes = 0, dims = null;
        for (let i = 0; i < benchN; i++) {
          const f = Math.floor((i / benchN) * totalFrames);
          const buf = await renderAndCapture(first, f, fps, fmt);
          bytes += buf.length; dims = dims || imageSize(buf);
          await fsp.writeFile(path.join(os.tmpdir(), `bench_${process.pid}.${fmt === 'png' ? 'png' : 'jpg'}`), buf);
        }
        const sec = (Date.now() - s) / 1000;
        res[fmt] = { frames: benchN, seconds: +sec.toFixed(3), s_per_frame: +(sec / benchN).toFixed(4), avg_kb: Math.round(bytes / benchN / 1024), dims };
        console.log(`[bench] ${fmt}${fmt === 'jpeg' ? ' q' + jpegQ : ''}: ${res[fmt].s_per_frame}s/frame (render+capture+write), ${res[fmt].avg_kb} KB/frame, ${dims?.w}x${dims?.h}`);
      }
      console.log(JSON.stringify({ bench_capture: res, renderer: gl.renderer, chrome: chromeVersion }));
      return;
    }

    // ------------------------------------------------------------ stills mode
    if (stillsMode) {
      const secs = String(args.stills).split(',').map((s) => s.trim()).filter(Boolean).map(Number);
      if (secs.some((s) => !Number.isFinite(s) || s < 0)) throw new Error(`bad --stills "${args.stills}"`);
      const stillsOut = path.resolve(args['stills-out'] || (outFile ? outFile.replace(/\.mp4$/i, '') + '_stills' : path.dirname(sceneReal) + '/stills'));
      await fsp.mkdir(stillsOut, { recursive: true });
      const report = [];
      for (const s of secs) {
        const frame = Math.min(totalFrames - 1, Math.round(s * fps));
        const buf = await renderAndCapture(first, frame, fps, 'png');
        const boxes = await first.page.evaluate(() => (window.__safeBoxes ? window.__safeBoxes() : []));
        const chk = checkBoxes(boxes, frame, frame / fps, zone);
        const name = `still_${s.toFixed(2)}s`;
        const full = path.join(stillsOut, `${name}.png`);
        const small = path.join(stillsOut, `${name}_1080w.png`);
        await fsp.writeFile(full, buf);
        await run(ffmpeg, ['-y', '-hide_banner', '-loglevel', 'error', '-i', full, '-vf', 'scale=1080:-2:flags=lanczos+accurate_rnd+full_chroma_int', small]);
        const dims = imageSize(buf);
        report.push({ t: s, frame, png: full, png_1080w: small, size: dims, boxes, violations: chk.violations, font_violations: chk.fontViolations });
        console.log(`[stills] t=${s}s frame ${frame} -> ${full} (${dims.w}x${dims.h}), boxes ${boxes.length}, zone violations ${chk.violations.length}, font violations ${chk.fontViolations.length}`);
      }
      await fsp.writeFile(path.join(stillsOut, 'stills.json'), JSON.stringify({ scene: sceneReal, renderer: gl.renderer, chrome: chromeVersion, scale, stills: report }, null, 2));
      console.log(`[stills] wrote ${secs.length} stills to ${stillsOut} in ${((Date.now() - t0) / 1000).toFixed(1)}s`);
      if (errors.length) console.log(`[stills] scene errors: ${errors.length}`);
      return;
    }

    // ------------------------------------------------------------ frame range + workers
    const from = args.from != null ? parseInt(args.from, 10) : 0;
    const to = args.to != null ? parseInt(args.to, 10) : totalFrames;
    if (!(from >= 0 && to > from && to <= totalFrames)) throw new Error(`bad frame range --from ${from} --to ${to} (scene has ${totalFrames} frames; --to is exclusive)`);
    const n = to - from;
    workers = Math.max(1, Math.min(workers, n));
    const framesDir = path.resolve(args['frames-dir'] || `${outFile}.frames`);
    await fsp.rm(framesDir, { recursive: true, force: true });
    await fsp.mkdir(framesDir, { recursive: true });
    await fsp.mkdir(path.dirname(outFile), { recursive: true });
    const ext = capture === 'png' ? 'png' : 'jpg';

    const pool = [first];
    const opened = await Promise.all(Array.from({ length: workers - 1 }, (_, i) => openWorker(i + 1, scene.width, scene.height)));
    pool.push(...opened);
    const tReady = Date.now();

    const chunk = Math.ceil(n / workers);
    const samples = [];
    let violations = [], fontViolations = [], minFont = Infinity;
    let done = 0, captureDims = null;
    const progressEvery = Math.max(1, Math.round(n / 20));
    const writes = [];

    await Promise.all(pool.map(async (w, wi) => {
      const a = from + wi * chunk;
      const b = Math.min(to, a + chunk);
      for (let f = a; f < b; f++) {
        const buf = await renderAndCapture(w, f, fps, capture);
        if (!captureDims) captureDims = imageSize(buf);
        writes.push(fsp.writeFile(path.join(framesDir, `frame_${String(f).padStart(6, '0')}.${ext}`), buf));
        if (f % SAFE_SAMPLE_EVERY === 0) {
          const boxes = await w.page.evaluate(() => (window.__safeBoxes ? window.__safeBoxes() : []));
          const chk = checkBoxes(boxes, f, f / fps, zone);
          samples.push({ frame: f, t: +(f / fps).toFixed(4), boxes });
          violations.push(...chk.violations); fontViolations.push(...chk.fontViolations);
          minFont = Math.min(minFont, chk.minFont);
        }
        done++;
        if (done % progressEvery === 0 || done === n) {
          const el = (Date.now() - tReady) / 1000;
          process.stdout.write(`\r[render] ${done}/${n} frames  ${(el / done).toFixed(3)} s/frame  ${el.toFixed(1)}s   `);
        }
      }
    }));
    await Promise.all(writes);
    process.stdout.write('\n');
    const tRender = Date.now();
    const renderSec = (tRender - tReady) / 1000;
    samples.sort((x, y) => x.frame - y.frame);
    violations.sort((x, y) => x.frame - y.frame);
    fontViolations.sort((x, y) => x.frame - y.frame);
    if (minFont === Infinity) minFont = null;

    // Effective type size = fontPx * transform scale. A text box that stays under 28 px on screen
    // for EFFECTIVE_HOLD_S or longer (consecutive samples) is a font violation too; a short
    // scale-in passes. Without this, 56 px type under a parent scale(0.4) (22.4 px on screen)
    // passed for the whole clip (measured with test/render_fixture_safe_violations).
    let minEffFont = Infinity;
    const runs = new Map(); // id -> {first, last, minEff, sample}
    const flushRun = (id) => {
      const r = runs.get(id);
      if (!r) return;
      runs.delete(id);
      const span = (r.last.frame - r.first.frame + SAFE_SAMPLE_EVERY) / fps;
      if (span >= EFFECTIVE_HOLD_S) {
        fontViolations.push({ frame: r.first.frame, t: r.first.t, id, fontPx: r.box.fontPx, scale: r.box.scale,
          effective_px: +r.minEff.toFixed(1), rule: 'effective', run_s: +span.toFixed(3) });
      }
    };
    let prevFrame = null;
    for (const smp of samples) {
      const seen = new Set();
      if (prevFrame != null && smp.frame - prevFrame !== SAFE_SAMPLE_EVERY) for (const id of [...runs.keys()]) flushRun(id);
      for (const b of smp.boxes) {
        if (b.kind !== 'text' || b.fontPx == null) continue;
        const eff = b.fontPx * (b.scale != null ? b.scale : 1);
        minEffFont = Math.min(minEffFont, eff);
        if (eff < MIN_FONT_PX && b.fontPx >= MIN_FONT_PX) { // design-size failures are already listed
          seen.add(b.id);
          const r = runs.get(b.id);
          if (r) { r.last = smp; if (eff < r.minEff) { r.minEff = eff; r.box = b; } }
          else runs.set(b.id, { first: smp, last: smp, minEff: eff, box: b });
        }
      }
      for (const id of [...runs.keys()]) if (!seen.has(id)) flushRun(id);
      prevFrame = smp.frame;
    }
    for (const id of [...runs.keys()]) flushRun(id);
    fontViolations.sort((x, y) => x.frame - y.frame);
    if (minEffFont === Infinity) minEffFont = null; else minEffFont = +minEffFont.toFixed(1);

    // ------------------------------------------------------------ encode
    const outW = scene.width, outH = scene.height;
    // format=rgb24 first: Chrome's JPEGs decode as yuvj420p (full-range BT.601), and swscale's
    // yuvj420p -> yuv420p(tv) Lanczos path is slow (measured 15.0 s for 300 2160x3840 frames).
    // Going through rgb24 takes 3.9 s for the same frames. PNG frames are already RGB.
    const vf = `format=rgb24,scale=${outW}:${outH}:flags=lanczos+accurate_rnd+full_chroma_int:out_color_matrix=bt709:out_range=tv,format=yuv420p,setparams=color_primaries=bt709:color_trc=bt709:colorspace=bt709:range=tv`;
    // setparams: ffmpeg 7.1 otherwise writes primaries/trc as 'unknown' despite -color_primaries/-color_trc (measured)
    const ff = ['-y', '-hide_banner', '-framerate', String(fps), '-start_number', String(from), '-i', path.join(framesDir, `frame_%06d.${ext}`)];
    // a --from range starts the audio at the same time so picture and sound stay in sync
    if (args.audio) ff.push(...(from > 0 ? ['-ss', (from / fps).toFixed(6)] : []), '-i', path.resolve(args.audio));
    ff.push('-vf', vf);
    if (codec === 'hevc') ff.push('-c:v', 'hevc_videotoolbox', '-tag:v', 'hvc1', '-b:v', fmtRate(bitrate), '-profile:v', 'main');
    else ff.push('-c:v', 'h264_videotoolbox', '-b:v', fmtRate(bitrate), '-maxrate', fmtRate(bitrate * 4 / 3), '-bufsize', fmtRate(bitrate * 2), '-profile:v', 'high');
    ff.push('-colorspace', 'bt709', '-color_primaries', 'bt709', '-color_trc', 'bt709', '-color_range', 'tv');
    if (args.audio) ff.push('-map', '0:v:0', '-map', '1:a:0', '-c:a', 'aac', '-b:a', '320k', '-ar', '48000', '-af', 'apad', '-t', (n / fps).toFixed(6));
    ff.push('-movflags', '+faststart', outFile);
    console.log(`[encode] ${ffmpeg} ${ff.map((x) => (/[\s:,=]/.test(x) ? `"${x}"` : x)).join(' ')}`);
    const enc = await run(ffmpeg, ff);
    const outInfo = enc.err.split('Output #0')[1] || '';
    const encLines = outInfo.split('\n').filter((l) => /Stream #0:\d+/.test(l)).map((l) => l.trim());
    const tEnc = Date.now();

    // ------------------------------------------------------------ sidecars
    const safeSidecar = {
      scene: sceneReal, video: outFile, width: scene.width, height: scene.height, fps,
      safe_zone: zone, min_font_rule_px: MIN_FONT_PX, sample_every_frames: SAFE_SAMPLE_EVERY,
      frames_sampled: samples.length, violations, font_violations: fontViolations, min_font_px: minFont,
      min_effective_font_px: minEffFont, effective_hold_s: EFFECTIVE_HOLD_S,
      font_px_note: 'fontPx is the computed CSS font-size (design size, before transforms); boxes include transforms. '
        + `effective px = fontPx * scale; under ${MIN_FONT_PX} px for ${EFFECTIVE_HOLD_S} s or more is a font violation (rule "effective")`,
      samples,
    };
    const totalSec = (tEnc - t0) / 1000;
    const renderSidecar = {
      generated_at: new Date().toISOString(),
      scene: sceneReal, scene_url: sceneUrl, out: outFile,
      chrome: { version: chromeVersion, path: chromePath, flags: chromeArgs, headless: true, raster },
      webgl: { renderer: gl.renderer || null, vendor: gl.vendor || null, webgl2: gl.webgl2 || false, software, fallback: fallback || null },
      width: scene.width, height: scene.height, fps, duration, scale,
      capture: { format: capture, jpeg_quality: capture === 'jpeg' ? jpegQ : null, dims: captureDims },
      frames: n, frame_range: [from, to], total_scene_frames: totalFrames, workers,
      seconds_per_frame: +(renderSec / n).toFixed(4),
      seconds_per_frame_per_worker: +((renderSec * workers) / n).toFixed(4),
      browsers: browsers.length,
      timings_s: { startup: +((tReady - t0) / 1000).toFixed(2), render: +renderSec.toFixed(2), encode: +((tEnc - tRender) / 1000).toFixed(2), total: +totalSec.toFixed(2) },
      encoder: { codec, bitrate: fmtRate(bitrate), command: [ffmpeg, ...ff].join(' '), output_streams: encLines },
      audio: args.audio ? path.resolve(args.audio) : null,
      scene_errors: errors, missing_files: misses,
    };
    await fsp.writeFile(`${outFile}.safezone.json`, JSON.stringify(safeSidecar, null, 2));
    await fsp.writeFile(`${outFile}.cues.json`, JSON.stringify(cuesBeats, null, 2));
    await fsp.writeFile(`${outFile}.render.json`, JSON.stringify(renderSidecar, null, 2));
    if (!args['keep-frames']) await fsp.rm(framesDir, { recursive: true, force: true });

    console.log(`[done] ${outFile}`);
    console.log(`[done] frames ${n} (${from}..${to - 1}) | workers ${workers} | ${renderSidecar.seconds_per_frame} s/frame wall (${renderSidecar.seconds_per_frame_per_worker} s/frame per worker) | render ${renderSec.toFixed(1)}s, encode ${((tEnc - tRender) / 1000).toFixed(1)}s, total ${totalSec.toFixed(1)}s`);
    console.log(`[done] capture ${capture} ${captureDims?.w}x${captureDims?.h} | WebGL ${gpuLine}`);
    console.log(`[done] safe zone: ${violations.length} violations, ${fontViolations.length} font violations, min_font_px ${minFont}, min effective ${minEffFont} (${samples.length} samples)`);
    console.log(`[done] encoder: ${encLines.join(' | ')}`);
    if (errors.length) console.log(`[done] scene errors: ${errors.length} (listed in render.json)`);
    if (args['keep-frames']) console.log(`[done] frames kept in ${framesDir}`);
  } finally {
    await cleanup();
  }
}

main().then(() => process.exit(0)).catch((e) => {
  console.error(`[render] FAILED: ${e && e.message ? e.message : e}`);
  process.exit(1);
});
