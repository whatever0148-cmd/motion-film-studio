#!/usr/bin/env python3
"""flaw_scan.py: measure a finished video for the flaws that make viewers skip or flinch. numpy + ffmpeg only.

  ~/EmpireBrain/studio/.venv/bin/python -I flaw_scan.py VIDEO [--cues VIDEO.cues.json] [--safezone VIDEO.safezone.json] [--spec spec.json] [--out PREFIX]

Writes PREFIX.flaws.json and PREFIX.flaws.md (default PREFIX = VIDEO) and prints the markdown.
Each finding has an id (F01..F18), a severity (P0 blocker, P1 fix before shipping, P2 look at it), a time and a measured value.
Thresholds live in SPEC below and can be overridden with --spec (a json file with the same keys). They are production targets, not laws of nature:
the skill that owns this script (video-flaw-scanner) says where each one comes from and when it was last checked.
Nothing here listens or looks like a human does. It measures; a person or the Skip-Psychology Analyst judges.
"""
import argparse
import json
import math
import os
import re
import subprocess
import sys

import numpy as np

import shutil as _sh
FF = _sh.which('ffmpeg') or os.path.expanduser('~/.local/bin/ffmpeg')
SPEC = {
    'fps': 60,                      # F17 expected frame rate (None to skip)
    'width_height': None,           # F17 expected [w, h], e.g. [1920, 1080] or [1080, 1920]; None = report only
    'first_change_max_s': 0.35,     # F02 something must visibly change by this time
    'first_second_energy_min': 1.2, # F03 mean motion energy (0..255 scale of mean abs frame diff) in the first second
    'flash_luma_jump': 9.0,         # F04 a one-frame excursion of the mean luma (0..255) this large and back
    'stutter_prev_min': 0.6,        # F05 motion before and after a frozen frame
    'static_hold_max_s': 1.4,       # F06 longest allowed run with no visible change
    'event_gap_max_s': 2.6,         # F07 longest allowed gap between visible events (cuts, wipes, strong motion)
    'contrast_p98_p2_min': 70.0,    # F08 per-frame luma spread (2nd to 98th percentile) below this counts as flat
    'lufs_target': -14.0,           # F09
    'lufs_tolerance': 1.5,
    'true_peak_max': -1.0,          # F10 dBTP
    'level_jump_lu': 9.0,           # F11 momentary loudness rise inside 0.5 s
    'silence_noise_db': -48,        # F12
    'silence_gap_max_s': 0.6,       # F12 silence inside the film (not at the ends)
    'clip_fraction_max': 0.0002,    # F13 share of samples at or above 0.99 full scale
    'audio_first_onset_max_s': 0.6, # F14
    'cue_sync_window_s': 0.12,      # F15 an audio onset must sit this close to a cue
    'cue_sync_miss_max': 0.15,      # F15 share of cues allowed without an onset
    'loop_mse_max': 120.0,          # F18 mean squared difference between first and last frame (0..255^2)
}
CUE_TYPES = {'thud', 'wipe', 'bloom', 'cloud', 'flower', 'zoom', 'hit', 'whoosh', 'tick', 'ping', 'strike', 'press', 'chip', 'logo', 'pop', 'whip', 'cloud'}


def run(cmd, text=False):
    return subprocess.run(cmd, capture_output=True, text=text)


def probe(path):
    err = run([FF, '-hide_banner', '-nostdin', '-i', path], text=True).stderr
    info = {}
    m = re.search(r'Duration: (\d+):(\d+):([\d.]+)', err)
    if m:
        info['duration_s'] = int(m[1]) * 3600 + int(m[2]) * 60 + float(m[3])
    v = re.search(r'Stream #\d+:\d+.*?Video: (\w+).*?, (\d{2,5})x(\d{2,5})', err)
    if v:
        info.update(vcodec=v[1], width=int(v[2]), height=int(v[3]))
    f = re.search(r'([\d.]+) fps', err)
    if f:
        info['fps'] = float(f[1])
    b = re.search(r'bitrate: (\d+) kb/s', err)
    if b:
        info['bitrate_kbps'] = int(b[1])
    a = re.search(r'Audio: (\w+).*?, (\d+) Hz, (\w+)', err)
    if a:
        info.update(acodec=a[1], sample_rate=int(a[2]), channels=a[3])
    info['has_audio'] = 'Audio:' in err
    return info


