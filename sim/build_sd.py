#!/usr/bin/env python3
"""The SD card for the Dolphin simulator (sim/sd, synced by Dolphin as the Wii's SD card): the real menu media
(clips, sounds, stills, art, metadata, fonts, cabinet settings) and tiny stand-ins for the games themselves (the
launcher only needs the files to exist and, for GameCube images, the 6-byte disc id). Rebuild after media changes.
Big files are APFS clones (cp -c): instant, no extra disk space."""
import json, os, re, shutil, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__)); WII = os.path.dirname(HERE)
sys.path.insert(0, WII)
import sdkit_install as k
SD = os.path.join(HERE, "sd")
V = os.path.join(WII, "videos")

def clone_dir(src, dst):
    os.makedirs(dst, exist_ok=True)
    for f in os.listdir(src):
        if f.startswith("."): continue
        s, d = os.path.join(src, f), os.path.join(dst, f)
        if not os.path.exists(d) or os.path.getsize(d) != os.path.getsize(s):
            subprocess.run(["cp", "-c", s, d], check=True)

def put(path, data):
    p = os.path.join(SD, path); os.makedirs(os.path.dirname(p), exist_ok=True)
    open(p, "wb").write(data if isinstance(data, bytes) else data.encode())

hidden = [l.strip() for l in open(os.path.join(WII, "sdkit/hidden.txt")) if l.strip() and not l.startswith("#")]
hid_rom = {h[4:] for h in hidden if h.startswith("rom:")}
tsv = []
for r in json.load(open(os.path.join(WII, "sdkit/arcade_plan.json"))):
    system, nas_dir, z, title, year, maker = r[:6]
    if not title or z[:-4] in hid_rom: continue
    dest = "neogeo.zip" if z == "neogeo (1).zip" else z
    tsv.append(f"{system}\t{dest}\t{k.clean_title(title)}\t{year}\t{maker}\t{r[6]}")
    put(f"roms/{system}/{dest}", b"")
put("arcade/arcade.tsv", "\n".join(tsv) + "\n")
for f in ("hidden.txt", "meta.tsv", "collections.tsv"):
    shutil.copy(os.path.join(WII, "sdkit", f), os.path.join(SD, "arcade", f))
clone_dir(os.path.join(WII, "sdkit/cabs"), os.path.join(SD, "arcade/cabs"))
for name, src in k.FONTS.items():
    put(f"arcade/fonts/{name}", open(src, "rb").read())
clone_dir(k.UI_ART, os.path.join(SD, "arcade/ui"))
for src, dst in [("gvid", "arcade/video"), ("gvid_discs", "arcade/video"), ("gaud", "arcade/audio"),
                 ("covers", "arcade/art/covers"), ("stills", "arcade/art/stills")]:
    clone_dir(os.path.join(V, src), os.path.join(SD, dst))
clone_dir(os.path.join(WII, "sdkit/sfx"), os.path.join(SD, "arcade/sfx"))
for f in os.listdir(os.path.join(V, "art")):
    system, stem = f.split("__", 1)
    d = os.path.join(SD, "arcade/art", system); os.makedirs(d, exist_ok=True)
    if not os.path.exists(os.path.join(d, stem)): subprocess.run(["cp", "-c", os.path.join(V, "art", f), os.path.join(d, stem)])
# GameCube: games/<name>.iso holding just the disc id; Wii: wbfs/<Title [ID]>/<ID>.wbfs (empty)
for line in open(os.path.join(V, "gc_ids.txt")):
    gid, name = line.rstrip("\n").split("|", 1)
    if f"id:{gid}" in hidden: continue
    put(f"games/{os.path.basename(name)}", gid.encode())
wii = {"RNCEH4": "SNK Arcade Classics", "SVME01": "Super Mario All-Stars", "STKE08": "Tatsunoko vs. Capcom- Ultimate All-Stars",
       "RSBE01": "Super Smash Bros Brawl"}
for gid, title in wii.items():
    put(f"wbfs/{title} [{gid}]/{gid}.wbfs", b"")
put("apps/wii-agent/meta.xml", open(os.path.join(WII, "agent/meta.xml")).read())
print("sim SD:", subprocess.run(["du", "-sh", SD], capture_output=True, text=True).stdout.split()[0], "-", len(tsv), "arcade games")
