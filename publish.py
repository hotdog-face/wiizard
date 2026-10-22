#!/usr/bin/env python3
"""Publish what the cabinets should have to the update server (wiisite.UPDATE_SERVER, served from PUBLISH_HOST):
dist/files/<sd path> plus dist/manifest.txt ("<size> <crc32> <sd path>"). Cabinets (launcher 0.9.5+) fetch changes
by themselves while idle in attract mode. Games themselves (ROMs, disc images) stay on the cards (card installs).
    publish.py [--stage-only] [--no-ping]"""
import gzip, json, os, subprocess, sys, zlib
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import sdkit_install as k
import wiisite
HOST, ROOT = wiisite.PUBLISH_HOST, wiisite.PUBLISH_ROOT
STAGE = os.path.join(HERE, "dist")
V, KIT = os.path.join(HERE, "videos"), os.path.join(HERE, "sdkit")

def files():
    yield "apps/wii-agent/boot.dol", os.path.join(HERE, "agent/wii-agent.dol")
    yield "apps/wii-agent/hop.dol", os.path.join(HERE, "hop/hop.dol")
    yield "apps/nintendont/boot.dol", os.path.join(HERE, "sdkit/nintendont-swiirl.dol")
    for f in ("boot-r1272.dol", "meta.xml", "icon.png", "boot.dol"):   # USB Loader GX r1283: Wii games from SD
        yield f"apps/usbloader_gx/{f}", os.path.join(KIT, "usbloader_gx", f)
    if os.path.exists(os.path.join(KIT, "retroarch-swiirl", "TESTED")):   # only once the arcade test passed with them
        for f in sorted(os.listdir(os.path.join(KIT, "retroarch-swiirl"))):
            if f.endswith(".dol"): yield f"apps/retroarch-wii/{f}", os.path.join(KIT, "retroarch-swiirl", f)
    for f in ("hidden.txt", "meta.tsv", "collections.tsv", "hiscores.tsv", "controls.tsv"):
        if os.path.exists(os.path.join(KIT, f)): yield f"arcade/{f}", os.path.join(KIT, f)
    for f in os.listdir(os.path.join(KIT, "cabs")):
        if f.endswith(".cfg"): yield f"arcade/cabs/{f}", os.path.join(KIT, "cabs", f)
    for name, src in k.FONTS.items(): yield f"arcade/fonts/{name}", src
    for f in sorted(os.listdir(k.UI_ART)):
        if not f.startswith("."): yield f"arcade/ui/{f}", os.path.join(k.UI_ART, f)
    for src, dst in [("gvid", "arcade/video"), ("gvid_discs", "arcade/video"), ("gaud", "arcade/audio"),
                     ("covers", "arcade/art/covers"), ("stills", "arcade/art/stills")]:
        for f in sorted(os.listdir(os.path.join(V, src))):
            if not f.startswith("."): yield f"{dst}/{f}", os.path.join(V, src, f)
    for f in sorted(os.listdir(os.path.join(V, "art"))):
        system, stem = f.split("__", 1)
        yield f"arcade/art/{system}/{stem}", os.path.join(V, "art", f)
    for f in sorted(os.listdir(os.path.join(KIT, "sfx"))): yield f"arcade/sfx/{f}", os.path.join(KIT, "sfx", f)
    tree = os.path.join(KIT, "retroarch")
    for d, _, fs in os.walk(tree):
        for f in fs: yield "retroarch/" + os.path.relpath(os.path.join(d, f), tree), os.path.join(d, f)
    yield "retroarch/retroarch-core-options.cfg", os.path.join(KIT, "retroarch-core-options.cfg")
    yield "roms/arcade/hiscore.dat", os.path.join(HERE, "downloads/hiscore/hiscore.dat")   # MAME 2000 reads it here
    for line in open(os.path.join(KIT, "translations.tsv")):   # English-patched GameCube discs (CISO)
        p = line.rstrip("\n").split("\t")
        if len(p) >= 4 and not line.startswith("#"): yield f"games/{p[2]}/game.ciso", os.path.join(HERE, p[3])
    for system, f, *_ in k.consoles():                     # console classics: small ROMs, fine over Wi-Fi
        yield f"roms/{system}/{f}", os.path.join(k.CONSOLE_ROMS, system, f)

