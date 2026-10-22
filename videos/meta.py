#!/usr/bin/env python3
"""meta.tsv for the launcher's showcase page, from Skyscraper's ScreenScraper cache: launcher key, players, rating
(0..1), genre, description. Also prints ratings for curation.  meta.py <out.tsv>"""
import hashlib
import html
import json
import os
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

HERE = Path(__file__).resolve().parent


def cache(plat):
    p = Path.home() / f".skyscraper/cache/{plat}/db.xml"
    data = {}
    if p.exists():
        for r in ET.parse(p).getroot():
            data.setdefault(r.get("id"), {})[r.get("type")] = r.text or ""
    return data


def main(out):
    """From Skyscraper's EmulationStation gamelists (scraped/<plat>/gamelist.xml), matched by file name."""
    keys = json.load(open(HERE / "keys.json"))
    rows = {}
    for plat, names in keys.items():
        gl = HERE / "scraped" / plat / "gamelist.xml"
        if not gl.exists():
            continue
        for g in ET.parse(gl).getroot().iter("game"):
            name = Path(g.findtext("path") or "").name
            if name not in names:
                continue
            desc = re.sub(r"\s+", " ", html.unescape(g.findtext("desc") or "")).strip()
            genre = (g.findtext("genre") or "").split(",")[0].strip()
            rows[names[name]] = (g.findtext("players") or "", g.findtext("rating") or "", genre, desc)
    with open(out, "w") as f:
        for key, (players, rating, genre, desc) in sorted(rows.items()):
            f.write(f"{key}\t{players}\t{rating}\t{genre}\t{desc[:1400]}\n")
    print(len(rows), "games with metadata")


if __name__ == "__main__":
    main(sys.argv[1])
