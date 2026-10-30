#!/usr/bin/env python3
"""Builds a sound plan for mix_plan.py from a film's cue sheet and a folder of real recorded sounds.
usage: make_sound_plan.py --cues film.mp4.cues.json --sounds ~/motion-studio/sounds --out plan.json [--voice vo.wav] [--duration 38.6] [--seed 3]
Sounds folder layout: sounds/<cue type>/*.wav  (types the scene uses: pop whoosh wipe tick press ping thud hit word riser logo room glide bloom ...)
A cue type with no folder falls back to sounds/any. Variants are cycled so the same file never plays twice in a row.
Rules baked in (from the studio's tests): hits carry mids above 500 Hz so they survive a phone speaker: every 'thud'/'hit' gets a mid layer from
sounds/thud-mid or sounds/pop; voice goes on stem 4 and the bed is ducked 12 dB or more under it by mix_plan.py."""
import argparse, json, random, sys
from pathlib import Path
EXT = {'.wav', '.mp3', '.ogg', '.flac', '.aif', '.aiff'}
# type -> (stem, gain_db, align, pan)  stem 1 sub, 2 foley mids, 3 air and bed
MAP = {'room': (3, -4, 'start', 0), 'word': (2, -16, 'onset', 0), 'pop': (2, -9, 'onset', .15), 'whoosh': (2, -9, 'onset', -.4), 'wipe': (2, -8, 'onset', .3),
       'tick': (2, -11, 'onset', .2), 'press': (2, -9, 'onset', 0), 'ping': (2, -17, 'onset', -.3), 'thud': (1, -13, 'onset', 0), 'hit': (1, -12, 'onset', 0),
       'riser': (2, -9, 'end', 0), 'bloom': (2, -9, 'end', 0), 'swell': (2, -12, 'end', 0), 'logo': (1, -8, 'onset', 0), 'glide': (2, -18, 'onset', .3), 'zoom': (2, -8, 'onset', 0)}
ap = argparse.ArgumentParser(); ap.add_argument('--cues', required=True); ap.add_argument('--sounds', required=True); ap.add_argument('--out', required=True)
ap.add_argument('--voice'); ap.add_argument('--duration', type=float); ap.add_argument('--seed', type=int, default=3); a = ap.parse_args()
cues = json.load(open(a.cues)); cues = cues['cues'] if isinstance(cues, dict) else cues
root = Path(a.sounds).expanduser(); rnd = random.Random(a.seed)
def files(t):
    for d in (root / t, root / 'any'):
        f = sorted(p for p in d.rglob('*') if p.suffix.lower() in EXT) if d.exists() else []
        if f: return f
    return []
dur = a.duration or (max(c['t'] for c in cues) + 2.0)
ev, used, missing = [], {}, set()
if a.voice: ev.append({'time': 0.0, 'visual_event': 'voice', 'sfx_category': 'voice', 'file': str(Path(a.voice).expanduser().resolve()), 'stem': 4, 'pan': 0, 'gain_db': None, 'align': 'start', 'loop': False})
def add(t, typ, f, stem, gain, align, pan, note):
    e = {'time': round(t, 3), 'visual_event': f'{note} @ {t:.2f}', 'sfx_category': typ, 'file': str(f), 'stem': stem, 'pan': pan, 'gain_db': gain, 'align': align}
    if typ == 'room': e['loop'] = True
    ev.append(e)
for c in sorted(cues, key=lambda c: c['t']):
    typ = c['type']; fl = files(typ)
    if not fl: missing.add(typ); continue
    k = used.get(typ, 0); used[typ] = k + 1
    stem, gain, align, pan = MAP.get(typ, (2, -12, 'onset', 0))
    add(c['t'], typ, fl[(k + rnd.randrange(len(fl))) % len(fl)] if k == 0 else fl[(k + rnd.randrange(len(fl))) % len(fl)], stem, gain, align, pan, typ)
    if typ in ('thud', 'hit'):
        mid = files('thud-mid') or files('pop') or files('tick')
        if mid: add(c['t'], 'mid-layer', mid[k % len(mid)], 2, -5, 'onset', 0, 'mid layer')
json.dump({'schema': 'motion-film-studio/sound-plan@1', 'duration_s': round(dur, 3), 'events': ev}, open(a.out, 'w'), indent=1)
print(f'{len(ev)} events -> {a.out}; cue types with no sounds: {sorted(missing) or "none"}')
