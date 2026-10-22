#!/usr/bin/env python3
"""collections.tsv for the launcher: hand-picked lists instead of system names, best first.
    make_collections.py [popularity.json]   (fleet.py report passes the fleet's play counts)
One line per collection: name<TAB>key,key,...  (keys: arcade zip stem or disc id). Order inside a collection: what
gets played on all cabinets in the last 30 days, then the ScreenScraper rating, with a nudge for famous games. Once
there are 30+ days of play data, games nobody has played in 30 days drop out of the collections (they stay in
All Games and on the card)."""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
WII = os.path.dirname(HERE)

# Crowd-pleasers: Quick Picks before there's any play data, and a small nudge after.
FAMOUS = ["pacman", "dkong", "galaxian", "frogger", "invaders", "centiped", "qbert", "mspacman", "digdug", "1942",
          "sf2ce", "ssf2t", "sfa3", "mvsc", "xmvsf", "ffight", "captcomm", "mslug", "mslugx", "mslug3", "kof98", "tmnt",
          "simpsons", "outrun", "contra", "rtype", "arkanoid", "bublbobl", "gauntlet", "goldnaxe",
          "GALE01", "GM4E01", "GMSE01", "GFZE01", "GP7E01", "GP6E01", "GSOE8P", "GKYE01", "GZLE01", "G4SE01",
          "SMNE01", "SF8E01", "SVME01",
          "mdsonc2", "mdsor2", "snsmw", "snsmk", "sntmnt4", "nesmb3", "snsf2t", "mdgunst"]

# Hand-picked for small children (toddlers): can't really fail, few buttons, forgiving.
LITTLE_KIDS = ["GKYE01",   # Kirby Air Ride: drives itself, steer only (Top Ride mode is the simplest)
               "GM4E01",   # Mario Kart: Double Dash!! (50cc; a cloud puts you back on the track)
               "snkirby", "nesmb", "neballo", "nedrmar", "GKQE01"]   # Kirby Super Star, SMB, Balloon Fight, Dr. Mario, Kururin

COLLECTIONS = [                              # name, test(entry) — entries: key, system, genre, players, year
    ("Little Kids", LITTLE_KIDS),           # a fixed list, in this order
    ("Arcade Classics", lambda e: e["system"] == "arcade" and e["year"] and e["year"] <= 1987),
    ("Console Classics", lambda e: e["system"] in ("genesis", "snes", "nes")),
    ("Fighting", lambda e: e["genre"].startswith("Fighting") or e["genre"] == "Sports / Fighting"),
    ("Beat-'em-Ups", lambda e: e["genre"].startswith("Beat") or e["genre"] == "Platform / Fighter Scrolling"),
    ("Shooters", lambda e: e["genre"].startswith(("Shoot", "Shooter"))),
    ("4-Player Games", lambda e: e["players"] >= 3),
    ("Platformers", lambda e: e["genre"].startswith(("Platform", "Action")) and "Fighter" not in e["genre"]),
    ("Racing & Sports", lambda e: e["genre"].startswith(("Racing", "Sports", "Motorcycle"))),
    ("Puzzle", lambda e: e["genre"].startswith("Puzzle")),
    ("Adventure & RPG", lambda e: any(w in e["genre"] for w in ("RPG", "Role Playing", "Adventure", "Strategy", "Simulation"))),
    ("GameCube", "@gamecube"),             # whole systems: the launcher fills these from what's on the card
    ("Wii", "@wii"),
]
QUICK_PICKS = 24


def entries():
    hidden = set()
    for line in open(os.path.join(HERE, "hidden.txt")):
        if line.startswith(("rom:", "id:")):
            hidden.add(line.strip().split(":", 1)[1])
    meta = {}
    for line in open(os.path.join(HERE, "meta.tsv"), errors="replace"):
        p = line.rstrip("\n").split("\t")
        if len(p) >= 4:
            meta[p[0]] = p
    out = {}
    for r in json.load(open(os.path.join(HERE, "arcade_plan.json"))):
        stem = r[2][:-4]
        if r[3] and stem not in hidden:
            out[stem] = {"system": "arcade" if r[0] == "arcade" else r[0], "year": int(r[4][:4]) if r[4][:4].isdigit() else 0}
    gc = os.path.join(WII, "videos/gc_ids.txt")
    for line in open(gc) if os.path.exists(gc) else []:
        gid = line.split("|")[0]
        if gid not in hidden:
            out[gid] = {"system": "wii" if gid[0] in "RS" else "gamecube", "year": 0}
    for key in meta:                         # Wii discs (ids R.../S...): the launcher skips any not on the card
        if len(key) == 6 and key[0] in "RS" and key.isalnum() and key.upper() == key and key not in hidden:
            out.setdefault(key, {"system": "wii", "year": 0})
    for line in open(os.path.join(HERE, "consoles.tsv")):   # Genesis / SNES / NES picks
        p = line.rstrip("\n").split("\t")
        stem = p[1].rsplit(".", 1)[0] if len(p) > 3 and not line.startswith("#") else None
        if stem and stem not in hidden:
            out[stem] = {"system": p[0], "year": int(p[3]) if p[3].isdigit() else 0}
    for key, e in out.items():
        m = meta.get(key, [key, "", "", ""])
        e["key"] = key
        e["players"] = int(m[1]) if m[1].isdigit() else 1
        e["rating"] = float(m[2]) if m[2] else 0.6
        e["genre"] = m[3]
    return out


def main(pop_path=None):
    pop = json.load(open(pop_path)) if pop_path and os.path.exists(pop_path) else {}
    history = pop.get("_history_days", 0)
    games = entries()

    def score(e):
        p = pop.get(e["key"], {})
        return 3.0 * p.get("plays30", 0) + 2.0 * p.get("favs", 0) + 10 * e["rating"] + (2 if e["key"] in FAMOUS else 0)

    def unplayed(e):                         # only once we know: 30+ days of data, nobody played it
        return history >= 30 and not pop.get(e["key"], {}).get("plays30", 0) and not pop.get(e["key"], {}).get("favs", 0)

    live = [e for e in games.values() if not unplayed(e)]
    ranked = sorted(live, key=score, reverse=True)
    if any(pop.get(e["key"], {}).get("plays30") for e in ranked):
        quick = ranked[:QUICK_PICKS]
    else:                                     # no play data yet: famous games first
        quick = [e for e in ranked if e["key"] in FAMOUS] + [e for e in ranked if e["key"] not in FAMOUS]
        quick = quick[:QUICK_PICKS]
    lines = ["# name<TAB>keys, best first (sdkit/make_collections.py)", "Quick Picks\t" + ",".join(e["key"] for e in quick)]
    for name, test in COLLECTIONS:
        if isinstance(test, str):
            lines.append(f"{name}\t{test}")
            continue
        if isinstance(test, list):
            keys = [k for k in test if k in games]
            if keys: lines.append(f"{name}\t" + ",".join(keys))
            continue
        keys = [e["key"] for e in ranked if test(e)]
        if len(keys) >= 3:
            lines.append(f"{name}\t" + ",".join(keys))
    open(os.path.join(HERE, "collections.tsv"), "w").write("\n".join(lines) + "\n")
    dropped = len(games) - len(live)
    for l in lines[1:]:
        n, k = l.split("\t")
        print(f"{n}: {len(k.split(','))}")
    if dropped:
        print(f"{dropped} games nobody played in 30 days left out of the collections (still in All Games)")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else None)
