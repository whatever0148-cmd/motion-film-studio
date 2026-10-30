#!/usr/bin/env python3
"""mix_plan.py: reference 4-stem mixer for a filled sound_plan.json (ffmpeg only).

    ~/EmpireBrain/studio/.venv/bin/python -I tools/mix_plan.py PLAN.json --out-dir DIR [--print-graph]

Stems (see doc 03 in wiki/motion-design-kb):
  1 sub / low impact      highpass 28 Hz, lowpass 220 Hz, not ducked
  2 tactile mid foley     highpass 120 Hz, -3 dB at 2.5 kHz for the voice, ducked ~2 dB by the voice
  3 air / texture / bed   highpass 200 Hz, ducked ~8 dB by the voice, must never be silent
  4 voice                 highpass 80 Hz, compressor 3:1, set to -18 LUFS before the master
  5 music bed (optional)  only with --music FILE: highpass 50 Hz, -4 dB at 1.8 kHz, ducked ~6 dB by the voice (slower release)

Master: amix of the 4 stems (normalize=0) -> volume to -14 LUFS + alimiter at -1.5 dBFS
-> loudnorm two-pass (I=-14, TP=-1, linear) -> 48 kHz 24-bit WAV, then measured with ebur128.

Plan fields per event: time (s), visual_event, sfx_category, file (library-relative or
absolute), gain_db, pan (-1..1), stem (1-4). Optional: align ("onset" default for stems
1-2: the file's measured onset lands on `time`; "start"; "end": the file ends on `time`,
for risers), loop (true: repeat to the end; default true only for vinyl-crackle-room-tone
beds), max_len_s, fade_out_s.
Top level: duration_s (required), events. Writes stem1..4.wav, premaster.wav, master.wav,
mix_report.json and filtergraph.txt into --out-dir.
"""
import argparse
import json
import math
import re
import subprocess
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sfxlib  # noqa: E402

LIB = Path(__file__).resolve().parent.parent
TARGET_I, TARGET_TP = -14.0, -1.0
VOICE_LUFS = -18.0
STEM_FILTERS = {
    1: "highpass=f=28,lowpass=f=220",
    2: "highpass=f=120,equalizer=f=2500:t=q:w=1:g=-3",
    3: "highpass=f=200",
    4: "highpass=f=80,acompressor=threshold=-20dB:ratio=3:attack=5:release=80:makeup=1",
    5: "highpass=f=50,equalizer=f=1800:t=q:w=0.7:g=-4",   # music bed: no sub rumble, a 4 dB dip where the voice lives
}
DUCK = {  # sidechaincompress settings, voice is the key input
    2: "sidechaincompress=threshold=0.063:ratio=2:attack=10:release=250",
    3: "sidechaincompress=threshold=0.02:ratio=20:attack=15:release=400",
    5: "sidechaincompress=threshold=0.025:ratio=12:attack=15:release=450",
}


def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(f"command failed ({r.returncode}): {' '.join(cmd[:6])} ...\n{r.stderr[-1500:]}")
    return r.stderr


def resolve(f):
    p = Path(str(f)).expanduser()
    return p if p.is_absolute() else LIB / p


def pan_expr(p, ch):
    p = max(-1.0, min(1.0, float(p)))
    if ch == 1:  # equal-power pan law (-3 dB in each side at centre)
        a = (p + 1) * math.pi / 4
        return f"pan=stereo|c0={math.cos(a):.4f}*c0|c1={math.sin(a):.4f}*c0"
    gl = 1.0 if p <= 0 else 1.0 - p  # balance for stereo sources
    gr = 1.0 if p >= 0 else 1.0 + p
    return f"pan=stereo|c0={gl:.4f}*c0|c1={gr:.4f}*c1"


