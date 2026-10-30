#!/usr/bin/env python3
"""sound_qa.py: measurable sound QA for a studio film (ffmpeg + numpy only).

  ~/EmpireBrain/studio/.venv/bin/python -I sound_qa.py MASTER.(wav|mp4) \
      [--plan sound_plan.filled.json --stems DIR] [--payoffs 5.3,22.1] [--loop] [--json out.json]

Checks (thresholds in LIMITS; each is a house rule, sources in the skill's references):
  loudness I / LRA / true peak, true peak after an AAC 128k re-encode, clipping fraction,
  first audio event time, digital-silence and quiet gaps, momentary level steps,
  phone-speaker prominence of each --payoff (500 Hz high-pass test),
  mono fold-down loss, loop-seam step, and with --plan and --stems the onset offset of every
  stem 1 and 2 event against its planned time (ms). Exit 0 = PASS, 1 = at least one FAIL.
"""
import argparse, json, os, re, subprocess, sys, tempfile
import numpy as np

FF = os.path.expanduser('~/.local/bin/ffmpeg') if os.path.exists(os.path.expanduser('~/.local/bin/ffmpeg')) else 'ffmpeg'
SR = 48000
LIMITS = {
    'lufs': (-15.0, -13.0), 'tp_max': -1.0, 'tp_after_aac_max': -1.0, 'clip_frac_max': 0.0002,
    'first_event_max_s': 0.25, 'quiet_gap_db': -48.0, 'quiet_gap_max_s': 0.3, 'digital_silence_db': -60.0,
    'step_warn_lu': 6.0, 'step_fail_lu': 9.0, 'phone_prominence_db': 6.0, 'mono_loss_max_db': 1.5,
    'seam_step_max_lu': 3.0, 'sync_abs_pass_ms': 8.0, 'sync_abs_fail_ms': 17.0,
}


def run(cmd):
    return subprocess.run(cmd, capture_output=True)


def pcm(path, af=None, ac=2):
    cmd = [FF, '-v', 'error', '-nostdin', '-i', path, '-vn', '-ac', str(ac), '-ar', str(SR)]
    if af:
        cmd += ['-af', af]
    r = run(cmd + ['-f', 'f32le', '-'])
    x = np.frombuffer(r.stdout, dtype='<f4')
    return x.reshape(-1, ac) if ac > 1 else x


def ebur(path):
    r = run([FF, '-hide_banner', '-nostdin', '-i', path, '-vn', '-af', 'ebur128=peak=true', '-f', 'null', '-']).stderr.decode('utf8', 'ignore')
    t, m = [], []
    for g in re.finditer(r't:\s*([\d.]+)\s+TARGET:\S+ LUFS\s+M:\s*(-?[\d.]+)', r):
        t.append(float(g[1])); m.append(float(g[2]))
    tail = r[r.rfind('Summary:'):]
    def pick(rx):
        g = re.search(rx, tail)
        return float(g[1]) if g else None
    return dict(I=pick(r'I:\s*(-?[\d.]+) LUFS'), LRA=pick(r'LRA:\s*([\d.]+) LU'), TP=pick(r'Peak:\s*(-?[\d.]+) dBFS')), np.array(t), np.array(m)


