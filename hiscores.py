#!/usr/bin/env python3
"""High scores for the menu's "HI 12,340" badges: decodes the arcade games' high-score saves (.hi files, the memory
ranges hiscore.dat names, saved by RetroArch's FB Alpha cores; the fleet collector pulls them into
fleet/cabs/<id>/hiscores/) into sdkit/hiscores.tsv (key<TAB>score), best across all cabinets. Each game stores its
table its own way, so there's one small decoder per game, added as games get played and their saves show up.
    hiscores.py [fleet dir]"""
import glob, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))

def bcd(b):
    return int("".join(f"{x >> 4}{x & 15}" for x in b) or "0")

DECODERS = {
    # Marvel vs. Capcom (CPS-2): 0xff26fd, 66 bytes: 1 byte, then 10-byte entries: 4 BCD score bytes + name;
    # the first entry is the top score (factory table 50000 .. 10000).
    "mvsc": lambda d: bcd(d[1:5]),
}

def main(fleet=os.path.join(HERE, "fleet")):
    best = {}
    for path in glob.glob(os.path.join(fleet, "cabs", "*", "hiscores", "*.hi")):
        key = os.path.basename(path)[:-3]
        dec = DECODERS.get(key)
        if not dec: continue
        try: score = dec(open(path, "rb").read())
        except Exception: continue
        if score > best.get(key, 0): best[key] = score
    out = os.path.join(HERE, "sdkit", "hiscores.tsv")
    open(out, "w").write("".join(f"{k}\t{v:,}\n" for k, v in sorted(best.items())))
    undecoded = sorted({os.path.basename(p)[:-3] for p in glob.glob(os.path.join(fleet, "cabs", "*", "hiscores", "*.hi"))} - set(DECODERS))
    print(len(best), "high scores;", "no decoder yet:", undecoded)
    return undecoded

if __name__ == "__main__":
    main(*(sys.argv[1:2]))