def build(plan, voice_trim_db=0.0, music=None):
    D = float(plan["duration_s"])
    events = sorted(plan["events"], key=lambda e: float(e["time"]))
    inputs, chains, by_stem, notes = [], [], {1: [], 2: [], 3: [], 4: [], 5: []}, []
    stems_on = (1, 2, 3, 4, 5) if music else (1, 2, 3, 4)
    for k, ev in enumerate(events):
        stem = int(ev["stem"])
        path = resolve(ev["file"])
        if not path.exists():
            raise FileNotFoundError(path)
        info = sfxlib.probe(path)
        ch = info["channels"] if isinstance(info["channels"], int) else 2
        dur = len(sfxlib.decode_mono(path)) / sfxlib.ANALYSIS_SR
        # only beds loop by default; a riser on stem 3 plays once
        loop = bool(ev.get("loop", ev.get("sfx_category") == "vinyl-crackle-room-tone"))
        gain = ev.get("gain_db")
        if stem == 4 and gain is None:
            i_val = sfxlib.measure_loudness(path)["integrated_lufs"]
            gain = round(VOICE_LUFS - i_val, 2) if i_val is not None else 0.0
            notes.append(f"voice {path.name}: measured {i_val} LUFS, gain {gain} dB to reach {VOICE_LUFS}")
        gain = float(gain or 0.0)
        align = ev.get("align", "onset" if stem in (1, 2) else "start")
        onset = float(ev.get("file_onset_s") or 0.0) if align == "onset" else 0.0
        if align == "onset" and "file_onset_s" not in ev:
            x = sfxlib.decode_mono(path)
            onset = sfxlib.features(x).get("onset_s") or 0.0
        start = float(ev["time"]) - (dur if align == "end" else onset)
        idx = sum(1 for x in inputs if x == "-i")  # ffmpeg input index of this file
        inputs += (["-stream_loop", "-1"] if loop else []) + ["-i", str(path)]
        f = [f"[{idx}:a]aresample=48000"]
        head = max(0.0, -start)
        length = D - max(0.0, start)
        if ev.get("max_len_s"):
            length = min(length, float(ev["max_len_s"]))
        if not loop:
            length = min(length, dur - head)
        if length <= 0:
            notes.append(f"event {k} at {ev['time']} s falls outside the timeline, skipped")
            continue
        f.append(f"atrim=start={head:.4f}:duration={length:.4f},asetpts=PTS-STARTPTS")
        fo = ev.get("fade_out_s") or (0.5 if loop else 0.0)
        if fo:
            f.append(f"afade=t=out:st={max(0.0, length - fo):.4f}:d={fo:.4f}")
        if loop:
            f.append("afade=t=in:d=0.05")
        f.append(pan_expr(ev.get("pan", 0), ch))
        f.append(f"volume={gain:.2f}dB")
        ms = int(round(max(0.0, start) * 1000))
        if ms:
            f.append(f"adelay=delays={ms}:all=1")
        label = f"e{k}"
        chains.append(",".join(f) + f"[{label}]")
        by_stem[stem].append(label)
    if music:  # one full-length music bed on its own stem (kept out of the sound plan so pick.py never has to licence-check it)
        idx = sum(1 for x in inputs if x == "-i")
        inputs += ["-i", str(music["file"])]
        fo = float(music.get("fade_out_s", 1.5))
        chains.append(f"[{idx}:a]aresample=48000,atrim=0:{D:.4f},asetpts=PTS-STARTPTS,"
                      f"afade=t=out:st={max(0.0, D - fo):.4f}:d={fo:.4f},volume={float(music.get('gain_db', 0.0)):.2f}dB[ms]")
        by_stem[5].append("ms")
        notes.append(f"music bed {Path(music['file']).name} on stem 5 at {float(music.get('gain_db', 0.0)):.2f} dB")
    # silent stereo source so every stem has the full length even when empty
    inputs += ["-f", "lavfi", "-t", f"{D:.3f}", "-i", "anullsrc=r=48000:cl=stereo"]
    sil = sum(1 for x in inputs if x == "-i") - 1  # index of the anullsrc input
    graph = list(chains)
    # one silent source split four ways, so every stem runs the full length even when empty
    graph.append(f"[{sil}:a]asplit={len(stems_on)}" + "".join(f"[z{s}]" for s in stems_on))
    for s in stems_on:
        labs = by_stem[s] + [f"z{s}"]
        graph.append("".join(f"[{l}]" for l in labs) +
                     f"amix=inputs={len(labs)}:normalize=0:dropout_transition=0,"
                     f"apad=whole_dur={D:.3f},atrim=0:{D:.3f},{STEM_FILTERS[s]}"
                     + (f",volume={voice_trim_db:.2f}dB" if s == 4 else "") + f"[raw{s}]")
    # voice key for ducking
    graph.append("[raw4]asplit=" + ("4[v_out][v_k2][v_k3][v_k5]" if music else "3[v_out][v_k2][v_k3]"))
    # sidechaincompress stops at the first input to end, so the key is padded
    # with silence forever and the main input decides the length
    graph.append("[v_k2]apad[k2]")
    graph.append("[v_k3]apad[k3]")
    if music:
        graph.append("[v_k5]apad[k5]")
        graph.append(f"[raw5][k5]{DUCK[5]}[d5]")
        graph.append("[d5]asplit=2[s5][m5]")
    graph.append(f"[raw2][k2]{DUCK[2]}[d2]")
    graph.append("[raw3]asplit=2[raw3a][s3pre]")
    graph.append(f"[raw3a][k3]{DUCK[3]}[d3]")
    graph.append("[raw1]asplit=2[s1][m1]")
    graph.append("[d2]asplit=2[s2][m2]")
    graph.append("[d3]asplit=2[s3][m3]")
    graph.append("[v_out]asplit=2[s4][m4]")
    graph.append(("[m1][m2][m3][m4][m5]amix=inputs=5" if music else "[m1][m2][m3][m4]amix=inputs=4") + ":normalize=0:dropout_transition=0[pre]")
    return inputs, ";\n".join(graph), notes, D