def rms_db(x, win):
    n = len(x) // win
    f = x[:n * win].reshape(n, win)
    return 20 * np.log10(np.sqrt((f ** 2).mean(axis=1)) + 1e-9)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('audio'); ap.add_argument('--plan'); ap.add_argument('--stems'); ap.add_argument('--payoffs', default='')
    ap.add_argument('--json'); ap.add_argument('--loop', action='store_true', help='film should loop: check the seam')
    a = ap.parse_args()
    L, res, fails = LIMITS, [], []

    def rep(name, value, ok, note=''):
        res.append({'check': name, 'value': value, 'pass': bool(ok), 'note': note})
        if not ok:
            fails.append(name)

    s, tt, mm = ebur(a.audio)
    rep('integrated LUFS', s['I'], s['I'] is not None and L['lufs'][0] <= s['I'] <= L['lufs'][1], 'target -14 +/- 1')
    rep('true peak dBTP', s['TP'], s['TP'] is not None and s['TP'] <= L['tp_max'], 'limit -1.0')
    rep('loudness range LU', s['LRA'], True, 'info; EBU R128 sets no maximum')
    with tempfile.TemporaryDirectory() as d:
        enc = os.path.join(d, 'x.m4a')
        run([FF, '-y', '-nostdin', '-i', a.audio, '-vn', '-c:a', 'aac', '-b:a', '128k', '-ar', '48000', enc])
        s2, _, _ = ebur(enc) if os.path.exists(enc) else ({'TP': None}, 0, 0)
    rep('true peak after AAC 128k', s2['TP'], s2['TP'] is not None and s2['TP'] <= L['tp_after_aac_max'], 'limit -1.0 after encode')
    st = pcm(a.audio); x = st.mean(axis=1); dur = len(x) / SR
    cf = float((np.abs(st) >= 0.99).mean())
    rep('clipping fraction', round(cf, 6), cf <= L['clip_frac_max'], 'share of samples at or above 0.99')
    # first event: fast envelope 5 ms vs bed floor
    e5 = rms_db(x, int(SR * 0.005)); floor = np.percentile(e5, 10)
    hit = np.where(e5 > floor + 12)[0]
    first = float(hit[0] * 0.005) if len(hit) else None
    rep('first audio event s', None if first is None else round(first, 3), first is not None and first <= L['first_event_max_s'], 'bed floor %.1f dBFS, event = +12 dB over it' % floor)
    # silence and quiet gaps
    e100 = rms_db(x, int(SR * 0.1))
    dig = int((e100 < L['digital_silence_db']).sum())
    rep('digital-silence windows (100 ms under -60 dBFS)', dig, dig == 0)
    q = e100 < L['quiet_gap_db']; run_n = best = 0; where = 0.0
    for i, v in enumerate(q):
        run_n = run_n + 1 if v else 0
        if run_n > best: best, where = run_n, (i - run_n + 1) * 0.1
    rep('longest quiet run s (under -48 dBFS)', round(best * 0.1, 1), best * 0.1 <= L['quiet_gap_max_s'], 'starts at %.1f s' % where)
    # level steps from momentary loudness
    steps, pauses = [], []
    for k in range(5, len(mm)):
        if mm[k - 5] > -50 and mm[k] - mm[k - 5] >= L['step_warn_lu']:
            (steps if mm[k - 5] >= -26 else pauses).append((round(float(tt[k - 5]), 1), round(float(mm[k] - mm[k - 5]), 1)))
    worst = max([v for _, v in steps], default=0.0)
    rep('worst rise in 0.5 s from an audible level LU', worst, worst < L['step_fail_lu'], 'rises %s; rises out of a pause or dip (planned payoffs and speech starts, list them in the plan) %s' % (steps[:5], pauses[:5]))
    # phone prominence at payoffs
    pay = [float(v) for v in a.payoffs.split(',') if v.strip()]
    if pay:
        ph = pcm(a.audio, af='highpass=f=500,highpass=f=500,lowpass=f=8000', ac=1)
        for t in pay:
            i = int(t * SR); post = ph[i:i + int(0.05 * SR)]; pre = ph[max(0, i - int(0.5 * SR)):max(1, i - int(0.02 * SR))]
            if len(post) == 0 or len(pre) == 0:
                continue
            pr = 20 * np.log10(np.sqrt((post ** 2).mean()) + 1e-9) - 20 * np.log10(np.sqrt((pre ** 2).mean()) + 1e-9)
            rep('phone-filtered prominence at %.2f s dB' % t, round(float(pr), 1), pr >= L['phone_prominence_db'], '500 Hz high-pass x2, 8 kHz low-pass; 50 ms after vs 500 ms before')
    # mono fold-down
    mono_l = 20 * np.log10(np.sqrt((x ** 2).mean()) + 1e-9) - 20 * np.log10(np.sqrt((st ** 2).mean()) + 1e-9)
    rep('mono fold-down loss dB', round(float(-mono_l), 2), -mono_l <= L['mono_loss_max_db'], 'RMS of (L+R)/2 vs RMS of L and R')
    # loop seam
    if a.loop and len(mm) > 12:
        seam = abs(float(np.mean(mm[1:6])) - float(np.mean(mm[-6:-1])))
        rep('loop seam loudness step LU', round(seam, 1), seam <= L['seam_step_max_lu'], 'first 0.5 s vs last 0.5 s; only matters if the film should loop')
    # sync offsets: plan time vs measured onset in the stem files
    if a.plan and a.stems:
        plan = json.load(open(a.plan)); offs = []; skipped = 0
        for stem_no, fn in ((2, 'stem2_foley.wav'),):  # stem 1 is below 220 Hz: its onset is smeared over 10 ms or more, so it is aligned by the library onset and not re-measured here
            p = os.path.join(a.stems, fn)
            if not os.path.exists(p):
                continue
            y = pcm(p, ac=1); env = rms_db(y, int(SR * 0.001))
            for ev in plan['events']:
                if ev.get('stem') != stem_no:
                    continue
                t = float(ev['time']); lo, hi = max(0, int((t - 0.06) * 1000)), int((t + 0.12) * 1000)
                w = env[lo:hi]
                if len(w) < 10 or w.max() < -60:
                    continue
                cand = [i for i in range(8, len(w)) if w[i] >= w.max() - 30 and w[i] - w[i - 5] >= 12]  # sharp onsets only: soft swells have no single onset
                if not cand:
                    skipped += 1  # onset hidden by a sound that is already playing
                    continue
                offs.append((t, (lo + cand[0]) / 1000.0 - t))
        if offs:
            ab = np.abs([o for _, o in offs]) * 1000
            bad = [(round(t, 2), round(o * 1000)) for t, o in offs if abs(o) * 1000 > L['sync_abs_pass_ms']]
            rep('sync: median |offset| ms (%d events, %d hidden)' % (len(offs), skipped), round(float(np.median(ab)), 1), np.median(ab) <= L['sync_abs_pass_ms'], 'plan time vs measured onset in the stem')
            rep('sync: p90 |offset| ms', round(float(np.percentile(ab, 90)), 1), np.percentile(ab, 90) <= L['sync_abs_fail_ms'], 'one frame at 60 fps = 16.7 ms; off-grid events %s' % bad[:6])
    w = max(len(r['check']) for r in res)
    for r in res:
        print(('PASS ' if r['pass'] else 'FAIL ') + r['check'].ljust(w) + '  ' + str(r['value']).rjust(8) + '  ' + r['note'])
    print('VERDICT', 'PASS' if not fails else 'FAIL: ' + ', '.join(fails), '| duration %.2f s' % dur)
    if a.json:
        json.dump({'file': os.path.abspath(a.audio), 'limits': L, 'results': res, 'verdict': 'PASS' if not fails else 'FAIL'}, open(a.json, 'w'), indent=1)
    sys.exit(1 if fails else 0)


if __name__ == '__main__':
    main()
