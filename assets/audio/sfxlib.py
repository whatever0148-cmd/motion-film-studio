"""Shared helpers for the Empire Brain sfx-library: decode with ffmpeg, measure with
ffmpeg ebur128/astats, and compute a few numpy spectral features.

Nothing here executes code from the downloaded packs; files are only decoded by ffmpeg.
"""
import json, math, os, re, subprocess
from pathlib import Path

import numpy as np

import shutil
FFMPEG = os.environ.get("FFMPEG") or shutil.which("ffmpeg") or str(Path.home() / ".local/bin/ffmpeg")
ANALYSIS_SR = 48000


def decode_mono(path, sr=ANALYSIS_SR):
    """Decode any audio file to float32 mono at `sr` using ffmpeg."""
    cmd = [FFMPEG, "-v", "error", "-nostdin", "-i", str(path), "-map", "0:a:0",
           "-ac", "1", "-ar", str(sr), "-f", "f32le", "-acodec", "pcm_f32le", "-"]
    raw = subprocess.run(cmd, capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype="<f4").astype(np.float64)


def probe(path):
    """Container facts from `ffmpeg -i` (there is no ffprobe on this Mac)."""
    err = subprocess.run([FFMPEG, "-hide_banner", "-nostdin", "-i", str(path)],
                         capture_output=True, text=True).stderr
    out = {"codec": None, "sample_rate": None, "channels": None}
    m = re.search(r"Audio: ([^,\s]+)[^,]*, (\d+) Hz, ([^,]+)", err)
    if m:
        out["codec"] = m.group(1)
        out["sample_rate"] = int(m.group(2))
        ch = m.group(3).strip()
        out["channels"] = {"mono": 1, "stereo": 2}.get(ch, None)
        if out["channels"] is None:
            mm = re.match(r"(\d+) channels", ch)
            out["channels"] = int(mm.group(1)) if mm else ch
    return out


def measure_loudness(path):
    """Run ffmpeg ebur128 (with true peak) and astats over the whole file.

    Returns integrated LUFS (None when the file is too short for a gated
    measurement, which ebur128 reports as -70 LUFS), loudness range, true peak,
    sample peak, RMS, sample count and duration.
    """
    af = ("ebur128=peak=true:framelog=quiet,"
          "astats=measure_perchannel=none:measure_overall=Peak_level+RMS_level+Number_of_samples")
    err = subprocess.run([FFMPEG, "-hide_banner", "-nostdin", "-v", "info", "-i", str(path),
                          "-map", "0:a:0", "-af", af, "-f", "null", "-"],
                         capture_output=True, text=True).stderr
    res = {}
    summ = err[err.rfind("Summary:"):] if "Summary:" in err else ""
    m = re.search(r"I:\s+(-?[\d.]+|-inf) LUFS", summ)
    i_val = float(m.group(1)) if m and m.group(1) != "-inf" else None
    res["integrated_lufs"] = None if (i_val is None or i_val <= -69.9) else round(i_val, 2)
    m = re.search(r"LRA:\s+(-?[\d.]+) LU", summ)
    res["lra_lu"] = round(float(m.group(1)), 2) if m else None
    m = re.search(r"True peak:\s+Peak:\s+(-?[\d.]+|-inf) dBFS", summ)
    res["true_peak_dbtp"] = (round(float(m.group(1)), 2) if m and m.group(1) != "-inf" else None)
    # astats overall block (last occurrences win)
    pk = re.findall(r"Peak level dB:\s+(-?[\d.]+|-inf)", err)
    rms = re.findall(r"RMS level dB:\s+(-?[\d.]+|-inf)", err)
    ns = re.findall(r"Number of samples:\s+(\d+)", err)
    res["peak_dbfs"] = round(float(pk[-1]), 2) if pk and pk[-1] != "-inf" else None
    res["rms_dbfs"] = round(float(rms[-1]), 2) if rms and rms[-1] != "-inf" else None
    res["samples"] = int(ns[-1]) if ns else None
    return res