def decode_frames(path, fps, w=320, h=180):
    raw = run([FF, '-v', 'error', '-nostdin', '-i', path, '-vf', f'fps={fps},scale={w}:{h}:flags=area,format=gray', '-f', 'rawvideo', '-']).stdout
    return np.frombuffer(raw, dtype=np.uint8).reshape(-1, h, w)


def decode_audio(path, sr=22050):
    raw = run([FF, '-v', 'error', '-nostdin', '-i', path, '-vn', '-ac', '1', '-ar', str(sr), '-f', 'f32le', '-']).stdout
    return np.frombuffer(raw, dtype='<f4')


def runs(mask, fps, min_len_s):
    out, i, n = [], 0, len(mask)
    while i < n:
        if mask[i]:
            j = i
            while j < n and mask[j]:
                j += 1
            if (j - i) / fps >= min_len_s:
                out.append((i / fps, j / fps))
            i = j
        else:
            i += 1
    return out


def video_findings(path, info, spec, fl):
    FPS = 60
    F = decode_frames(path, FPS)
    n = len(F)
    L = F.reshape(n, -1).mean(axis=1)
    D = np.zeros(n)
    D[1:] = np.abs(F[1:].astype(np.int16) - F[:-1].astype(np.int16)).reshape(n - 1, -1).mean(axis=1)
    t = lambda i: round(i / FPS, 3)
    m = {'frames_analysed': n, 'mean_luma': round(float(L.mean()), 1), 'median_motion_energy': round(float(np.median(D)), 3)}
    # F01 blank first frame, F02 slow start, F03 low first-second energy
    spread0 = float(np.percentile(F[0], 95) - np.percentile(F[0], 5))
    m['first_frame_contrast'] = round(spread0, 1)
    if spread0 < 12:
        fl('F01', 'P1', 0.0, spread0, 'the first frame is nearly blank (luma spread %.1f)' % spread0)
    ch = np.where(D > 0.5)[0]
    first = float(ch[0] / FPS) if len(ch) else None
    m['first_visible_change_s'] = None if first is None else round(first, 3)
    if first is None or first > spec['first_change_max_s']:
        fl('F02', 'P1', first or 0.0, first, 'nothing visibly changes until %s s' % ('never' if first is None else '%.2f' % first))
    e1 = float(D[1:FPS].mean()) if n > FPS else 0.0
    m['first_second_motion_energy'] = round(e1, 3)
    if e1 < spec['first_second_energy_min']:
        fl('F03', 'P1', 0.0, e1, 'the first second barely moves (energy %.2f, target at least %.1f)' % (e1, spec['first_second_energy_min']))
    # F04 single-frame flash
    for i in range(1, n - 1):
        a, b = L[i] - L[i - 1], L[i + 1] - L[i]
        if abs(a) > spec['flash_luma_jump'] and abs(b) > spec['flash_luma_jump'] and a * b < 0 and abs(L[i + 1] - L[i - 1]) < 0.4 * abs(a):
            fl('F04', 'P0', t(i), round(float(abs(a)), 1), 'one-frame flash: mean luma jumps %.1f and comes back' % abs(a))
    # F05 frozen frame inside motion
    for i in range(4, n - 4):
        if D[i] < 0.02 and D[i - 3:i].mean() > spec['stutter_prev_min'] and D[i + 1:i + 4].mean() > spec['stutter_prev_min']:
            fl('F05', 'P0', t(i), round(float(D[i - 3:i].mean()), 2), 'duplicate or frozen frame inside moving footage (stutter)')
    # F06 static holds
    still = D < 0.05
    for s0, s1 in runs(still, FPS, spec['static_hold_max_s']):
        fl('F06', 'P2', round(s0, 2), round(s1 - s0, 2), 'nothing changes for %.1f s' % (s1 - s0))
    m['longest_static_hold_s'] = max([b - a for a, b in runs(still, FPS, 0.2)] or [0.0])
    # F07 event spacing: peaks of motion energy, merged inside 0.25 s
    thr = max(3 * float(np.median(D)), 1.5)
    ev = []
    for i in range(1, n - 1):
        if D[i] > thr and D[i] >= D[i - 1] and D[i] >= D[i + 1] and (not ev or i / FPS - ev[-1] > 0.25):
            ev.append(i / FPS)
    gaps = [b - a for a, b in zip([0.0] + ev, ev + [n / FPS])]
    m['visual_events'] = len(ev)
    m['max_gap_between_events_s'] = round(max(gaps), 2) if gaps else None
    m['mean_gap_between_events_s'] = round(float(np.mean(gaps)), 2) if gaps else None
    if gaps and max(gaps) > spec['event_gap_max_s']:
        k = int(np.argmax(gaps))
        start = ([0.0] + ev)[k]
        fl('F07', 'P1', round(start, 2), round(max(gaps), 2), 'no visible event for %.1f s (limit %.1f)' % (max(gaps), spec['event_gap_max_s']))
    # F08 low-contrast frames (sampled)
    flat = []
    for i in range(0, n, 12):
        sp = float(np.percentile(F[i], 98) - np.percentile(F[i], 2))
        if sp < spec['contrast_p98_p2_min']:
            flat.append(i / FPS)
    m['flat_contrast_samples'] = len(flat)
    for s0, s1 in _merge(flat, 0.3):
        fl('F08', 'P2', round(s0, 2), round(s1 - s0, 2), 'flat, low-contrast stretch (luma spread under %.0f)' % spec['contrast_p98_p2_min'])
    # F18 loop seam
    mse = float(np.mean((F[0].astype(np.float32) - F[-1].astype(np.float32)) ** 2))
    m['loop_seam_mse'] = round(mse, 1)
    if mse > spec['loop_mse_max']:
        fl('F18', 'P2', round(n / FPS, 2), round(mse, 1), 'last frame differs from the first (loop seam mse %.0f); fine if the film is not meant to loop' % mse)
    m['motion_energy_per_second'] = [round(float(D[i:i + FPS].mean()), 2) for i in range(0, n, FPS)]
    return m


