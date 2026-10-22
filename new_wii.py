#!/usr/bin/env python3
"""A new Wii (running the launcher from a fresh card) -> a cabinet, the way cab1 was done on 2026-10-15. NEW_WII.md.
    new_wii.py <ip> check                  read-only: console id, Priiloader, its boot program, AHBPROT, the TV
                                           settings (480i, 60 Hz, 4:3: SYSCONF IPL.PGS / IPL.E60 / IPL.AR and the
                                           running video mode), card
    new_wii.py <ip> apply --yes [--no-menu] [--skip-hop-test]
                                           ONLY with the owner's OK for this console. Backs up, then writes (each read
                                           back): Priiloader main.bin = hop, main.nfo byte 0 = 1 (keep AHBPROT),
                                           loader.ini autoboot = file, SYSCONF (one write) IPL.AR = 0 (4:3),
                                           IPL.PGS = 0 (480i, not 480p), IPL.E60 = 1 (60 Hz; PAL consoles only have
                                           it). Then Wii Menu -> Priiloader -> hop -> launcher, and checks
                                           ahbprot=1 autobooted=1 and the video mode.
    new_wii.py <ip> cab <name>             sdkit/cabs/<id>.cfg (name + default.cfg's settings), onto the card, and
                                           devices.json, so fleet/status/report know it by name
WII_PORT=<port> for a simulator slot (4310 + slot)."""
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import wiiagent  # noqa: E402

wiiagent.PORT = int(os.environ.get("WII_PORT", wiiagent.PORT))
DATA = "/title/00000001/00000002/data"            # Priiloader's files (System Menu title's data folder)
LOADER_INI, MAIN_BIN, MAIN_NFO, SYSCONF = f"{DATA}/loader.ini", f"{DATA}/main.bin", f"{DATA}/main.nfo", "/shared2/sys/SYSCONF"
AUTOBOOT = {0: "off", 1: "hbc", 2: "bootmii", 3: "system_menu", 4: "file"}
HOP = open(os.path.join(HERE, "hop/hop.dol"), "rb").read()