def loudnorm_json(path, extra=""):
    err = run([sfxlib.FFMPEG, "-hide_banner", "-nostdin", "-i", str(path), "-af",
               f"loudnorm=I={TARGET_I}:TP={TARGET_TP}:LRA=11{extra}:print_format=json", "-f", "null", "-"])
    return json.loads(err[err.rfind("{"):err.rfind("}") + 1])


def env_db(x, sr=48000, win=0.05):
    h = int(sr * win)
    n = x.size // h
    return 20 * np.log10(np.sqrt(np.mean(x[: n * h].reshape(n, h) ** 2, axis=1)) + 1e-12)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("plan")
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--print-graph", action="store_true")
    ap.add_argument("--music", help="optional music bed (any ffmpeg-readable file), mixed on stem 5")
    ap.add_argument("--music-gain", type=float, default=0.0, help="dB applied to the music bed before ducking")
    ap.add_argument("--music-fade", type=float, default=1.5, help="fade-out length of the bed in seconds")
    a = ap.parse_args()
    plan = json.loads(Path(a.plan).read_text())
    out = Path(a.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    pcm = ["-c:a", "pcm_s24le", "-ar", "48000"]
    gfile = out / "filtergraph.txt"
    music = {"file": str(Path(a.music).expanduser().resolve()), "gain_db": a.music_gain, "fade_out_s": a.music_fade} if a.music else None

    def render(trim):
        inputs, graph, notes, D = build(plan, trim, music)
        gfile.write_text(graph + "\n")
        cmd = [sfxlib.FFMPEG, "-hide_banner", "-nostdin", "-y", *inputs, "-filter_complex_script", str(gfile)]
        for lab, name in (("s1", "stem1_sub.wav"), ("s2", "stem2_foley.wav"), ("s3", "stem3_air_bed.wav"),
                          ("s4", "stem4_voice.wav"), ("s3pre", "stem3_air_bed_preduck.wav"), ("pre", "premaster.wav"),
                          *((("s5", "stem5_music.wav"),) if music else ())):
            cmd += ["-map", f"[{lab}]", *pcm, str(out / name)]
        run(cmd)
        return graph, notes, D

    # pass A renders once and measures the processed voice stem; pass B trims it to VOICE_LUFS
    graph, notes, D = render(0.0)
    v_i = sfxlib.measure_loudness(out / "stem4_voice.wav")["integrated_lufs"]
    trim = round(VOICE_LUFS - v_i, 2) if v_i is not None else 0.0
    if abs(trim) > 0.1:
        graph, notes, D = render(trim)
        notes.append(f"voice stem measured {v_i} LUFS after its chain; trimmed {trim} dB to {VOICE_LUFS}")
    if a.print_graph:
        print(graph)

    # master: gain to target + limiter, then loudnorm two-pass in linear mode
    pre_i = sfxlib.measure_loudness(out / "premaster.wav")["integrated_lufs"]
    g = TARGET_I - pre_i
    run([sfxlib.FFMPEG, "-hide_banner", "-nostdin", "-y", "-i", str(out / "premaster.wav"), "-af",
         f"volume={g:.2f}dB,alimiter=limit=0.8414:attack=5:release=50:level=false:latency=1",
         *pcm, str(out / "limited.wav")])
    p1 = loudnorm_json(out / "limited.wav")
    lra_t = max(11.0, math.ceil(float(p1["input_lra"]) + 1))
    second = (f"loudnorm=I={TARGET_I}:TP={TARGET_TP}:LRA={lra_t}:measured_I={p1['input_i']}:"
              f"measured_TP={p1['input_tp']}:measured_LRA={p1['input_lra']}:"
              f"measured_thresh={p1['input_thresh']}:offset={p1['target_offset']}:linear=true:print_format=json")
    err = run([sfxlib.FFMPEG, "-hide_banner", "-nostdin", "-y", "-i", str(out / "limited.wav"), "-af", second,
               *pcm, str(out / "master.wav")])
    p2 = json.loads(err[err.rfind("{"):err.rfind("}") + 1])
    (out / "limited.wav").unlink()

    m = sfxlib.measure_loudness(out / "master.wav")
    stems = {n: sfxlib.measure_loudness(out / n) for n in
             ("stem1_sub.wav", "stem2_foley.wav", "stem3_air_bed.wav", "stem4_voice.wav") + (("stem5_music.wav",) if music else ())}
    master = sfxlib.decode_mono(out / "master.wav")
    v = env_db(sfxlib.decode_mono(out / "stem4_voice.wav"))
    b_pre = env_db(sfxlib.decode_mono(out / "stem3_air_bed_preduck.wav"))
    b_post = env_db(sfxlib.decode_mono(out / "stem3_air_bed.wav"))
    n = min(v.size, b_pre.size, b_post.size)
    voiced = (v[:n] > -40) & (b_pre[:n] > -90)
    quiet = (v[:n] <= -60) & (b_pre[:n] > -90)
    duck = float(np.mean(b_pre[:n][voiced] - b_post[:n][voiced])) if voiced.any() else None
    duck_q = float(np.mean(b_pre[:n][quiet] - b_post[:n][quiet])) if quiet.any() else None
    m_env = env_db(master, win=0.1)
    report = {
        "plan": str(Path(a.plan).resolve()), "duration_s": D,
        "events": len(plan["events"]), "notes": notes,
        "premaster_integrated_lufs": pre_i,
        "loudnorm_pass1": p1, "loudnorm_pass2_type": p2.get("normalization_type"),
        "master": {"integrated_lufs": m["integrated_lufs"], "true_peak_dbtp": m["true_peak_dbtp"],
                   "lra_lu": m["lra_lu"], "peak_dbfs": m["peak_dbfs"],
                   "min_100ms_rms_dbfs": round(float(m_env.min()), 1),
                   "min_100ms_rms_dbfs_before_end_fade": round(float(m_env[:-5].min()), 1) if m_env.size > 5 else None},
        "stems": stems,
        "stem_peak_minus_voice_lufs_db": {n: (round(v["peak_dbfs"] - stems["stem4_voice.wav"]["integrated_lufs"], 1)
                                              if v["peak_dbfs"] is not None and stems["stem4_voice.wav"]["integrated_lufs"] is not None else None)
                                          for n, v in stems.items()},
        "bed_duck_db_while_voice": round(duck, 2) if duck is not None else None,
        "bed_duck_db_without_voice": round(duck_q, 2) if duck_q is not None else None,
        "targets": {"integrated_lufs": TARGET_I, "true_peak_dbtp": TARGET_TP, "voice_lufs": VOICE_LUFS},
        "pass": bool(m["integrated_lufs"] is not None and abs(m["integrated_lufs"] - TARGET_I) <= 0.5
                     and m["true_peak_dbtp"] is not None and m["true_peak_dbtp"] <= TARGET_TP + 0.05
                     and float(m_env[:-5].min() if m_env.size > 5 else m_env.min()) > -70),
    }
    (out / "mix_report.json").write_text(json.dumps(report, indent=1) + "\n")
    print(json.dumps({k: report[k] for k in ("master", "loudnorm_pass2_type", "bed_duck_db_while_voice",
                                              "bed_duck_db_without_voice", "pass")}, indent=1))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