def _merge(times, gap):
    out = []
    for x in times:
        if out and x - out[-1][1] <= gap:
            out[-1][1] = x
        else:
            out.append([x, x])
    return [(a, b + 0.2) for a, b in out]


def audio_findings(path, info, spec, fl, cues):
    m = {}
    e = run([FF, '-hide_banner', '-nostdin', '-i', path, '-vn', '-af', 'ebur128=peak=true', '-f', 'null', '-'], text=True).stderr
    i_m = re.findall(r'\n\s+I:\s+(-?[\d.]+) LUFS', e)
    p_m = re.findall(r'\n\s+Peak:\s+(-?[\d.]+) dBFS', e)
    lra = re.findall(r'\n\s+LRA:\s+(-?[\d.]+) LU', e)
    M = [(float(a), float(b)) for a, b in re.findall(r't:\s*([\d.]+)\s+TARGET:-?\d+ LUFS\s+M:\s*(-?[\d.]+)', e)]
    if i_m:
        m['integrated_lufs'] = float(i_m[-1])
        if abs(m['integrated_lufs'] - spec['lufs_target']) > spec['lufs_tolerance']:
            fl('F09', 'P1', 0.0, m['integrated_lufs'], 'integrated loudness %.1f LUFS, target %.0f +/- %.1f' % (m['integrated_lufs'], spec['lufs_target'], spec['lufs_tolerance']))
    if p_m:
        m['true_peak_dbtp'] = float(p_m[-1])
        if m['true_peak_dbtp'] > spec['true_peak_max']:
            fl('F10', 'P0', 0.0, m['true_peak_dbtp'], 'true peak %.1f dBTP is above %.1f' % (m['true_peak_dbtp'], spec['true_peak_max']))
    if lra:
        m['lra_lu'] = float(lra[-1])
    # F11 sudden rise of momentary loudness inside 0.5 s (skip the first 0.6 s: a fade-in is fine)
    if M:
        tt = np.array([a for a, _ in M])
        mm = np.array([b for _, b in M])
        mm = np.where(mm < -70, -70, mm)
        step = 5
        last = -9
        for k in range(step, len(mm)):
            if tt[k] > 0.6 and mm[k] - mm[k - step] > spec['level_jump_lu'] and mm[k - step] > -50 and tt[k] - last > 1.0:
                fl('F11', 'P1' if mm[k - step] >= -26 else 'P2', round(float(tt[k - step]), 2), round(float(mm[k] - mm[k - step]), 1), 'loudness jumps %.1f LU in 0.5 s, from %.0f LUFS (%s)' % (mm[k] - mm[k - step], mm[k - step], 'a flinch' if mm[k - step] >= -26 else 'out of a pause, usually speech starting'))
                last = tt[k]
    # F12 silence gaps, F14 late audio start
    s = run([FF, '-hide_banner', '-nostdin', '-i', path, '-vn', '-af', 'silencedetect=noise=%ddB:d=0.3' % spec['silence_noise_db'], '-f', 'null', '-'], text=True).stderr
    starts = [float(x) for x in re.findall(r'silence_start: ([\d.]+)', s)]
    ends = re.findall(r'silence_end: ([\d.]+) \| silence_duration: ([\d.]+)', s)
    dur = info.get('duration_s', 0)
    first_onset = 0.0
    if starts and starts[0] < 0.05 and ends:
        first_onset = float(ends[0][0])
    m['audio_first_onset_s'] = round(first_onset, 2)
    if first_onset > spec['audio_first_onset_max_s']:
        fl('F14', 'P1', 0.0, first_onset, 'sound only starts at %.2f s' % first_onset)
    for a, (b, d) in zip(starts, ends):
        d = float(d)
        if a > 0.5 and float(b) < dur - 0.6 and d > spec['silence_gap_max_s']:
            fl('F12', 'P1', round(a, 2), round(d, 2), 'silence for %.2f s inside the film' % d)
    # F13 clipping, F15 cue sync
    raw2 = run([FF, '-v', 'error', '-nostdin', '-i', path, '-vn', '-ac', '2', '-ar', '48000', '-f', 'f32le', '-']).stdout
    st = np.frombuffer(raw2, dtype='<f4')
    x = decode_audio(path)
    m['sample_peak'] = round(float(np.abs(st).max()), 3) if len(st) else None
    if len(x):
        cf = float((np.abs(st) >= 0.99).mean()) if len(st) else 0.0
        m['clip_fraction'] = round(cf, 6)
        if cf > spec['clip_fraction_max']:
            fl('F13', 'P0', 0.0, cf, '%.3f %% of samples sit at full scale (clipping)' % (cf * 100))
        if cues:
            sr = 22050
            n_fft, hop = 512, 128
            w = np.hanning(n_fft).astype(np.float32)
            nfr = 1 + (len(x) - n_fft) // hop
            fr = np.lib.stride_tricks.sliding_window_view(x, n_fft)[::hop][:nfr] * w
            S = np.abs(np.fft.rfft(fr, axis=1))
            flux = np.maximum(0, np.log1p(10 * S[1:]) - np.log1p(10 * S[:-1])).sum(axis=1)
            thr = np.percentile(flux, 80)
            peaks = [i for i in range(1, len(flux) - 1) if flux[i] > thr and flux[i] >= flux[i - 1] and flux[i] >= flux[i + 1]]
            pt = np.array([(p * hop + n_fft / 2) / sr for p in peaks])
            offs, miss = [], []
            for c in cues:
                if c['type'] not in CUE_TYPES:
                    continue
                d = pt - c['t']
                if len(d) and np.abs(d).min() <= spec['cue_sync_window_s']:
                    offs.append(float(d[np.abs(d).argmin()]))
                else:
                    miss.append(c)
            tot = len(offs) + len(miss)
            m['cue_sync'] = {'cues': tot, 'with_onset': len(offs), 'median_offset_ms': round(float(np.median(offs)) * 1000) if offs else None, 'p90_abs_offset_ms': round(float(np.percentile(np.abs(offs), 90)) * 1000) if offs else None}
            if tot and len(miss) / tot > spec['cue_sync_miss_max']:
                fl('F15', 'P1', round(miss[0]['t'], 2), len(miss), '%d of %d visual cues have no audio onset within %.0f ms (first: %s at %.2f s)' % (len(miss), tot, spec['cue_sync_window_s'] * 1000, miss[0]['type'], miss[0]['t']))
    return m


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('video')
    ap.add_argument('--cues')
    ap.add_argument('--safezone')
    ap.add_argument('--spec')
    ap.add_argument('--out')
    a = ap.parse_args()
    spec = dict(SPEC)
    if a.spec:
        spec.update(json.load(open(a.spec)))
    prefix = a.out or a.video
    cues_p = a.cues or (a.video + '.cues.json')
    sz_p = a.safezone or (a.video + '.safezone.json')
    findings = []

    def fl(fid, sev, t, value, msg):
        findings.append({'id': fid, 'severity': sev, 'time_s': t, 'value': value, 'message': msg})

    info = probe(a.video)
    if spec['fps'] and info.get('fps') and abs(info['fps'] - spec['fps']) > 0.5:
        fl('F17', 'P0', 0.0, info['fps'], 'frame rate %.2f, expected %s' % (info['fps'], spec['fps']))
    if spec['width_height'] and (info.get('width'), info.get('height')) != tuple(spec['width_height']):
        fl('F17', 'P0', 0.0, [info.get('width'), info.get('height')], 'size %sx%s, expected %s' % (info.get('width'), info.get('height'), spec['width_height']))
    metrics = {'file': os.path.abspath(a.video), 'probe': info}
    metrics['video'] = video_findings(a.video, info, spec, fl)
    cues = json.load(open(cues_p)).get('cues', []) if os.path.exists(cues_p) else []
    if info.get('has_audio'):
        metrics['audio'] = audio_findings(a.video, info, spec, fl, cues)
    else:
        fl('F14', 'P1', 0.0, None, 'the file has no audio track')
    if os.path.exists(sz_p):
        sz = json.load(open(sz_p))
        v = sz.get('violations', [])
        fv = sz.get('font_violations', [])
        metrics['safezone'] = {'violations': len(v), 'font_violations': len(fv), 'min_font_px': sz.get('min_font_px')}
        for x in v[:12]:
            fl('F16', 'P1', x.get('t'), x.get('overflow_px'), 'text box %s leaves the safe zone' % x.get('id'))
        for x in fv[:12]:
            fl('F16', 'P0', x.get('t'), x.get('fontPx') or x.get('px'), 'text under the minimum size')
    order = {'P0': 0, 'P1': 1, 'P2': 2}
    findings.sort(key=lambda f: (order[f['severity']], f['time_s'] or 0))
    verdict = 'FAIL' if any(f['severity'] == 'P0' for f in findings) else ('FIX' if any(f['severity'] == 'P1' for f in findings) else 'PASS')
    rep = {'verdict': verdict, 'counts': {k: sum(1 for f in findings if f['severity'] == k) for k in order}, 'spec': spec, 'metrics': metrics, 'findings': findings}
    json.dump(rep, open(prefix + '.flaws.json', 'w'), indent=1, default=float)
    md = ['# Flaw scan: %s' % os.path.basename(a.video), '', 'Verdict: **%s**  (P0 %d, P1 %d, P2 %d)' % (verdict, rep['counts']['P0'], rep['counts']['P1'], rep['counts']['P2']), '']
    v, au = metrics['video'], metrics.get('audio', {})
    md += ['| measure | value |', '|---|---|', '| size and fps | %sx%s at %s fps, %s kb/s |' % (info.get('width'), info.get('height'), info.get('fps'), info.get('bitrate_kbps')),
           '| first visible change | %s s |' % v.get('first_visible_change_s'), '| first-second motion energy | %s |' % v.get('first_second_motion_energy'),
           '| visual events, max gap | %s events, %s s |' % (v.get('visual_events'), v.get('max_gap_between_events_s')), '| longest static hold | %.2f s |' % v.get('longest_static_hold_s'),
           '| loudness | %s LUFS, true peak %s dBTP, LRA %s |' % (au.get('integrated_lufs'), au.get('true_peak_dbtp'), au.get('lra_lu')),
           '| cue sync | %s |' % json.dumps(au.get('cue_sync')), '| safe zone | %s |' % json.dumps(metrics.get('safezone')), '']
    md += ['## Findings', ''] + (['| id | sev | time | measured | what |', '|---|---|---|---|---|'] + ['| %s | %s | %s | %s | %s |' % (f['id'], f['severity'], f['time_s'], f['value'], f['message']) for f in findings] if findings else ['none'])
    open(prefix + '.flaws.md', 'w').write('\n'.join(md) + '\n')
    print('\n'.join(md))
    return 0 if verdict == 'PASS' else 1


if __name__ == '__main__':
    sys.exit(main())