def features(x, sr=ANALYSIS_SR):
    """Spectral and envelope features used to sort and to flag synthetic tones."""
    out = {}
    if x.size == 0:
        return {"empty": True}
    peak = float(np.max(np.abs(x)))
    out["onset_s"] = None
    if peak > 0:
        idx = np.argmax(np.abs(x) >= peak * 10 ** (-30 / 20))
        out["onset_s"] = round(idx / sr, 4)
    # 10 ms RMS envelope
    hop = sr // 100
    n = x.size // hop
    if n >= 1:
        fr = x[: n * hop].reshape(n, hop)
        rms = np.sqrt(np.mean(fr ** 2, axis=1) + 1e-30)
        rms_db = 20 * np.log10(rms)
        out["noise_floor_dbfs"] = round(float(max(np.percentile(rms_db, 5), -140.0)), 1)
        top = float(np.max(rms_db))
        out["active_s"] = round(float(np.sum(rms_db > top - 30)) * hop / sr, 3)
    out["digital_zero_frac"] = round(float(np.mean(x == 0.0)), 4)
    # averaged power spectrum over the active part
    N = 4096
    if x.size < N:
        x = np.pad(x, (0, N - x.size))
    win = np.hanning(N)
    starts = range(0, x.size - N + 1, N // 2)
    frames = np.stack([x[s:s + N] for s in starts])
    e = np.sum(frames ** 2, axis=1)
    keep = e >= (e.max() * 10 ** (-40 / 10)) if e.max() > 0 else np.ones_like(e, bool)
    spec = np.mean(np.abs(np.fft.rfft(frames[keep] * win, axis=1)) ** 2, axis=0)
    freqs = np.fft.rfftfreq(N, 1 / sr)
    tot = float(spec.sum()) + 1e-30
    out["spectral_centroid_hz"] = round(float(np.sum(freqs * spec) / tot), 1)
    out["low_band_ratio_lt120hz"] = round(float(spec[freqs < 120].sum() / tot), 4)
    # tonal ratio: share of the energy above 150 Hz that sits in the 5 strongest
    # narrow peaks (+-2 bins = +-23 Hz). Measured above 150 Hz so wind rumble and
    # handling noise in real recordings do not read as a "tone".
    hp = freqs >= 150
    s = spec[hp].copy()
    tot_hp = float(s.sum()) + 1e-30
    acc = 0.0
    for _ in range(5):
        k = int(np.argmax(s))
        lo, hi = max(0, k - 2), min(s.size, k + 3)
        acc += float(s[lo:hi].sum())
        s[lo:hi] = 0
    out["tonal_ratio"] = round(acc / tot_hp, 4)
    out["dominant_hz"] = round(float(freqs[hp][int(np.argmax(spec[hp]))]), 1)
    # peak prominence: strongest bin above 150 Hz against the median of the
    # surrounding +-40 bins (+-470 Hz). A sine beep stands 30-60 dB proud of its
    # neighbourhood; a click, rip or whoosh stays within a few dB.
    sh = spec[hp]
    k = int(np.argmax(sh))
    nb = np.concatenate([sh[max(0, k - 40):max(0, k - 3)], sh[k + 4:k + 41]])
    med = float(np.median(nb)) if nb.size else 1e-30
    out["peak_prominence_db"] = round(10 * np.log10((sh[k] + 1e-30) / (med + 1e-30)), 1)
    # spectral flatness (geometric / arithmetic mean) between 100 Hz and 16 kHz
    band = spec[(freqs > 100) & (freqs < 16000)] + 1e-30
    out["spectral_flatness"] = round(float(np.exp(np.mean(np.log(band))) / np.mean(band)), 5)
    return out


def synthetic_suspect(f):
    """Heuristic flag for synthetic tones (sine/square UI beeps).

    A recorded click, rip or whoosh spreads its energy across many bins; a
    synthetic beep puts most of it in a handful of narrow peaks. Calibrated on
    this library (see catalog.md, 'How files were vetted').
    """
    flat = f.get("spectral_flatness", 1.0)
    prom = f.get("peak_prominence_db", 0.0)
    if f.get("low_band_ratio_lt120hz", 0.0) >= 0.15:
        # Rumble-heavy recordings (thunder, log drum) have a steeply falling
        # spectrum above 100 Hz, so flatness reads near zero; judge on the peak only.
        return bool(flat < 0.0005 and prom >= 25.0)
    return bool(flat < 0.0001 or (flat < 0.0005 and prom >= 25.0))
