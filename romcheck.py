#!/usr/bin/env python3
"""Which arcade ZIPs will FB Alpha 2012 (the Wii's RetroArch arcade cores) actually run?
Parses the core's driver source (d_neogeo.cpp, d_cps1.cpp: ROM names, sizes, CRCs, parent/clone, BIOS) and checks
each ZIP's CRCs (read from the ZIP directory, nothing is extracted) against what that game needs, including
ROMs that live in its parent set.
    romcheck.py <driver.cpp> <zip listing .json> -> JSON report on stdout
The zip listing is {"name.zip": {"rom.bin": crc, ...}, ...} (see list_zips())."""
import json
import re
import sys
import zipfile

ROMDESC = re.compile(r"static\s+struct\s+BurnRomInfo\s+(\w+)RomDesc\[\]\s*=\s*\{(.*?)\};", re.S)
ROMLINE = re.compile(r'\{\s*"([^"]*)"\s*,\s*(0x[0-9a-fA-F]+|\d+)\s*,\s*(0x[0-9a-fA-F]+)\s*,\s*([^}]*)\}')
DRIVER = re.compile(r"struct\s+BurnDriver\w*\s+BurnDrv\w+\s*=\s*\{(.*?)\};", re.S)
STRING = re.compile(r'"((?:[^"\\]|\\.)*)"|NULL')


def parse_driver_source(text):
    roms = {}
    for name, body in ROMDESC.findall(text):
        entries = []
        for rname, size, crc, flags in ROMLINE.findall(body):
            if not rname:
                continue
            optional = "BRF_OPT" in flags or "BRF_NODUMP" in flags
            entries.append({"name": rname, "size": int(size, 0), "crc": int(crc, 16), "optional": optional,
                            "bios": "BRF_BIOS" in flags})
        roms[name] = entries
    games = {}
    for body in DRIVER.findall(text):
        strs = [m.group(1) for m in STRING.finditer(body)]
        if len(strs) < 6:
            continue
        short, parent, board = strs[0], strs[1], strs[2]
        # fields: name, parent, board(bios), sample, date, fullname, comment, manufacturer, ...
        title = strs[5] if len(strs) > 5 and strs[5] else short
        maker = strs[7] if len(strs) > 7 else ""
        year = strs[4] if len(strs) > 4 else ""
        rd = re.search(r"\b(\w+)RomInfo\s*,\s*(\w+)RomName", body)
        games[short] = {"parent": parent, "board": board, "title": title, "year": year, "maker": maker,
                        "romdesc": rd.group(1) if rd else short}
    return roms, games


MAME_ROMSTART = re.compile(r"ROM_START\(\s*(\w+)\s*\)(.*?)ROM_END", re.S)
MAME_ROMLOAD = re.compile(r'ROM_LOAD\w*\(\s*"([^"]+)"\s*,[^,]+,[^,]+,\s*(?:BADCRC\(\s*)?(0x[0-9a-fA-F]+)')
MAME_GAME = re.compile(r'\bGAMEX?\(\s*"?(\w*)"?\s*,\s*(\w+)\s*,\s*(\w+)\s*,[^,]*,[^,]*,[^,]*,[^,]*,\s*"([^"]*)"\s*,\s*"([^"]*)"')


def parse_mame037(texts):
    """MAME 0.37 drivers (mame2000-libretro src/drivers/*.c): ROM_START blocks and GAME() lines."""
    roms, games = {}, {}
    for text in texts:
        for name, body in MAME_ROMSTART.findall(text):
            roms[name] = [{"name": n, "size": 0, "crc": int(c, 16), "optional": False, "bios": False}
                          for n, c in MAME_ROMLOAD.findall(body) if int(c, 16)]
        for year, short, parent, maker, title in MAME_GAME.findall(text):
            games[short] = {"parent": "" if parent == "0" else parent, "board": "", "title": title, "year": year,
                            "maker": maker, "romdesc": short}
    return roms, games


def needed_roms(short, roms, games, seen=None):
    """CRCs the set must have (own ROMs, non-optional, non-BIOS)."""
    g = games.get(short)
    if not g:
        return []
    return [r for r in roms.get(g["romdesc"], []) if not r["optional"] and not r["bios"] and r["crc"]]


def check(listing, roms, games):
    report = {}
    for zipname, contents in listing.items():
        short = zipname.rsplit(".", 1)[0]
        g = games.get(short)
        if not g:
            report[zipname] = {"ok": False, "why": "not a game this core knows"}
            continue
        have = set(contents.values())
        if g["parent"] and g["parent"] + ".zip" in listing:
            have |= set(listing[g["parent"] + ".zip"].values())
        need = needed_roms(short, roms, games)
        missing = [r["name"] for r in need if r["crc"] not in have]
        report[zipname] = {"ok": not missing, "title": g["title"], "year": g["year"], "maker": g["maker"],
                           "parent": g["parent"], "missing": missing[:6], "needs": len(need)}
    return report


def list_zips(paths):
    out = {}
    for p in paths:
        try:
            with zipfile.ZipFile(p) as z:
                out[p.rsplit("/", 1)[-1]] = {i.filename.rsplit("/", 1)[-1].lower(): i.CRC for i in z.infolist()}
        except (zipfile.BadZipFile, OSError):
            out[p.rsplit("/", 1)[-1]] = {}
    return out


if __name__ == "__main__":
    src, listing = sys.argv[1], sys.argv[2]
    roms, games = parse_driver_source(open(src, encoding="latin-1").read())
    print(json.dumps(check(json.load(open(listing)), roms, games), indent=1))
