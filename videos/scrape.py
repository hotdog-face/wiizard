#!/usr/bin/env python3
"""Gameplay video snaps for the Wii launcher from ScreenScraper, through a Skyscraper install
($SKYSCRAPER_DIR, default ~/skyscraper). Login from the macOS Keychain (service
"screenscraper"), passed straight to Skyscraper, never printed or stored.
    scrape.py links | gather [plat..] | generate [plat..] | map
Placeholders named after each game (ScreenScraper matches by name; the real ISOs are 1.4 GB each) live in
links/<plat>/; keys.json maps placeholder -> launcher key (disc id for GameCube/Wii, zip stem for arcade).
map writes videos.json: launcher key -> mp4 path."""
import json
import os
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKYDIR = Path(os.environ.get("SKYSCRAPER_DIR", Path.home() / "skyscraper"))
SKY = SKYDIR / "Skyscraper.app/Contents/MacOS/Skyscraper"
LINKS, OUT = HERE / "links", HERE / "scraped"
PLATFORMS = ["arcade", "neogeo", "gc", "wii"]
WII_KEEP = {"RSBE01", "SMNE01", "SF8E01", "RNPP69", "RX9P69", "SVME01", "SVTEXS", "STKE08", "RNCEH4"}
WII_TITLES = {"RSBE01": "Super Smash Bros. Brawl", "SMNE01": "New Super Mario Bros. Wii", "SF8E01": "Donkey Kong Country Returns",
              "RNPP69": "Need for Speed ProStreet", "RX9P69": "Need for Speed Undercover",
              "SVME01": "Super Mario All-Stars", "SVTEXS": "Bit.Trip Complete",
              "STKE08": "Tatsunoko vs. Capcom - Ultimate All-Stars", "RNCEH4": "SNK Arcade Classics Volume 1"}


def creds():
    acct = subprocess.run(["security", "find-generic-password", "-s", "screenscraper"], capture_output=True,
                          text=True).stdout
    user = next((l.split('="', 1)[1].rstrip('"') for l in acct.splitlines() if '"acct"' in l), None)
    pw = subprocess.run(["security", "find-generic-password", "-s", "screenscraper", "-w"], capture_output=True,
                        text=True).stdout.strip()
    if not user or not pw:
        raise SystemExit("ScreenScraper login not in Keychain (service 'screenscraper')")
    return user + ":" + pw


def placeholder(plat, name, key, keys):
    d = LINKS / plat
    d.mkdir(parents=True, exist_ok=True)
    f = d / name
    if not f.exists():
        f.write_bytes(("wii-launcher placeholder " + name).encode())   # unique bytes: Skyscraper caches by checksum
    keys.setdefault(plat, {})[name] = key


def links():
    keys = {}
    plan = json.load(open(HERE.parent / "sdkit/arcade_plan.json"))
    for row in plan:
        system, z, title = row[0], row[2], row[3]
        if not title:
            continue                          # parent/BIOS zips that aren't menu entries
        placeholder("neogeo" if system == "neogeo" else "arcade", z, z.rsplit(".", 1)[0], keys)
    for line in open(HERE / "gc_ids.txt"):
        gid, name = line.rstrip("\n").split("|", 1)
        stem = re.sub(r"\s*\[\w{6}\]$", "", name.rsplit(".", 1)[0] if name.lower().endswith((".iso", ".gcm", ".ciso")) else name)
        placeholder("gc", stem + ".iso", gid, keys)
    for gid in WII_KEEP:
        placeholder("wii", WII_TITLES[gid] + ".wbfs", gid, keys)
    json.dump(keys, open(HERE / "keys.json", "w"), indent=1)
    print({p: len(v) for p, v in keys.items()})


def run(args):
    shown = ["****" if i > 0 and args[i - 1] == "-u" else a for i, a in enumerate(args)]
    print("Skyscraper", " ".join(shown), flush=True)
    return subprocess.run([str(SKY)] + args).returncode


def gather(plats):
    u = creds()
    for p in plats:
        run(["-p", p, "-s", "screenscraper", "-t", "4", "-i", str(LINKS / p), "-u", u, "--flags", "videos,unattend,nohints,onlymissing"])


def generate(plats):
    for p in plats:
        o = OUT / p
        o.mkdir(parents=True, exist_ok=True)
        run(["-p", p, "-f", "emulationstation", "-i", str(LINKS / p), "-g", str(o), "-o", str(o / "media"),
             "-a", str(HERE / "artwork_wii.xml"), "--flags", "videos,unattend,nohints,relative"])


def map_videos():
    keys = json.load(open(HERE / "keys.json"))
    out = {}
    for p, names in keys.items():
        gl = OUT / p / "gamelist.xml"
        if not gl.exists():
            continue
        for g in ET.parse(gl).getroot().iter("game"):
            path, video = g.findtext("path") or "", g.findtext("video") or ""
            name = Path(path).name
            if name in names and video:
                v = (OUT / p / video).resolve() if not video.startswith("/") else Path(video)
                if v.exists():
                    out[names[name]] = str(v)
    json.dump(out, open(HERE / "videos.json", "w"), indent=1)
    total = sum(len(v) for v in keys.values())
    print(f"videos for {len(out)} of {total} games")


if __name__ == "__main__":
    cmd, rest = sys.argv[1], sys.argv[2:] or PLATFORMS
    {"links": lambda r: links(), "gather": gather, "generate": generate, "map": lambda r: map_videos()}[cmd](rest)
