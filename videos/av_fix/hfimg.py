#!/usr/bin/env python3
"""Imaging/aliasing energy a resampler adds: share of the output's energy above the core's Nyquist (rate/2), in dB,
over the loud part of the clip. For a 22050 Hz core played at 32 kHz everything above 11.025 kHz is artefact."""
import sys, wave, numpy as np
w = wave.open(sys.argv[1]); r = w.getframerate(); nyq = float(sys.argv[2]) / 2
a = np.frombuffer(w.readframes(w.getnframes()), dtype='<i2').reshape(-1, 2).astype(float)[:, 0]
# skip single-sample chunk glitches: median-of-3 cleanup so only the resampler's own artefacts count
b = np.median(np.stack([a[:-2], a[1:-1], a[2:]]), axis=0)
win = 4096; tot = hi = 0.0; f = np.fft.rfftfreq(win, 1 / r); hann = np.hanning(win)
for i in range(0, len(b) - win, win):
    x = b[i:i + win]; x = x - x.mean()
    if np.std(x) < 300: continue
    X = np.abs(np.fft.rfft(x * hann)) ** 2; tot += X.sum(); hi += X[f > nyq * 1.02].sum()
print("%s: energy above %.0f Hz = %.1f dB" % (sys.argv[1], nyq * 1.02, 10 * np.log10(hi / tot)))