def say(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


def info(ip, timeout=8):
    try:
        with wiiagent.Agent(ip, timeout=timeout) as a:   # (probe() gives the reply only 2 s: too short on busy Wi-Fi)
            return a.info()
    except OSError:
        return None


def nget(a, path):
    try:
        return a.nget(path)
    except (OSError, ValueError, IndexError):
        return None


def sysconf_byte(sc, name):
    """(offset, value) of a one-byte SYSCONF item, (-1, None) if there is none. SYSCONF: "SCv0", item count (BE16),
    item offsets (BE16); an item is a byte type << 5 | (name length - 1), the name, the value (type 3 = one byte)."""
    if not sc or sc[:4] != b"SCv0":
        return -1, None
    for i in range(int.from_bytes(sc[4:6], "big")):
        off = int.from_bytes(sc[6 + 2 * i:8 + 2 * i], "big")
        if off + 1 >= len(sc):
            continue
        t, n = sc[off] >> 5, (sc[off] & 0x1F) + 1
        if t == 3 and sc[off + 1:off + 1 + n] == name.encode() and off + 1 + n < len(sc):
            return off + 1 + n, sc[off + 1 + n]
    return -1, None


def ipl_ar(sc):
    return sysconf_byte(sc, "IPL.AR")


TV = {0: "NTSC", 1: "PAL", 2: "MPAL"}               # INFO tv= (CONF_GetVideo); the CRTs want 480i, 60 Hz, 4:3
SYSCONF_WANT = (("IPL.AR", 0, "4:3"), ("IPL.PGS", 0, "480i, progressive off"), ("IPL.E60", 1, "60 Hz"))


def tv_settings(sc, i):
    """[(good, text)] for the TV settings: SYSCONF IPL.PGS / IPL.E60 / IPL.AR and the running video mode.
    480p (PGS=1) gives no picture on a 15 kHz CRT, 50 Hz rolls or squashes, 16:9 squashes everything."""
    tv = int(i.get("tv", -1)) if str(i.get("tv", "")).lstrip("-").isdigit() else -1
    _, ar = sysconf_byte(sc, "IPL.AR")
    _, pgs = sysconf_byte(sc, "IPL.PGS")
    _, e60 = sysconf_byte(sc, "IPL.E60")
    fb = i.get("fb", "?")
    out = [(ar == 0, f"SYSCONF IPL.AR = {ar} (want 0 = 4:3)"),
           (pgs in (0, None), f"SYSCONF IPL.PGS = {'missing (= 480i)' if pgs is None else pgs} (want 0 = 480i; 1 = 480p, "
                              "no picture on the CRT)"),
           (e60 == 1 or (e60 is None and tv in (0, 2)),
            f"SYSCONF IPL.E60 = {'missing' if e60 is None else e60} on a {TV.get(tv, f'tv={tv}')} console (want 60 Hz: "
            + ("NTSC/MPAL are always 60 Hz" if tv in (0, 2) else "E60 = 1") + ")"),
           (tv in (0, 1, 2) and fb.endswith("x480"),
            f"running video mode: {TV.get(tv, f'tv={tv}')} framebuffer {fb} (want 480 lines: 480i/60; 574 = 50 Hz)")]
    return out


def read_state(ip):
    with wiiagent.Agent(ip, timeout=60) as a:
        st = {"info": a.info(), "data": None, "ini": nget(a, LOADER_INI), "bin": nget(a, MAIN_BIN),
              "nfo": nget(a, MAIN_NFO), "sysconf": nget(a, SYSCONF)}
        try:
            st["data"] = a.nls(DATA)
        except OSError:
            pass
        for p in ("sd:/apps/wii-agent/hop.dol", "sd:/arcade/update.cfg", f"sd:/arcade/cabs/{st['info'].get('id')}.cfg"):
            try:
                st[p] = a.get(p)
            except OSError:
                st[p] = None
    return st


def check(ip):
    st = read_state(ip)
    i, ok = st["info"], True
    def line(good, text):
        nonlocal ok
        ok &= bool(good)
        print(("  ok   " if good else "  TODO ") + text)
    print(f"{ip}: launcher {i.get('agent')}, console id {i.get('id')}, IOS{i.get('ios')}, cab {i.get('cab')}")
    line("nand" in i.get("caps", ""), "agent can read/write the allowed NAND files")
    ini = st["ini"]
    line(ini and len(ini) == 32, f"Priiloader installed (loader.ini {len(ini) if ini else 'missing'})")
    if ini:
        line(ini[0] == 4, f"Priiloader autoboot = {AUTOBOOT.get(ini[0], ini[0])} (want: file)")
    b = st["bin"]
    line(b is not None and b[:len(HOP)] == HOP,
         "main.bin = hop" if b and b[:len(HOP)] == HOP else
         f"main.bin is {'missing' if b is None else f'another program ({len(b)} bytes)'}; hop needs >= {len(HOP)} bytes"
         + ("" if b is None or len(b) >= len(HOP) else " -- TOO SMALL, see NEW_WII.md"))
    n = st["nfo"]
    line(n and n[0] == 1, f"main.nfo byte 0 = {n[0] if n else 'missing'} (want 1: keep AHBPROT for Nintendont / USB Loader GX)")
    for good, text in tv_settings(st["sysconf"], i):
        line(good, text)
    line(i.get("ahbprot") == "1", f"running with AHBPROT off: ahbprot={i.get('ahbprot')}")
    line(i.get("autobooted") == "1", f"started by Priiloader/hop at power-on: autobooted={i.get('autobooted')}")
    line(st["sd:/apps/wii-agent/hop.dol"] == HOP, "sd:/apps/wii-agent/hop.dol is the current hop")
    line(st["sd:/arcade/update.cfg"], "sd:/arcade/update.cfg (pull updates)")
    line(st[f"sd:/arcade/cabs/{i.get('id')}.cfg"], f"sd:/arcade/cabs/{i.get('id')}.cfg (name, screen) -- `cab` subcommand")
    print("all set" if ok else "not done yet")
    return ok


def wait_back(ip, timeout=300):
    time.sleep(8)
    end = time.time() + timeout
    while time.time() < end:
        i = info(ip)
        if i:
            return i
        time.sleep(5)
    return None


def write_checked(a, path, new):
    a.nput(path, new)
    back = a.nget(path)
    if back[:len(new)] != new:
        raise OSError(f"{path} did not read back as written -- stop and look before anything else")


def sysconf_fixed(sc):
    """SYSCONF with IPL.AR = 0, IPL.PGS = 0, IPL.E60 = 1 (only the items it has; same size, bytes changed in place)
    -> (new bytes, ["IPL.AR 1 -> 0 (4:3)", ...])."""
    new, changed = bytearray(sc), []
    for name, want, what in SYSCONF_WANT:
        k, v = sysconf_byte(sc, name)
        if k >= 0 and v != want:
            new[k] = want
            changed.append(f"{name} {v} -> {want} ({what})")
    return bytes(new), changed


def apply(ip, menu=True, hop_test=True):
    st = read_state(ip)
    i = st["info"]
    cid = i.get("id")
    if "nand" not in i.get("caps", ""):
        sys.exit("the running launcher can't write the NAND")
    if not st["ini"] or len(st["ini"]) != 32 or st["ini"][1:4] != b"\0\0\0":
        sys.exit("Priiloader's loader.ini is missing or has an unknown layout: install Priiloader first (NEW_WII.md)")
    if st["bin"] is None or len(st["bin"]) < len(HOP) or st["nfo"] is None:
        sys.exit(f"main.bin/main.nfo missing or main.bin < {len(HOP)} bytes: the agent can only overwrite in place. "
                 "Owner step B6 in NEW_WII.md (Priiloader 'Load/Install File' once).")
    if ipl_ar(st["sysconf"])[0] < 0:
        sys.exit("SYSCONF has no IPL.AR item: not editing it")
    tv = str(i.get("tv", ""))
    if tv == "1" and sysconf_byte(st["sysconf"], "IPL.E60")[0] < 0:
        sys.exit("a PAL console whose SYSCONF has no IPL.E60 item: can't switch it to 60 Hz, not editing anything")
    if st["sd:/apps/wii-agent/hop.dol"] != HOP:
        sys.exit("sd:/apps/wii-agent/hop.dol is missing or old: files_put hop/hop.dol there first")
    stamp = time.strftime("%Y%m%d-%H%M%S")
    os.makedirs(os.path.join(HERE, "backups"), exist_ok=True)
    for key, name in (("ini", "loader.ini"), ("bin", "priiloader-main.bin"), ("nfo", "priiloader-main.nfo"), ("sysconf", "SYSCONF")):
        path = os.path.join(HERE, "backups", f"{cid}-{name}.{stamp}")
        open(path, "wb").write(st[key])
        say("backed up", name, len(st[key]), "bytes ->", os.path.relpath(path, HERE))
    if hop_test and st["bin"][:len(HOP)] != HOP:   # hop from the card first (no NAND change): it must bring the launcher back
        with wiiagent.Agent(ip) as a:
            a.cmd("EXEC sd:/apps/wii-agent/hop.dol")
        j = wait_back(ip)
        if not j or j.get("autobooted") != "1":
            sys.exit(f"hop test from the card failed ({j}); nothing written")
        say("hop test ok: launcher back, autobooted=1")
    with wiiagent.Agent(ip, timeout=120) as a:
        if a.nget(MAIN_BIN)[:len(HOP)] != HOP:
            write_checked(a, MAIN_BIN, HOP); say("main.bin = hop, verified")
        nfo = a.nget(MAIN_NFO)
        if nfo[0] != 1:
            write_checked(a, MAIN_NFO, b"\x01" + nfo[1:]); say("main.nfo byte 0 = 1, verified")
        ini = a.nget(LOADER_INI)
        if ini[0] != 4:
            write_checked(a, LOADER_INI, b"\x04" + ini[1:]); say("Priiloader autoboot = file, verified")
        sc = a.nget(SYSCONF)
        new, changed = sysconf_fixed(sc)
        if changed:                                # one write for all three settings
            write_checked(a, SYSCONF, new); say("SYSCONF", ", ".join(changed) + ", verified")
        if menu:
            say("MENU:", a.cmd("MENU"))            # Wii Menu -> Priiloader -> hop -> launcher
    if menu:
        j = wait_back(ip)
        say("after Priiloader:", j and {k: j.get(k) for k in ("agent", "ahbprot", "autobooted", "ios", "tv", "fb")})
    else:
        say("--no-menu: SYSCONF changes (screen) take effect at the next start")
    return check(ip)


def cab(ip, name):
    import json
    i = info(ip)
    if not i:
        sys.exit(f"{ip}: the launcher doesn't answer")
    cid = i["id"]
    dflt = [l for l in open(os.path.join(HERE, "sdkit/cabs/default.cfg")) if l.strip() and not l.startswith(("#", "name"))]
    path = os.path.join(HERE, "sdkit/cabs", f"{cid}.cfg")
    if os.path.exists(path):
        text = "".join(l if not l.startswith("name") else f"name = {name}\n" for l in open(path))
    else:
        text = f"name = {name}\n" + "".join(dflt)
    sim = wiiagent.PORT != 4300                     # a simulator slot: only its card, not sdkit/cabs or devices.json
    if not sim:
        open(path, "w").write(text)
    with wiiagent.Agent(ip) as a:
        a.cmd("MKDIR sd:/arcade/cabs")
        a.put(f"sd:/arcade/cabs/{cid}.cfg", text.encode())
    dev_path = os.path.join(HERE, "devices.json")
    devs = json.load(open(dev_path)) if os.path.exists(dev_path) else {}
    if not sim:
        devs[cid] = {"ip": ip, "name": name}
        json.dump(devs, open(dev_path, "w"), indent=2)
    say(f"console {cid} is {name!r}: sdkit/cabs/{cid}.cfg written and put on the card (the launcher reads it at start)")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    ip, what = sys.argv[1], sys.argv[2]
    if what == "check":
        sys.exit(0 if check(ip) else 1)
    elif what == "apply":
        if "--yes" not in sys.argv:
            sys.exit("NAND writes: only with the owner's OK for this console; add --yes")
        apply(ip, menu="--no-menu" not in sys.argv, hop_test="--skip-hop-test" not in sys.argv)
    elif what == "cab" and len(sys.argv) > 3:
        cab(ip, sys.argv[3])
    else:
        sys.exit(__doc__)