def generated():
    yield "apps/retroarch-wii/retroarch.cfg", k.RETROARCH_CFG.encode()
    hidden = {l.strip()[4:] for l in open(os.path.join(KIT, "hidden.txt")) if l.startswith("rom:")}
    tsv = []
    for r in json.load(open(os.path.join(KIT, "arcade_plan.json"))):
        system, nas_dir, z, title, year, maker = r[:6]
        if not title or z[:-4] in hidden: continue
        tsv.append(f"{system}\t{'neogeo.zip' if z == 'neogeo (1).zip' else z}\t{k.clean_title(title)}\t{year}\t{maker}\t{r[6]}")
    for system, f, title, year, maker, core in k.consoles():
        if f.rsplit(".", 1)[0] not in hidden: tsv.append(f"{system}\t{f}\t{title}\t{year}\t{maker}\t{core}")
    yield "arcade/arcade.tsv", ("\n".join(tsv) + "\n").encode()
    yield "arcade/update.cfg", k.UPDATE_CFG

def gz_copy(dst, data):
    """dst.gz next to the file when it saves 15%+ (launcher 0.9.21+ fetch it and inflate on the card). 0 = none."""
    gz = dst + ".gz"
    if len(data) < 16384:
        if os.path.exists(gz): os.remove(gz)
        return 0
    if not os.path.exists(gz) or os.path.getmtime(gz) < os.path.getmtime(dst):
        z = gzip.compress(data, 9, mtime=0)
        if len(z) > len(data) * 0.85:
            if os.path.exists(gz): os.remove(gz)
            return 0
        open(gz, "wb").write(z)
    return os.path.getsize(gz)

def main():
    if "-h" in sys.argv or "--help" in sys.argv: print(__doc__); return
    manifest, manifest2 = [], []
    for rel, src in files():
        dst = os.path.join(STAGE, "files", rel); os.makedirs(os.path.dirname(dst), exist_ok=True)
        if not os.path.exists(dst) or os.path.getsize(dst) != os.path.getsize(src) or os.path.getmtime(dst) < os.path.getmtime(src):
            subprocess.run(["cp", "-c", src, dst], check=True)
        data = open(dst, "rb").read()
        manifest.append(f"{len(data)} {zlib.crc32(data):08x} sd:/{rel}")
        manifest2.append(f"{len(data)} {zlib.crc32(data):08x} {gz_copy(dst, data)} sd:/{rel}")
    for rel, data in generated():
        dst = os.path.join(STAGE, "files", rel); os.makedirs(os.path.dirname(dst), exist_ok=True)
        if not os.path.exists(dst) or open(dst, "rb").read() != data: open(dst, "wb").write(data)
        manifest.append(f"{len(data)} {zlib.crc32(data):08x} sd:/{rel}")
        manifest2.append(f"{len(data)} {zlib.crc32(data):08x} {gz_copy(dst, data)} sd:/{rel}")
    # the launcher last: the cabinet installs everything else first
    # manifest.txt: "<size> <crc> <path>" for launchers before 0.9.21; manifest2.txt adds the .gz size (0 = none)
    for m, name in ((manifest, "manifest.txt"), (manifest2, "manifest2.txt")):
        m.sort(key=lambda l: l.endswith("apps/wii-agent/boot.dol"))
        open(os.path.join(STAGE, name), "w").write("\n".join(m) + "\n")
    if "--stage-only" in sys.argv:           # dist/ only: test it first (a local server + the simulator)
        print(len(manifest), "files staged in", STAGE, "(not published)"); return
    if not HOST: sys.exit("set publish_host / update_server in wiisite.json (or WII_PUBLISH_HOST)")
    subprocess.run(["rsync", "-a", "--delete", STAGE + "/", f"{HOST}:{ROOT}/"], check=True)
    print(len(manifest), "files published to", f"http://{wiisite.UPDATE_SERVER}/")
    if "--no-ping" not in sys.argv: ping_cabs()

def ping_cabs():
    """Tell every cabinet on the LAN to check for updates now (launcher 0.9.21+; older ones just answer ERR and
    pick the update up on their 3-hour timer)."""
    import fleet, wiiagent
    for ip, info in fleet.find_cabs().items():
        if str(info.get("id")) in fleet.SIM_IDS: continue
        try:
            with wiiagent.Agent(ip, timeout=15) as a: print(" ", ip, info.get("agent"), "UPDATE:", a.cmd("UPDATE").strip())
        except Exception as e: print(" ", ip, "not reached:", str(e)[:60])

if __name__ == "__main__":
    main()
