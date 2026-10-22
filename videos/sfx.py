#!/usr/bin/env python3
"""The menu's sound effects, synthesised (no samples to license): sdkit/sfx/{move,select,back,coin}.gaud, the same
GAU1 format as the attract clips (16 kHz mono s16be). Soft square/sine blips in the spirit of an arcade cabinet."""
import os, struct
import numpy as np

RATE = 16000
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "sdkit", "sfx")


def tone(freq, secs, kind="square", vol=0.5, decay=8.0):
    t = np.arange(int(RATE * secs)) / RATE
    if callable(freq):
        phase = 2 * np.pi * np.cumsum(freq(t)) / RATE
    else:
        phase = 2 * np.pi * freq * t
    w = np.sign(np.sin(phase)) * 0.6 + np.sin(phase) * 0.4 if kind == "square" else np.sin(phase)
    env = np.exp(-decay * t) * np.minimum(1, t * 400)          # 2.5 ms attack, exponential decay
    return w * env * vol


def save(name, x):
    pcm = (np.clip(x, -1, 1) * 32767 * 0.8).astype(">i2").tobytes()
    open(os.path.join(OUT, name + ".gaud"), "wb").write(b"GAU1" + struct.pack(">II", RATE, len(pcm) // 2) + pcm)


os.makedirs(OUT, exist_ok=True)
# Calm: sine tones only (no square edges), low and soft, gentle attack and release.
def soft(freq, secs, vol, decay, attack=0.012):
    t = np.arange(int(RATE * secs)) / RATE
    f = freq(t) if callable(freq) else freq
    phase = 2 * np.pi * (np.cumsum(f) / RATE if callable(freq) else f * t)
    env = np.minimum(1, t / attack) * np.exp(-decay * t)
    tail = np.minimum(1, (secs - t) / 0.02)                    # no click at the end
    return np.sin(phase) * env * tail * vol
save("move", soft(520, 0.06, 0.10, 45))                        # a soft tick
save("select", np.concatenate([soft(523, 0.09, 0.16, 18), soft(784, 0.22, 0.14, 12)]))      # C5 -> G5, gentle
save("back", soft(lambda t: 600 - 900 * t, 0.14, 0.12, 16))   # a soft downward glide
save("coin", np.concatenate([soft(659, 0.12, 0.16, 10), soft(988, 0.5, 0.14, 5)]))          # E5 -> B5 chime
print(sorted(os.listdir(OUT)))
