#!/usr/bin/env python3
"""Compare the Wii's audio (Dolphin DSP dump, 32 kHz) with the core's own output from the macOS build (hostref.py):
the reference is played at the rate RetroArch assumes (core rate * 59.826/60), ideally resampled to 32 kHz, aligned by
cross-correlation over a window, and the residual after best gain gives an SNR (higher = cleaner). DC is removed
from both (the dkong DAC sits on a large DC offset).
    audcmp.py <wii.wav> <wii_t0> <secs> <host.wav> <host_rate_assumed> [search_from search_to]"""
import sys, wave, json, numpy as np
def load(p):
    w = wave.open(p); r = w.getframerate()
    return r, np.frombuffer(w.readframes(w.getnframes()), dtype='<i2').reshape(-1, 2).astype(float)[:, 0]
def hp(x, r, fc=20.0):
    a = np.exp(-2 * np.pi * fc / r); y = np.empty_like(x); prev_x = prev_y = 0.0
    for i, v in enumerate(x):
        prev_y = a * (prev_y + v - prev_x); prev_x = v; y[i] = prev_y
    return y
def fft_resample(x, n_out):
    X = np.fft.rfft(x); n = len(x); Y = np.zeros(n_out // 2 + 1, complex); k = min(len(X), len(Y)); Y[:k] = X[:k]
    return np.fft.irfft(Y, n_out) * n_out / n
def compare(wpath, t0, secs, hpath, hrate, s0=None, s1=None):
    rw, w = load(wpath); rh, h = load(hpath)
    seg = w[int(t0 * rw): int((t0 + secs) * rw)]
    a, b = (int((s0 or 0) * rh), int((s1 or len(h) / rh) * rh))
    hh = h[a:b]
    href = fft_resample(hh, int(len(hh) * 32000 / hrate))
    seg_h, ref_h = hp(seg, 32000), hp(href, 32000)
    n = len(seg_h); N = 1 << int(np.ceil(np.log2(len(ref_h) + n)))
    xc = np.fft.irfft(np.fft.rfft(ref_h, N) * np.conj(np.fft.rfft(seg_h, N)), N)[:len(ref_h) - n]
    lag = int(np.argmax(xc)); r = ref_h[lag:lag + n]
    g = np.dot(seg_h, r) / np.dot(r, r); e = seg_h - g * r
    snr = 10 * np.log10(np.sum((g * r) ** 2) / np.sum(e ** 2))
    E = np.abs(np.fft.rfft(e)) ** 2; f = np.fft.rfftfreq(n, 1 / 32000)
    return {"snr_db": round(snr, 1), "gain": round(g, 3), "lag_s": round((a + lag * hrate / 32000) / rh, 3),
            "resid_rms": round(float(np.sqrt(np.mean(e ** 2))), 1), "sig_rms": round(float(np.sqrt(np.mean(seg_h ** 2))), 1),
            "resid_above_8k_pct": round(100 * E[f > 8000].sum() / E.sum(), 1)}
if __name__ == "__main__":
    a = sys.argv[1:]
    print(json.dumps(compare(a[0], float(a[1]), float(a[2]), a[3], float(a[4]), *(float(x) for x in a[5:7]))))
