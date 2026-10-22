#!/usr/bin/env python3
"""Before publishing: the picture baseline Mitchell approved on the CRT (2026-10-21: "looks fantastic ... pixel
perfect") must not change by accident. Compares the video keys of the shipped retroarch.cfg (sdkit_install.py
RETROARCH_CFG) and every per-game/core override in sdkit/retroarch/config with baseline-20261021/. Exit 1 on any
difference. A deliberate picture change: update the baseline in the same change, with the CRT check noted."""
import importlib.util, os, re, sys
HERE = os.path.dirname(os.path.abspath(__file__)); WII = os.path.abspath(os.path.join(HERE, "../.."))
B = os.path.join(HERE, "baseline-20261021")
V = re.compile(r'^\s*(video_(?!font_enable)\w+|current_resolution_id|aspect_ratio_index|custom_viewport_\w+)\s*=')
spec = importlib.util.spec_from_file_location("k", os.path.join(WII, "sdkit_install.py"))
k = importlib.util.module_from_spec(spec); spec.loader.exec_module(k)
bad = []
cur = [l for l in k.RETROARCH_CFG.splitlines() if V.match(l)]
if cur != open(os.path.join(B, "retroarch.cfg.video")).read().splitlines(): bad.append("retroarch.cfg video keys")
def vids(p): return [l for l in open(p).read().splitlines() if V.match(l)] if os.path.exists(p) else None
S = os.path.join(WII, "sdkit/retroarch/config"); BC = os.path.join(B, "config")
for root in (S, BC):
    for d, _, fs in os.walk(root):
        for f in fs:
            if not f.endswith(".cfg"): continue
            rel = os.path.relpath(os.path.join(d, f), root)
            if vids(os.path.join(S, rel)) != vids(os.path.join(BC, rel)) and rel not in bad: bad.append(rel)
print("video baseline:", "OK" if not bad else f"{len(bad)} differ: {bad[:10]}")
sys.exit(1 if bad else 0)
