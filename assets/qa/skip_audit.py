#!/usr/bin/env python3
"""skip_audit.py: viewer-side skip audit of a finished studio film (companion to video-flaw-scanner/flaw_scan.py).

Measures what a scrolling viewer would feel: time to first change, first-second energy, event cadence,
metronome/over-cut/dead holds, clutter and competing-motion proxies, text size in phone points,
text contrast, text dwell vs reading speed, frame-timing jitter, loudness behaviour, and writes the
"bored scroller" timeline at 0.3 s, 1 s, 3 s and 8 s.

flaw_scan.py already owns: flashes, frozen frames, silence, clipping, cue sync, safe zone, spec. Run both.
Every threshold lives in T below with its source tag; ids (SK-xxx) match references/flaw-catalog.md.

    ~/EmpireBrain/studio/.venv/bin/python -I ~/.claude/skills/skip-psychology-and-flaw-audit/scripts/skip_audit.py \
        film.mp4 [--safezone film.safezone.json] [--text-map text.json] [--out-dir DIR] [--phone-width-pt 390]

--text-map is {"text-0": "words shown", ...} (ids from the safezone sidecar) so reading speed can be checked.
Exit code 0 = no P0/P1, 1 = at least one P1, 2 = at least one P0. Needs numpy + ffmpeg only.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import zlib
from pathlib import Path

import numpy as np

FF = next((p for p in [str(Path.home() / ".local/bin/ffmpeg"), "/opt/homebrew/bin/ffmpeg", shutil.which("ffmpeg") or ""] if p and Path(p).exists()), None)
if not FF:
    sys.exit("skip_audit: ffmpeg not found")

# Thresholds. tag: S = sourced standard/study, H = house target (ours, not science), D = derived arithmetic from sourced numbers.
T = {
    "blank_frame0_std": 4.0,            # SK-A01 H (first-impression research is on static aesthetics, see catalog)
    "first_change_max_s": 0.35,         # SK-A02 H (floor from Facebook IQ 2016: recall after 0.25 s)
    "first_second_energy_min": 1.2,     # SK-A03 H (matches flaw_scan F03)
    "early_event_window_s": 1.5,        # SK-A06 H: an event in every 1.5 s window inside the first 3 s
    "static_hold_max_s": 1.4,           # SK-B01 H
    "event_gap_max_s": 2.6,             # SK-B02 H (CONTRACT.md resets 1.8 to 2.6 s)
    "metronome_cv_min": 0.15,           # SK-B03 H/SPECULATION
    "overcut_interval_s": 0.8,          # SK-B04 H; science: Lang LC4MP (unrelated rapid cuts are not encoded)
    "overcut_min_run_s": 3.0,
    "clutter_ratio_flag": 1.5,          # SK-C03 H: proxy vs the film's own median (Rosenholtz 2007 idea), uncalibrated
    "blobs_flag": 3,                    # SK-C04 H
    "blobs_min_run_s": 0.4,
    "phone_pt_hard_min": 11.0,          # SK-D01 S (Apple HIG iOS minimum, secondary check)
    "phone_pt_glance_min": 17.0,        # SK-D02 D (Apple HIG default body size)
    "contrast_small": 4.5,              # SK-D03 S WCAG 1.4.3
    "contrast_large": 3.0,              # SK-D03 S WCAG 1.4.3 (large = 18 pt, here judged on phone points)
    "large_pt": 18.0,
    "cps_hard": 20.0,                   # SK-D06 S Netflix English adult
    "cps_soft": 17.0,                   # SK-D06 S Netflix English children / conservative first-view
    "min_dwell_s": 5.0 / 6.0,           # SK-D06 S Netflix minimum subtitle duration
    "max_chars_event": 84,              # SK-D07 S Netflix 42 chars x 2 lines
    "max_simul_text": 2,                # SK-C01 H
    "lufs_target": -14.0, "lufs_tol": 1.5,       # SK-E01 H (CONTRACT)
    "tp_max": -1.0,                     # SK-E02 S EBU R128 s1
    "short_term_over_integrated": 5.0,  # SK-E03 S EBU R128 s1 (+5 LU), applied relative to our -14 target
    "momentary_jump_lu": 9.0,           # SK-E04 H (matches flaw_scan F11)
    "pts_jitter_frac": 0.25,            # SK-F03 H: frame time off by more than 25% of nominal
}
SEV = {"P0": 2, "P1": 1, "P2": 0}


def run(cmd, text=False):
    return subprocess.run(cmd, capture_output=True, text=text)


def probe(path):
    err = run([FF, "-hide_banner", "-nostdin", "-i", path], text=True).stderr
    info = {}
    m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", err)
    info["duration"] = int(m[1]) * 3600 + int(m[2]) * 60 + float(m[3]) if m else None
    v = re.search(r"Video: (\w+).*?, (\d{2,5})x(\d{2,5})", err)
    if v:
        info.update(vcodec=v[1], width=int(v[2]), height=int(v[3]))
    f = re.search(r"([\d.]+) fps", err)
    info["fps"] = float(f[1]) if f else 30.0
    info["has_audio"] = "Audio:" in err
    return info


def decode(path, fps, w=256, h=144):
    raw = run([FF, "-v", "error", "-nostdin", "-i", path, "-vf", f"fps={fps},scale={w}:{h}:flags=area,format=gray", "-f", "rawvideo", "-"]).stdout
    return np.frombuffer(raw, dtype=np.uint8).reshape(-1, h, w)


def runs(mask, fps, min_len_s):
    out, i, n = [], 0, len(mask)
    while i < n:
        if mask[i]:
            j = i
            while j < n and mask[j]:
                j += 1
            if (j - i) / fps >= min_len_s:
                out.append((round(i / fps, 3), round(j / fps, 3)))
            i = j
        else:
            i += 1
    return out


class Report:
    def __init__(self):
        self.rows = []

    def add(self, fid, sev, t, msg, value=None, limit=None):
        self.rows.append({"id": fid, "sev": sev, "t": t, "msg": msg, "value": value, "limit": limit})

    def worst(self):
        return max((SEV[r["sev"]] for r in self.rows), default=-1)


def luma_lin(rgb):
    c = rgb.astype(np.float64) / 255.0
    c = np.where(c <= 0.03928, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    return 0.2126 * c[..., 0] + 0.7152 * c[..., 1] + 0.0722 * c[..., 2]


def frame_rgb_crop(path, t, x, y, w, h, W, H):
    x, y = max(0, int(x)), max(0, int(y))
    w, h = max(2, min(int(w), W - x) & ~1), max(2, min(int(h), H - y) & ~1)  # even sizes: yuv420p crop rounds odd sizes down
    raw = run([FF, "-v", "error", "-nostdin", "-ss", f"{t:.3f}", "-i", path, "-frames:v", "1", "-vf", f"crop={w}:{h}:{x}:{y}", "-pix_fmt", "rgb24", "-f", "rawvideo", "-"]).stdout
    a = np.frombuffer(raw, dtype=np.uint8)
    return a.reshape(h, w, 3) if a.size == w * h * 3 else None


def video_checks(path, info, G, rep, tl):
    fps = min(info["fps"], 60.0)
    F = decode(path, fps)
    n = len(F)
    f = F.astype(np.int16)
    me = np.zeros(n)
    me[1:] = np.abs(f[1:] - f[:-1]).mean(axis=(1, 2))
    from0 = np.abs(f - f[0]).mean(axis=(1, 2))
    t = np.arange(n) / fps
    dur = n / fps
    tl["me"] = me
    tl["fps"] = fps

    # SK-A01 blank first frame
    s0 = float(F[0].std())
    if s0 < T["blank_frame0_std"]:
        rep.add("SK-A01", "P1", 0.0, "frame 0 is blank or a flat colour (thumbnail and first impression carry nothing)", round(s0, 2), f">= {T['blank_frame0_std']} luma std")
    # SK-A02 time to first meaningful change
    k = np.where(np.convolve((from0 > 3.0).astype(int), np.ones(3, int), "valid") == 3)[0]
    t_first = float(t[k[0]]) if len(k) else None
    G["time_to_first_change_s"] = t_first
    if t_first is None or t_first > T["first_change_max_s"]:
        rep.add("SK-A02", "P1", t_first or 0.0, "nothing visibly changes until late", None if t_first is None else round(t_first, 3), f"<= {T['first_change_max_s']} s")
    # SK-A03 first second energy
    m1 = float(me[1:int(fps) + 1].mean()) if n > fps else 0.0
    G["first_second_energy"] = round(m1, 3)
    if m1 < T["first_second_energy_min"]:
        rep.add("SK-A03", "P1", 0.0, "first second barely moves", round(m1, 3), f">= {T['first_second_energy_min']}")

    # events: smoothed ME local maxima
    k5 = max(1, int(fps * 0.1))
    sm = np.convolve(me, np.ones(k5) / k5, "same")
    med = float(np.median(me[me > 0])) if (me > 0).any() else 1.0
    thr = max(4.0, 2.5 * med)
    ev, last = [], -9.0
    for i in range(1, n - 1):
        if sm[i] >= thr and sm[i] >= sm[i - 1] and sm[i] > sm[i + 1] and t[i] - last >= 0.4:
            ev.append(float(t[i]))
            last = t[i]
    G["events"] = [round(x, 2) for x in ev]
    G["event_count"] = len(ev)
    G["events_per_min"] = round(len(ev) / dur * 60, 1) if dur else 0
    gaps = np.diff([0.0] + ev + [dur]) if ev else np.array([dur])
    G["max_event_gap_s"] = round(float(gaps.max()), 2)
    # SK-A06 early events
    early = [e for e in ev if e <= 3.0]
    if dur >= 3 and (not [e for e in early if e <= T["early_event_window_s"]] or not [e for e in early if e > T["early_event_window_s"]]):
        rep.add("SK-A06", "P1", 0.0, "fewer than one event in each 1.5 s window of the first 3 s", len(early), "1 per 1.5 s")
    # SK-B02 gap
    for i, g in enumerate(gaps):
        if g > T["event_gap_max_s"] and i < len(gaps):
            start = ([0.0] + ev)[i]
            rep.add("SK-B02", "P1", round(start, 2), f"{g:.2f} s with no event", round(float(g), 2), f"<= {T['event_gap_max_s']} s")
    # SK-B01 static holds
    for a, b in runs(me < 0.15, fps, T["static_hold_max_s"]):
        rep.add("SK-B01", "P1", a, f"static for {b - a:.2f} s ({a:.2f} to {b:.2f})", round(b - a, 2), f"<= {T['static_hold_max_s']} s")
    # SK-B03 metronome
    mid = np.diff(ev)
    if len(mid) >= 5:
        cv = float(mid.std() / mid.mean())
        G["event_interval_cv"] = round(cv, 3)
        if cv < T["metronome_cv_min"]:
            rep.add("SK-B03", "P2", 0.0, "events arrive on a metronome (habituation risk, house heuristic)", round(cv, 3), f">= {T['metronome_cv_min']}")
    # SK-B04 over-cutting
    dense = np.zeros(n, bool)
    for a, b in zip(ev[:-1], ev[1:]):
        if b - a < T["overcut_interval_s"]:
            dense[int(a * fps):int(b * fps)] = True
    for a, b in runs(dense, fps, T["overcut_min_run_s"]):
        rep.add("SK-B04", "P2", a, f"events closer than {T['overcut_interval_s']} s for {b - a:.1f} s (cuts may not be encoded)", None, None)

    # clutter proxy (compressed size of a downscaled frame, after Rosenholtz et al. 2007 note that file size tracks feature congestion)
    step = max(1, int(fps * 0.5))
    idx = list(range(0, n, step))
    cl = np.array([len(zlib.compress(F[i].tobytes(), 6)) / F[i].size for i in idx])
    G["clutter_median"] = round(float(np.median(cl)), 3)
    tl["clutter"] = dict(zip([round(float(t[i]), 2) for i in idx], [round(float(c), 3) for c in cl]))
    base = float(np.median(cl)) or 1e-6
    hot = (cl > base * T["clutter_ratio_flag"]) & (cl > 0.15)
    for j in range(len(idx) - 1):
        if hot[j] and hot[j + 1]:
            rep.add("SK-C03", "P2", round(float(t[idx[j]]), 2), "visual-clutter proxy is 1.5x the film median for 1 s or more (uncalibrated, look at it)", round(float(cl[j]), 3), f"<= {T['clutter_ratio_flag']}x median")
            break

    # competing motion blobs on a 16x9 grid
    gh, gw = 9, 16
    cell = np.abs(f[1:] - f[:-1]).reshape(n - 1, gh, 144 // gh, gw, 256 // gw).mean(axis=(2, 4))
    active = cell > 6.0
    blobs = np.zeros(n, int)
    for i in range(n - 1):
        a = active[i]
        if a.mean() > 0.6:
            continue
        seen = np.zeros_like(a)
        c = 0
        for y in range(gh):
            for x in range(gw):
                if a[y, x] and not seen[y, x]:
                    c += 1
                    st = [(y, x)]
                    seen[y, x] = True
                    while st:
                        cy, cx = st.pop()
                        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                            ny, nx = cy + dy, cx + dx
                            if 0 <= ny < gh and 0 <= nx < gw and a[ny, nx] and not seen[ny, nx]:
                                seen[ny, nx] = True
                                st.append((ny, nx))
        blobs[i + 1] = c
    tl["blobs"] = blobs
    G["max_blobs"] = int(blobs.max())
    for a, b in runs(blobs >= T["blobs_flag"], fps, T["blobs_min_run_s"]):
        rep.add("SK-C04", "P2", a, f"{T['blobs_flag']}+ separate regions moving at once for {b - a:.2f} s (competes with the single focus)", int(blobs[int(a * fps):int(b * fps)].max()), f"< {T['blobs_flag']}")
        break
    tl["luma"] = F.reshape(n, -1).mean(axis=1)
    tl["t"] = t
    tl["events"] = ev
    return F


def pts_check(path, info, rep, G):
    err = run([FF, "-hide_banner", "-nostdin", "-i", path, "-an", "-vf", "showinfo", "-f", "null", "-"], text=True).stderr
    pts = [float(x) for x in re.findall(r"pts_time:\s*([\d.]+)", err)]
    if len(pts) < 10:
        return
    d = np.diff(pts)
    nom = 1.0 / info["fps"]
    bad = np.where(np.abs(d - nom) > nom * T["pts_jitter_frac"])[0]
    G["pts_irregular_frames"] = int(len(bad))
    if len(bad):
        rep.add("SK-F03", "P0", round(pts[bad[0]], 3), f"{len(bad)} frames with timestamps off the {nom * 1000:.2f} ms grid (judder)", int(len(bad)), "0")


def audio_checks(path, rep, G, tl):
    err = run([FF, "-hide_banner", "-nostdin", "-v", "info", "-i", path, "-vn", "-af", "ebur128=peak=true:framelog=info", "-f", "null", "-"], text=True).stderr
    rows = re.findall(r"t:\s*([\d.]+)\s+TARGET:\S+ LUFS\s+M:\s*(-?[\d.]+|-inf)\s+S:\s*(-?[\d.]+|-inf)", err)
    if not rows:
        rows = re.findall(r"t:\s*([\d.]+)\s+M:\s*(-?[\d.]+|-inf)\s+S:\s*(-?[\d.]+|-inf)", err)
    tt = np.array([float(r[0]) for r in rows])
    def fl(x):
        return -120.0 if "inf" in x else float(x)
    M = np.array([fl(r[1]) for r in rows])
    S = np.array([fl(r[2]) for r in rows])
    tl["M"], tl["Mt"] = M, tt
    summ = err.split("Summary:")[-1]
    mi = re.search(r"I:\s*(-?[\d.]+) LUFS", summ)
    mp = re.search(r"Peak:\s*(-?[\d.]+) dBFS", summ)
    lra = re.search(r"LRA:\s*([\d.]+) LU", summ)
    if not mi:
        return
    I = float(mi[1])
    G["integrated_lufs"] = I
    G["true_peak_dbtp"] = float(mp[1]) if mp else None
    G["lra_lu"] = float(lra[1]) if lra else None
    if abs(I - T["lufs_target"]) > T["lufs_tol"]:
        rep.add("SK-E01", "P1", 0.0, "integrated loudness off target", I, f"{T['lufs_target']} +/- {T['lufs_tol']} LUFS")
    if mp and float(mp[1]) > T["tp_max"]:
        rep.add("SK-E02", "P0", 0.0, "true peak over limit", float(mp[1]), f"<= {T['tp_max']} dBTP")
    if len(S):
        smax = float(S.max())
        G["short_term_max"] = smax
        if smax > I + T["short_term_over_integrated"]:
            rep.add("SK-E03", "P1", round(float(tt[S.argmax()]), 2), "short-term loudness more than 5 LU above the integrated level", round(smax - I, 1), f"<= {T['short_term_over_integrated']} LU")
    if len(M) > 6:
        w = 5
        ok = M > -40  # only count jumps that start from an audible level
        worst, at = 0.0, 0.0
        for i in range(len(M) - w):
            if ok[i + w] and ok[i]:
                d = M[i + w] - M[i]
                if d > worst:
                    worst, at = d, tt[i]
        G["max_momentary_rise_lu_500ms"] = round(worst, 1)
        if worst > T["momentary_jump_lu"]:
            rep.add("SK-E04", "P1", round(float(at), 2), "sudden level jump", round(worst, 1), f"<= {T['momentary_jump_lu']} LU / 0.5 s")


def text_checks(path, info, sz, tmap, rep, G, tl, phone_pt):
    W, H = info["width"], info["height"]
    scale_to_phone = phone_pt / W
    ids = {}
    simul = []
    for s in sz.get("samples", []):
        tx = [b for b in s["boxes"] if b.get("kind") == "text"]
        vis = [b for b in tx if b.get("opacity", 1) >= 0.9]
        simul.append((s["t"], len(vis)))
        for b in tx:
            d = ids.setdefault(b["id"], {"t": [], "pt": [], "boxes": []})
            if b.get("opacity", 1) >= 0.9:
                d["t"].append(s["t"])
                d["pt"].append(b["fontPx"] * b.get("scale", 1) * scale_to_phone)
                d["boxes"].append(b)
    step = (sz["samples"][1]["t"] - sz["samples"][0]["t"]) if len(sz.get("samples", [])) > 1 else 0.1
    G["text_items"] = {}
    for tid, d in ids.items():
        if not d["t"]:
            continue
        t0, t1 = min(d["t"]), max(d["t"]) + step
        dwell = t1 - t0
        pt = min(d["pt"])
        item = {"first": round(t0, 2), "last": round(t1, 2), "dwell_s": round(dwell, 2), "min_phone_pt": round(pt, 1)}
        txt = tmap.get(tid)
        if txt is not None:
            chars = len(txt)
            item["chars"] = chars
            item["cps"] = round(chars / dwell, 1) if dwell else None
            if chars > T["max_chars_event"]:
                rep.add("SK-D07", "P2", t0, f"{tid}: {chars} characters on screen at once", chars, f"<= {T['max_chars_event']}")
            if dwell and chars / dwell > T["cps_hard"]:
                rep.add("SK-D06", "P1", t0, f"{tid}: read speed {chars / dwell:.1f} chars/s", round(chars / dwell, 1), f"<= {T['cps_hard']}")
            elif dwell and chars / dwell > T["cps_soft"]:
                rep.add("SK-D06", "P2", t0, f"{tid}: read speed {chars / dwell:.1f} chars/s is above the conservative 17", round(chars / dwell, 1), f"<= {T['cps_soft']}")
        if dwell < T["min_dwell_s"]:
            rep.add("SK-D06", "P1", t0, f"{tid}: on screen only {dwell:.2f} s", round(dwell, 2), f">= {T['min_dwell_s']:.2f} s")
        if pt < T["phone_pt_hard_min"]:
            rep.add("SK-D01", "P0", t0, f"{tid}: {pt:.1f} pt on a {phone_pt:.0f} pt wide phone", round(pt, 1), f">= {T['phone_pt_hard_min']} pt")
        elif pt < T["phone_pt_glance_min"] and dwell < 3.0:
            rep.add("SK-D02", "P2", t0, f"{tid}: {pt:.1f} pt is under the 17 pt glance size and it is on screen only {dwell:.1f} s", round(pt, 1), f">= {T['phone_pt_glance_min']} pt")
        # contrast at mid life
        mid_i = len(d["t"]) // 2
        b = d["boxes"][mid_i]
        crop = frame_rgb_crop(path, d["t"][mid_i], b["x"], b["y"], b["w"], b["h"], W, H)
        if crop is not None and crop.size:
            L = luma_lin(crop).ravel()
            bg = float(np.median(L))
            lo, hi = float(np.percentile(L, 2)), float(np.percentile(L, 98))
            fg = hi if abs(hi - bg) >= abs(bg - lo) else lo
            ratio = (max(fg, bg) + 0.05) / (min(fg, bg) + 0.05)
            item["contrast"] = round(ratio, 2)
            need = T["contrast_large"] if pt >= T["large_pt"] else T["contrast_small"]
            if ratio < need:
                rep.add("SK-D03", "P1", d["t"][mid_i], f"{tid}: contrast {ratio:.2f}:1 (estimate from box pixels)", round(ratio, 2), f">= {need}:1")
        G["text_items"][tid] = item
    # simultaneous text
    sim = max((c for _, c in simul), default=0)
    G["max_simultaneous_text"] = sim
    if sim > T["max_simul_text"]:
        tt = next(tm for tm, c in simul if c == sim)
        rep.add("SK-C01", "P2", tt, f"{sim} text blocks visible at once", sim, f"<= {T['max_simul_text']}")
    tl["text_ids"] = ids
    tl["simul"] = dict(simul)


def scroller(tl, G, info):
    out = []
    fps, t, me = tl["fps"], tl["t"], tl["me"]
    n = len(t)
    for cp in (0.0, 0.3, 1.0, 3.0, 8.0):
        if cp > t[-1]:
            continue
        i = min(n - 1, int(cp * fps))
        w0 = max(0, i - int(0.3 * fps))
        row = {"t": cp, "motion_energy_last_0.3s": round(float(me[w0:i + 1].mean()), 2), "mean_luma": round(float(tl["luma"][i]), 1),
               "regions_moving": int(tl["blobs"][i]), "events_so_far": len([e for e in tl["events"] if e <= cp])}
        if "Mt" in tl and len(tl["Mt"]):
            j = min(len(tl["M"]) - 1, int(np.searchsorted(tl["Mt"], cp)))
            row["momentary_loudness"] = round(float(tl["M"][j]), 1)
        txt = []
        for tid, d in tl.get("text_ids", {}).items():
            if d["t"] and min(d["t"]) <= cp <= max(d["t"]) + 0.1:
                txt.append(f"{tid} ({min(d['pt']):.0f} pt)")
        row["text_visible"] = txt
        out.append(row)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("--safezone")
    ap.add_argument("--text-map")
    ap.add_argument("--out-dir")
    ap.add_argument("--phone-width-pt", type=float, default=390.0)
    a = ap.parse_args()
    path = str(Path(a.video).resolve())
    info = probe(path)
    rep, G, tl = Report(), {}, {}
    video_checks(path, info, G, rep, tl)
    if info.get("width") and info.get("height") and info["width"] > info["height"]:
        rep.add("SK-G12", "P2", 0.0, "landscape frame: on an upright phone it plays letterboxed at about 56% the scale of a 9:16 frame; Instagram's written guidance asks for 9x16 full screen (specialist 01 holds the ratio veto)", f"{info['width']}x{info['height']}", "9x16")
    pts_check(path, info, rep, G)
    if info["has_audio"]:
        audio_checks(path, rep, G, tl)
    sz_path = a.safezone or next((str(p) for p in Path(path).parent.glob(Path(path).stem + "*.safezone.json")), None)
    if sz_path and Path(sz_path).exists():
        sz = json.loads(Path(sz_path).read_text())
        tmap = json.loads(Path(a.text_map).read_text()) if a.text_map else {}
        text_checks(path, info, sz, tmap, rep, G, tl, a.phone_width_pt)
    scr = scroller(tl, G, info)
    rep.rows.sort(key=lambda r: (-SEV[r["sev"]], r["t"]))
    verdict = {2: "FAIL (P0)", 1: "FIX (P1)", 0: "LOOK (P2 only)", -1: "PASS"}[rep.worst()]
    res = {"video": path, "verdict": verdict, "info": info, "global": G, "bored_scroller": scr, "flaws": rep.rows}
    outd = Path(a.out_dir) if a.out_dir else Path(path).parent
    outd.mkdir(parents=True, exist_ok=True)
    jp = outd / (Path(path).stem + ".skip.json")
    jp.write_text(json.dumps(res, indent=2, default=lambda o: o.tolist() if hasattr(o, "tolist") else str(o)))
    print(f"skip_audit {Path(path).name}: {verdict}  ({info.get('width')}x{info.get('height')} @ {info['fps']} fps, {info['duration']} s)")
    for k in ("time_to_first_change_s", "first_second_energy", "events_per_min", "max_event_gap_s", "event_interval_cv", "max_blobs", "integrated_lufs", "true_peak_dbtp", "max_simultaneous_text"):
        if k in G:
            print(f"  {k}: {G[k]}")
    print("bored scroller:")
    for r in scr:
        print("  ", r)
    for r in rep.rows:
        print(f"  [{r['sev']}] {r['id']} @ {r['t']}s  {r['msg']}  (value {r['value']}, limit {r['limit']})")
    print(f"wrote {jp}")
    sys.exit({2: 2, 1: 1}.get(rep.worst(), 0))


if __name__ == "__main__":
    main()
