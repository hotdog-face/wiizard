#!/usr/bin/env python3
"""Find dropouts/clicks in a stereo s16 WAV: runs of exact-zero samples inside sound (|neighbours| large), and
big single-sample steps. Prints counts, run lengths and spacing; optional start/end seconds."""
import sys, wave, numpy as np
def load(p):
    w = wave.open(p); r = w.getframerate()
    return r, np.frombuffer(w.readframes(w.getnframes()), dtype='<i2').reshape(-1, 2).astype(np.int32)
def analyse(p, t0=0, t1=None, thr=1500):
    r, a = load(p); m = a[:, 0]
    s, e = int(t0 * r), (int(t1 * r) if t1 else len(m)); m = m[s:e]
    z = (m == 0).astype(np.int8)
    d = np.diff(np.concatenate([[0], z, [0]]))
    starts, ends = np.where(d == 1)[0], np.where(d == -1)[0]
    runs = []
    for a0, b0 in zip(starts, ends):
        if a0 > 2 and b0 < len(m) - 2 and abs(m[a0 - 1]) > thr and abs(m[b0]) > thr:
            runs.append((a0, b0 - a0))
    mm = m.astype(np.int64)
    dev = np.abs(mm[1:-1] - (mm[:-2] + mm[2:]) // 2); nb = np.abs(mm[:-2] - mm[2:])
    spikes = np.where((dev > 1500) & (nb < dev // 3))[0] + 1
    steps = np.abs(np.diff(m))
    big = np.where(steps > 8000)[0]
    out = {"secs": round(len(m) / r, 1), "rate": r, "dropouts": len(runs),
           "dropout_len_hist": {int(k): int(v) for k, v in zip(*np.unique([l for _, l in runs], return_counts=True))} if runs else {},
           "dropouts_per_s": round(len(runs) / (len(m) / r), 2), "steps_gt_8000": int(len(big)), "spikes": int(len(spikes)),
           "spikes_per_s": round(len(spikes) / (len(m) / r), 1),
           "spike_phase64": (lambda u: {int(k): int(v) for k, v in zip(*u)})(np.unique(spikes % 64, return_counts=True)) if len(spikes) < 100000 and len(spikes) else {},
           "first": [round((s + a0) / r, 4) for a0, _ in runs[:8]]}
    if len(runs) > 1:
        sp = np.diff([a0 for a0, _ in runs]); out["spacing_median"] = int(np.median(sp)); out["spacing_min"] = int(sp.min())
    return out
if __name__ == "__main__":
    import json
    print(json.dumps(analyse(sys.argv[1], *(float(x) for x in sys.argv[2:4])), indent=None))
