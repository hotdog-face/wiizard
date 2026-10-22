#!/usr/bin/env python3
"""Menu media for the console classics (sdkit/consoles.tsv: Genesis, SNES, NES), with the same pipeline as the
arcade and disc games: ScreenScraper through Skyscraper (scrape.py), convert.py, audio.py.
    consoles.py links | gather [plat..] | generate [plat..] | map | stills | art | meta <out.tsv>
links: links/<plat>/<NAS file name> -> the staged ROM (videos/roms/consoles/<system>/<card file>); the real ROMs,
so ScreenScraper matches by checksum. keys.json gets <plat>: {link name: vkey}, vkey = card file without extension.
map: videos_consoles.json (vkey -> mp4).  stills: stills/<vkey>.jpg = frame 40 of the clip (2 s in), as for the
others.  art: art/<system>__<vkey>.png = box art (screenshot if none), fit in 256x352, RGB."""
import io
import json
import struct
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import scrape
from PIL import Image

HERE = Path(__file__).resolve().parent
TSV = HERE.parent / "sdkit/consoles.tsv"
ROMS = HERE / "roms/consoles"
PLAT = {"genesis": "megadrive", "snes": "snes", "nes": "nes"}     # launcher system -> Skyscraper platform
PLATFORMS = list(PLAT.values())


def games():
    for line in open(TSV):
        if line.startswith("#") or not line.strip():
            continue
        system, card, title, year, maker, core, src = line.rstrip("\n").split("\t")
        yield system, card, Path(src).name, card.rsplit(".", 1)[0]


def links():
    keys = json.load(open(HERE / "keys.json"))
    for p in PLATFORMS:
        keys[p] = {}
    for system, card, name, vkey in games():
        d = scrape.LINKS / PLAT[system]
        d.mkdir(parents=True, exist_ok=True)
        f = d / name
        if f.is_symlink() or f.exists():
            f.unlink()
        f.symlink_to(ROMS / system / card)
        keys[PLAT[system]][name] = vkey
    json.dump(keys, open(HERE / "keys.json", "w"), indent=1)
    print({p: len(keys[p]) for p in PLATFORMS})


REGION = ["--region", "us", "--lang", "en"]     # US box art and titles (Skyscraper's default prefers eu)


def gather(plats):
    """As scrape.gather, plus REGION and --refresh (the cache already had these games from older scrapes, without
    videos, so onlymissing would skip them)."""
    u = scrape.creds()
    for p in plats or PLATFORMS:
        scrape.run(["-p", p, "-s", "screenscraper", "-t", "4", "-i", str(scrape.LINKS / p), "-u", u, "--refresh",
                    *REGION, "--flags", "videos,unattend,nohints"])


def generate(plats):
    for p in plats or PLATFORMS:
        o = scrape.OUT / p
        o.mkdir(parents=True, exist_ok=True)
        scrape.run(["-p", p, "-f", "emulationstation", "-i", str(scrape.LINKS / p), "-g", str(o), "-o", str(o / "media"),
                    "-a", str(HERE / "artwork_wii.xml"), *REGION, "--flags", "videos,unattend,nohints,relative"])


def gamelist(plat):
    gl = scrape.OUT / plat / "gamelist.xml"
    return ET.parse(gl).getroot().iter("game") if gl.exists() else []


def entries():
    """vkey -> (system, gamelist <game> element)."""
    keys = json.load(open(HERE / "keys.json"))
    sysof = {PLAT[s]: s for s in PLAT}
    out = {}
    for p in PLATFORMS:
        for g in gamelist(p):
            name = Path(g.findtext("path") or "").name
            if name in keys.get(p, {}):
                out[keys[p][name]] = (sysof[p], p, g)
    return out


def media(p, rel):
    if not rel:
        return None
    f = (scrape.OUT / p / rel).resolve() if not rel.startswith("/") else Path(rel)
    return f if f.exists() else None


def map_videos():
    out = {}
    for vkey, (system, p, g) in entries().items():
        v = media(p, g.findtext("video") or "")
        if v:
            out[vkey] = str(v)
    json.dump(out, open(HERE / "videos_consoles.json", "w"), indent=1)
    print(f"videos for {len(out)} of {len(list(games()))} games")


def frame(gvid, i):
    d = open(gvid, "rb").read()
    n = struct.unpack(">I", d[12:16])[0]
    offs = struct.unpack(f">{n + 1}I", d[16:16 + 4 * (n + 1)])
    i = min(i, n - 1)
    return Image.open(io.BytesIO(d[offs[i]:offs[i + 1]]))


def stills(index=40):
    n = 0
    for system, card, name, vkey in games():
        g = HERE / "gvid" / (vkey + ".gvid")
        if g.exists():
            frame(g, index).convert("RGB").save(HERE / "stills" / (vkey + ".jpg"), quality=88)
            n += 1
    print(n, "stills")


def art():
    found = entries()
    n, fallback = 0, []
    for system, card, name, vkey in games():
        if vkey not in found:
            continue
        _, p, g = found[vkey]
        src = media(p, g.findtext("thumbnail") or g.findtext("cover") or "")
        if not src:
            src = media(p, g.findtext("image") or g.findtext("screenshot") or "")
            fallback.append(vkey)
        if not src:
            continue
        im = Image.open(src).convert("RGB")
        im.thumbnail((256, 352), Image.LANCZOS)
        im.save(HERE / "art" / f"{system}__{vkey}.png", optimize=True)
        n += 1
    print(n, "art;", "screenshot instead of box art:", fallback)


if __name__ == "__main__":
    cmd, rest = sys.argv[1], sys.argv[2:]
    {"links": lambda r: links(), "gather": gather, "generate": generate, "map": lambda r: map_videos(),
     "stills": lambda r: stills(), "art": lambda r: art()}[cmd](rest)
