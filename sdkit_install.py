#!/usr/bin/env python3
"""Set up a Wii arcade cabinet's SD card mounted on the Mac (one card swap per cabinet).
Adds files only; anything it replaces is kept next to it (boot-prev.dol etc.). Never deletes. (Exception: a
GameCube disc that turns out to be the wrong disc/build, e.g. disc 2 or the 20XX hack, is overwritten with the
right one; the NAS backup keeps both.)
    sdkit_install.py /Volumes/WIISD [--games <games.tsv>] [--check-only] [--working-tree] [--any-cluster-size]
                     [--move-wii-games] [--remove-wii ID,ID,..]
First checks the card: the volume mounted at that path (nothing else is written), FAT32, 32 KB clusters (else
refused unless --any-cluster-size), and enough free space for what this run will copy. --check-only stops there.
Published files (everything publish.py stages: launcher, hop, Nintendont, USB Loader GX, RetroArch cores/config/
overrides, media, metadata, console ROMs, ...) come from dist/files as listed in dist/manifest.txt, so a new card
gets exactly what the fleet runs. --working-tree takes them from the working tree instead (unpublished builds).
--games (a new card): also copies every GameCube/Wii game the master cabinet has, GameCube as CISO (~27% smaller):
disc 1 (disc 2 as disc2.ciso next to it, Nintendont's multi-disc layout), never a hack over the retail disc;
nothing hidden in
sdkit/hidden.txt (disc ids, path rules, arcade/console ROMs) is copied.
Also installs: arcade ROM sets from the NAS (checked against the cores' ROM lists by romcheck.py, listed in
arcade/arcade.tsv), the Wii arcade picks into wbfs/ (unless hidden), the Priiloader installer, hiscore.dat for the
FB Alpha 2012 and MAME 2000 cores, arcade/update.cfg (pull updates) and arcade/installed.tsv (what of
dist/manifest.txt the card already has).
--move-wii-games moves games/Wii/<Title [ID]>/ to wbfs/ (where USB Loader GX looks), same card, instant.
--remove-wii deletes those Wii games from wbfs/ (only on the owner's say-so; they stay on the NAS / in the backup).
Gameplay clips (videos/gvid/<key>.gvid, made by videos/convert.py) go to arcade/video/."""
import json
import os
import plistlib
import re
import shlex
import shutil
import subprocess
import sys
import zlib

import wiisite

HERE = os.path.dirname(os.path.abspath(__file__))
KIT = os.path.join(HERE, "sdkit")
DIST_FILES = os.path.join(HERE, "dist/files")      # what publish.py staged (its STAGE/files) = what the fleet runs
MANIFEST = os.path.join(HERE, "dist/manifest.txt")
HISCORE_DAT = os.path.join(HERE, "downloads/hiscore/hiscore.dat")
HISCORE_DESTS = ("retroarch/savefiles/hiscore.dat", "retroarch/system/hiscore.dat",
                 "retroarch/system/fbalpha2012/hiscore.dat",       # the FB Alpha 2012 cores read system/fbalpha2012/
                 "retroarch/savefiles/FB Alpha 2012/hiscore.dat",  # FB Alpha 2012 burn/hiscore.cpp: the save folder
                 "roms/arcade/hiscore.dat")                        # MAME 2000 (fileio.c): the ROM folder
WANT_CLUSTER = 32768                                # Nintendont wants 32 KB clusters (macOS gives that on 128 GB)
NAS = wiisite.NAS                                  # user@host (ssh): the game library and card backups
NAS_WII = wiisite.NAS_WII                          # its folder of Wii WBFS files
# Wii games that play without the sensor bar (no pointer): the cabinets have no sensor bar
WII_ARCADE_PICKS = [
    "Tatsunoko vs. Capcom- Ultimate All-Stars [STKE08].wbfs",
    "Super Smash Bros Brawl [RSBE01].wbfs",
    "SNK Arcade Classics [RNCEH4].wbfs",
]
RA_CORES = ["fbalpha2012_neogeo_libretro_wii.dol", "fbalpha2012_cps1_libretro_wii.dol",
            "fbalpha2012_cps2_libretro_wii.dol", "fbalpha2012_libretro_wii.dol", "mame2000_libretro_wii.dol",
            "genesis_plus_gx_libretro_wii.dol", "snes9x2010_libretro_wii.dol", "fceumm_libretro_wii.dol"]  # consoles.tsv
UPDATE_CFG = f"server = {wiisite.UPDATE_SERVER}\n".encode()   # pull updates (publish.py); same as the published arcade/update.cfg
GVID = os.path.join(HERE, "videos/gvid")
RA_SRC = os.path.join(HERE, "downloads/retroarch-1.22.2/x/retroarch/apps/retroarch-wii")
NINTENDONT = os.path.join(KIT, "nintendont-swiirl.dol")   # our build (6.509 + exit combo, autotest, SWIIRL look); see nintendont/
FONTS = {"ui.ttf": "/System/Library/Fonts/Supplemental/Arial Rounded Bold.ttf",
         "display.ttf": "/System/Library/Fonts/Supplemental/DIN Condensed Bold.ttf",
         "body.ttf": "/System/Library/Fonts/Supplemental/DIN Alternate Bold.ttf",
         "term.ttf": "/System/Library/Fonts/Menlo.ttc",            # RetroArch's loading / returning line (wiizard_wii.c)
         "anton.ttf": os.path.join(KIT, "fonts/Anton-Regular.ttf"),           # the launcher's collage look (OFL)
         "archivo.ttf": os.path.join(KIT, "fonts/ArchivoBlack-Regular.ttf")}  # its small print (OFL)
UI_ART = os.path.join(KIT, "ui")   # the collage paper, the attract band, the wizard animation (art/make_ui.py) -> arcade/ui
# Every Wii must be set to 4:3 (SYSCONF IPL.AR = 0; cab1 was 16:9 and squashed everything until 2026-10-15): RetroArch
# takes the screen shape from it. Aspect 22 = the core's own (4:3, or 3:4 for vertical games).
# RetroArch for an arcade cabinet: straight into the game; L + R + Z + START quits back to the launcher (combo 3 =
# L1+R1+Start+Select: the same buttons Nintendont's R+Z+Start exit sits inside, so one exit for arcade and GameCube,
# and kids mashing Start + coin can't trigger it); kiosk mode hides every setting; per-game overrides in
# sd:/retroarch/config switch on the bezel overlays of vertical games (videos/bezels.py); aspect from the
# core (index 22 = ASPECT_RATIO_CORE in RetroArch 1.22) so vertical games aren't stretched to 4:3; 640x240
# (resolution id 20 in gx_gfx.c) = real 240p on the CRTs is only the fallback: every game / console core has an
# override in sdkit/retroarch/config (videos/av_fix/make_overrides.py) with its native line count and an integer
# multiple of its width, and the VI widens that to video_viwidth = 664 samples (4:3 for a 224-line picture; 640
# made everything ~10% too narrow). Audio: only the sinc resampler is compiled into the Wii build ("nearest" fell
# back to sinc quality 1); quality 2 = 8 taps. The old crackle was gx_audio's unaligned DMA chunks (fixed in our
# RetroArch build, videos/av_fix). audio_latency does nothing on the Wii driver (fixed 32 ms ring).
# Core options (high scores, free-play DIPs) from sdkit.
RETROARCH_CFG = """\
config_save_on_exit = "false"
quit_press_twice = "false"
input_quit_gamepad_combo = "3"
input_menu_toggle_gamepad_combo = "0"
pause_nonactive = "false"
video_smooth = "false"
savestate_auto_load = "false"
savestate_auto_save = "false"
system_directory = "sd:/retroarch/system"
input_autodetect_enable = "true"
menu_show_load_content_animation = "false"
notification_show_autoconfig = "false"
video_aspect_ratio_auto = "true"
aspect_ratio_index = "22"
audio_resampler = "sinc"
audio_resampler_quality = "2"
audio_latency = "96"
current_resolution_id = "20"
video_viwidth = "664"
input_remapping_directory = "sd:/retroarch/config/remaps"
auto_remaps_enable = "true"
global_core_options = "true"
core_options_path = "sd:/retroarch/retroarch-core-options.cfg"
kiosk_mode_enable = "true"
rgui_config_directory = "sd:/retroarch/config"
auto_overrides_enable = "true"
input_overlay_enable = "false"
network_cmd_enable = "true"
network_cmd_port = "55355"
input_axis_threshold = "0.35"
video_font_enable = "false"
notification_show_autoconfig_fails = "false"
notification_show_cheats_applied = "false"
notification_show_config_override_load = "false"
notification_show_disk_control = "false"
notification_show_fast_forward = "false"
notification_show_netplay_extra = "false"
notification_show_patch_applied = "false"
notification_show_refresh_rate = "false"
notification_show_remap_load = "false"
notification_show_save_state = "false"
notification_show_screenshot = "false"
notification_show_screenshot_flash = "0"
notification_show_set_initial_disk = "false"
notification_show_when_menu_is_alive = "false"
"""
# video_font_enable / notification_show_* (2026-10-21, Mitchell: "i dont want players to see things like that"): no
# RetroArch on-screen text at all (refresh-rate change on 240p, overrides/remaps loaded, autoconfig, save states...).
# video_font_enable is the master switch for RetroArch's OSD; the notification flags are belt and braces. No video
# setting changes (the picture baseline is locked, videos/av_fix/findings.md).
# input_axis_threshold (controls audit 2026-10-17, videos/controls_audit): the GameCube stick drives the d-pad
# (analog_dpad_mode in every sdkit/retroarch/config/remaps .rmp); its diagonals only reach ~0.55 of full scale,
# so the default 0.5 threshold made diagonals flaky on worn sticks.


def log(*a):
    print(*a, flush=True)


def put(src_bytes_or_path, dest, keep_old=None):
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    data = src_bytes_or_path if isinstance(src_bytes_or_path, bytes) else open(src_bytes_or_path, "rb").read()
    if os.path.exists(dest):
        if open(dest, "rb").read() == data:
            return "same"
        if keep_old and not os.path.exists(keep_old):
            shutil.copyfile(dest, keep_old)
    tmp = dest + ".part"
    with open(tmp, "wb") as f:
        f.write(data)
    os.replace(tmp, dest)
    return "written"


WBFS_SPLIT = 0xFFFF8000                     # FAT32 holds < 4 GiB per file: USB Loader GX reads <ID>.wbfs + .wbf1, ...


def wbfs_parts(dest, size):
    """The card files a disc image of this size becomes: one .wbfs, or split parts past WBFS_SPLIT."""
    if not dest.endswith(".wbfs") or size <= WBFS_SPLIT:
        return [(dest, size)]
    n = (size + WBFS_SPLIT - 1) // WBFS_SPLIT
    return [(dest if i == 0 else dest[:-1] + str(i), min(WBFS_SPLIT, size - i * WBFS_SPLIT)) for i in range(n)]


def stream_to(src, dest, size):
    """Copy a file object (or path) onto the card in 8 MiB chunks, split per wbfs_parts, each via .part."""
    parts = wbfs_parts(dest, size)
    if all(os.path.exists(d) and os.path.getsize(d) == n for d, n in parts):
        return "same"
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    f_in = open(src, "rb") if isinstance(src, str) else src
    try:
        for d, n in parts:
            with open(d + ".part", "wb") as f:
                left = n
                while left:
                    chunk = f_in.read(min(8 << 20, left))
                    if not chunk:
                        raise OSError(f"short copy for {d}")
                    f.write(chunk)
                    left -= len(chunk)
                f.flush(); os.fsync(f.fileno())
            os.replace(d + ".part", d)
    finally:
        if isinstance(src, str):
            f_in.close()
    return "copied" + (f" in {len(parts)} parts" if len(parts) > 1 else "")


def nas_local(nas_path):
    """The copy of a NAS file staged on the Mac (videos/roms), if there is one."""
    local = os.path.join(HERE, "videos/roms", os.path.basename(nas_path))
    if os.path.basename(nas_path) == "neogeo (1).zip":
        local = os.path.join(HERE, "videos/sys/neogeo.zip")
    return local if os.path.exists(local) else None


_NAS_SIZE = {}


def nas_sizes(paths):
    """Sizes of NAS files, one ssh for all of them (cached); -1 = not there."""
    todo = [p for p in dict.fromkeys(paths) if p not in _NAS_SIZE]
    if todo:
        r = subprocess.run(["ssh", "-o", "BatchMode=yes", NAS,
                            'while IFS= read -r f; do stat -c %s -- "$f" 2>/dev/null || echo -1; done'],
                           input="\n".join(todo) + "\n", capture_output=True, text=True)
        out = r.stdout.split()
        if r.returncode or len(out) != len(todo):
            sys.exit(f"can't read file sizes from the NAS ({NAS}): {r.stderr.strip()[:200]}")
        _NAS_SIZE.update(zip(todo, map(int, out)))
    return {p: _NAS_SIZE[p] for p in paths}


def from_nas(nas_path, dest):
    """Stream a NAS file onto the card (skips if the size already matches); uses the local copy staged in
    videos/roms when there is one."""
    local = nas_local(nas_path) or ""
    if os.path.exists(local):
        if dest.endswith(".wbfs"):
            return stream_to(local, dest, os.path.getsize(local))
        if os.path.exists(dest) and os.path.getsize(dest) == os.path.getsize(local):
            return "same"
        return "copied" if put(local, dest) else "copied"
    size = nas_sizes([nas_path])[nas_path]
    if size < 0:
        raise OSError(f"not on the NAS: {nas_path}")
    if dest.endswith(".wbfs"):
        proc = subprocess.Popen(["ssh", "-o", "BatchMode=yes", NAS, f"cat {shlex.quote(nas_path)}"], stdout=subprocess.PIPE)
        try:
            return stream_to(proc.stdout, dest, size)
        finally:
            proc.kill(); proc.wait()
    if os.path.exists(dest) and os.path.getsize(dest) == size:
        return "same"
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    tmp = dest + ".part"
    with open(tmp, "wb") as f:
        subprocess.run(["ssh", "-o", "BatchMode=yes", NAS, f"cat {shlex.quote(nas_path)}"], stdout=f, check=True)
    if os.path.getsize(tmp) != size:
        raise OSError(f"short copy of {nas_path}")
    os.replace(tmp, dest)
    return "copied"


def consoles():
    """Console classics (sdkit/consoles.tsv): (system, card file, title, year, maker, core); ROMs staged in
    videos/roms/consoles/<system>/<file> (copied from the NAS paths in the last column)."""
    for l in open(os.path.join(KIT, "consoles.tsv")):
        if l.strip() and not l.startswith("#"):
            yield tuple(l.rstrip("\n").split("\t")[:6])


CONSOLE_ROMS = os.path.join(HERE, "videos/roms/consoles")


USBLGX_PASSWORD = wiisite.USBLGX_PASSWORD   # unlocks USB Loader GX's settings (wiisite.json / WII_USBLGX_PASSWORD)


def lock_usbloader(card):
    """USB Loader GX only shows its own menu if a Wii game fails to boot; lock its settings there (parental lock)."""
    if not USBLGX_PASSWORD:
        log("usb loader gx: not locked (no usblgx_password in wiisite.json)")
        return
    cfgs = (f"{card}/apps/usbloader_gx/GXGlobal.cfg", f"{card}/config/usbloader_gx/GXGlobal.cfg")
    if not any(os.path.exists(c) for c in cfgs):   # a new card: USB Loader GX would start unlocked (godmode 1);
        put(b"", cfgs[0])                          # it keeps its defaults for every key not in the file
    for cfg in cfgs:
        if not os.path.exists(cfg):
            continue
        text = open(cfg, errors="replace").read()
        for key, val in (("godmode", "0"), ("password", USBLGX_PASSWORD), ("RememberUnlock", "0")):
            if re.search(rf"^{key} = .*$", text, flags=re.M):
                text = re.sub(rf"^{key} = .*$", f"{key} = {val}", text, flags=re.M)
            else:
                text += f"{key} = {val}\n"
        log("usb loader gx:", put(text.encode(), cfg), "(settings locked)")


BACKUP = wiisite.NAS_BACKUP                        # the master card's backup on the NAS (sd_backup.py)
CISO_BLOCK = 2 << 20


def ssh_read(path, offset, size):
    cmd = f"dd if={shlex.quote(path)} bs=4096 skip={offset // 4096} count={(size + offset % 4096 + 4095) // 4096} 2>/dev/null"
    data = subprocess.run(["ssh", "-o", "BatchMode=yes", NAS, cmd], capture_output=True, check=True).stdout
    return data[offset % 4096:offset % 4096 + size]


def gc_used_blocks(path):
    """2 MiB blocks a GameCube image actually uses: header, apploader, main program, file table, and every file.
    Returns (used blocks, the disc's first 0x440 bytes)."""
    import struct
    hdr = ssh_read(path, 0, 0x440)
    fst_off, fst_size = struct.unpack(">II", hdr[0x424:0x42C])
    fst = ssh_read(path, fst_off, fst_size)
    used = set(range(0, (fst_off + fst_size + CISO_BLOCK - 1) // CISO_BLOCK))
    for i in range(1, struct.unpack(">I", fst[8:12])[0]):
        e = fst[i * 12:(i + 1) * 12]
        if e[0] == 0:
            off, size = struct.unpack(">II", e[4:12])
            used.update(range(off // CISO_BLOCK, (off + max(size, 1) - 1) // CISO_BLOCK + 1))
    return used, hdr


_GC = {}


def gc_layout(nas_path):
    """(used blocks < nblocks, disc header, image size, nblocks) of a GameCube image on the NAS (cached)."""
    if nas_path not in _GC:
        total = nas_sizes([nas_path])[nas_path]
        if total < 0:
            raise OSError(f"not on the NAS: {nas_path}")
        used, hdr = gc_used_blocks(nas_path)
        nblocks = (total + CISO_BLOCK - 1) // CISO_BLOCK
        _GC[nas_path] = ({b for b in used if b < nblocks}, hdr, total, nblocks)
    return _GC[nas_path]


def ciso_size(nas_path):
    used, _, total, _ = gc_layout(nas_path)
    return 0x8000 + sum(min((b + 1) * CISO_BLOCK, total) - b * CISO_BLOCK for b in used)


def ciso_matches(dest, nas_path):
    """Is the CISO on the card this exact NAS image (same disc header, block map and size)? For ids with several
    images (disc 1/2, a hack build) "a file is there" isn't enough."""
    used, hdr, _, nblocks = gc_layout(nas_path)
    with open(dest, "rb") as f:
        head = f.read(0x8000 + len(hdr))
    want_map = bytes(1 if b in used else 0 for b in range(nblocks))
    return (os.path.getsize(dest) == ciso_size(nas_path) and head[8:8 + nblocks] == want_map
            and head[0x8000:] == hdr)


def copy_ciso(nas_path, dest, verify=False):
    """A GameCube image as CISO (what Nintendont reads; unused space left out, about 27% smaller): "CISO", block
    size (LE), a used-block map, padded to 0x8000, then the used blocks in order. verify: an existing file must be
    this image; a different disc/build there is overwritten in place (its clusters reused, so a sparse dry-run image
    doesn't grow), through .part so an interrupted copy is never taken for a finished one."""
    import struct
    tmp = dest + ".part"
    note = ""
    if os.path.exists(dest):
        if not verify or ciso_matches(dest, nas_path):
            return "same"
        os.replace(dest, tmp)
        note = ", replaced a different disc/build"
    used, _, total, nblocks = gc_layout(nas_path)
    header = bytearray(0x8000)
    header[0:8] = b"CISO" + struct.pack("<I", CISO_BLOCK)
    for b in used:
        header[8 + b] = 1
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    runs = []                                    # read only the used blocks, a run at a time
    for b in sorted(used):
        if runs and runs[-1][1] == b:
            runs[-1][1] = b + 1
        else:
            runs.append([b, b + 1])
    with open(tmp, "r+b" if os.path.exists(tmp) else "wb") as f:
        f.seek(0)
        f.write(header)
        for start, end in runs:
            cmd = f"dd if={shlex.quote(nas_path)} bs={CISO_BLOCK} skip={start} count={end - start} 2>/dev/null"
            data = subprocess.run(["ssh", "-o", "BatchMode=yes", NAS, cmd], capture_output=True, check=True).stdout
            want = min(end * CISO_BLOCK, total) - start * CISO_BLOCK
            if len(data) != want:
                raise OSError(f"short read of {nas_path} blocks {start}-{end}")
            f.write(data)                        # the last block may be short; Nintendont reads it as is
        f.truncate()
        f.flush(); os.fsync(f.fileno())
    os.replace(tmp, dest)
    return f"copied ({len(used) * CISO_BLOCK / 2**30:.2f} of {total / 2**30:.2f} GiB{note})"


def gc_source(name):
    """A videos/gc_ids.txt entry on the NAS backup: "<name>.iso", or a folder "<name>" holding game.iso (Pikmin,
    Paper Mario, Pokemon, ...)."""
    src = f"{BACKUP}/games/{name}".replace("Pac-Man Vs./", "Pac-Man Vs (trailing dot)/")
    return src if name.lower().endswith((".iso", ".gcm", ".ciso")) else src + "/game.iso"


def load_hidden():
    """sdkit/hidden.txt: id:<disc id>, rom:<zip stem>, path:<part of a path> (the launcher's rules, catalog.c)."""
    h = {"id": set(), "rom": set(), "path": []}
    for line in open(os.path.join(KIT, "hidden.txt")):
        kind, _, val = line.strip().partition(":")
        if line.startswith("#") or not val:
            continue
        if kind == "path":
            h["path"].append(val)
        elif kind in h:
            h[kind].add(val)
    return h


def is_hidden(h, gid, *paths):
    return gid in h["id"] or any(r in p for r in h["path"] for p in paths)


GC_HACK = re.compile(r"20XX|\bhack(ed)?\b", re.I)   # hack builds sharing a retail id (Melee 20XX = GALE01)
GC_PREFER = {"GALE01": "20XX"}   # ...except where a hack is the pick: Melee 20XX, "more arcady" (Mitchell 2026-10-17)
DISC_NO = re.compile(r"\s*\(Disc (\d)\)", re.I)


def gc_name_title(name):
    """"Resident Evil 4 (USA) (Disc 1).iso" -> "residentevil4": compared with games.tsv titles."""
    t = re.sub(r"\.(iso|gcm|ciso)$", "", name, flags=re.I)
    t = re.sub(r"(\s*\([^()]*\))+\s*$", "", t)
    return re.sub(r"[^a-z0-9]", "", t.lower())


def gc_pick(gid, title, cands):
    """(disc 1 entry, disc 2 entry or None) for a disc id from videos/gc_ids.txt's entries for it. Never a hack
    build when the id has the retail disc too (Melee 20XX; a hack that is the only entry, F-Zero AX, is the game);
    disc 1 of a two-disc game; when one id is two games (PSO Episode I & II vs. Plus), the one whose name is the
    title."""
    pref = GC_PREFER.get(gid)
    ok = [n for n in cands if pref and pref in n] or [n for n in cands if not GC_HACK.search(n)] or list(cands)
    if title:
        same = [n for n in ok if gc_name_title(n) == re.sub(r"[^a-z0-9]", "", title.lower())]
        ok = same or ok
    disc = lambda n: int(DISC_NO.search(n).group(1)) if DISC_NO.search(n) else 1
    first = next((n for n in ok if disc(n) == 1), None)
    second = next((n for n in ok if disc(n) == 2), None) if first else None
    return first, second


def gc_candidates():
    cands = {}
    for line in open(os.path.join(HERE, "videos/gc_ids.txt")):
        gid, name = line.rstrip("\n").split("|", 1)
        cands.setdefault(gid, []).append(name)
    return cands


def disc_jobs(card, master, hidden):
    """What --games copies from the master cabinet's library (fleet/cabs/<id>/games.tsv), from cab1's card backup
    on the NAS: [(kind, label, NAS path, card path, verify)]. GameCube: games/<Title [ID]>/game.ciso (+ disc2.ciso);
    Wii: wbfs/<Title [ID]>/<ID>.wbfs. Hidden games (sdkit/hidden.txt) are left out."""
    cands = gc_candidates()
    translated = {l.split("\t")[0] for l in open(os.path.join(KIT, "translations.tsv")) if not l.startswith("#") and "\t" in l}
    listing = gc_have = None
    jobs = []
    for line in open(master):
        p = line.rstrip("\n").split("\t")
        if len(p) < 4:
            continue
        system, gid, title = p[1], p[2], p[3]
        if system == "NINTENDO GAMECUBE":
            if gid in translated:               # staged English discs: copied with the translations (main install)
                continue
            if gid not in cands:
                log(f"  ? {gid} {title}: not in the disc list")
                continue
            first, second = gc_pick(gid, title, cands[gid])
            folder = re.sub(r"[\\/:*?\"<>|]", "", title).rstrip(". ") + f" [{gid}]"
            if gc_have is None:
                gc_have = sorted(os.listdir(f"{card}/games")) if os.path.isdir(f"{card}/games") else []
            same_id = [d for d in gc_have if d.endswith(f" [{gid}]") and not d.startswith(".")]
            if folder not in gc_have and len(same_id) == 1:
                folder = same_id[0]             # a card made under an older title ("Legend of Zelda, The - ..."
                                                # before launcher 0.9.18 moved ", The" to the front): no 2nd copy
            if not first:
                log(f"  ? {gid} {title}: only a disc 2 in the disc list, not copied")
                continue
            if is_hidden(hidden, gid, first, f"sd:/games/{folder}/game.ciso"):
                log(f"  - gc {title} [{gid}]: hidden in sdkit/hidden.txt, not copied")
                continue
            multi = len(cands[gid]) > 1
            jobs.append(("gc", title, gc_source(first), f"{card}/games/{folder}/game.ciso", multi))
            if second:                          # Nintendont finds disc2.* next to game.* (kernel/DI.c)
                jobs.append(("gc", f"{title} (disc 2)", gc_source(second), f"{card}/games/{folder}/disc2.ciso", True))
        elif system == "NINTENDO WII":
            if gid in hidden["id"]:
                log(f"  - wii {title} [{gid}]: hidden in sdkit/hidden.txt, not copied")
                continue
            if listing is None:
                listing = subprocess.run(["ssh", "-o", "BatchMode=yes", NAS, f"cd {shlex.quote(BACKUP)} && find games wbfs -name '*.wbfs'"],
                                         capture_output=True, text=True).stdout.splitlines()   # paths have spaces
            src = next((l for l in listing if l.endswith(f"/{gid}.wbfs")), None)
            pick = next((f for f in WII_ARCADE_PICKS if f"[{gid}]" in f), None)
            if src:
                folder = src.split("/")[-2]
                src = f"{BACKUP}/{src}"
            elif pick:
                folder, src = pick.rsplit(".", 1)[0], f"{NAS_WII}/{pick}"
            else:
                log(f"  ? {gid} {title}: not found on the NAS")
                continue
            dest = f"{card}/wbfs/{folder}/{gid}.wbfs"
            if is_hidden(hidden, gid, src, "sd:" + dest[len(card):]):
                log(f"  - wii {folder}: hidden in sdkit/hidden.txt, not copied")
                continue
            jobs.append(("wii", folder, src, dest, False))
    return jobs


def copy_discs(jobs):
    for kind, label, src, dest, verify in jobs:
        if kind == "gc":
            # cards from before CISO (cab1) hold full-size game.iso: the same disc there counts as installed, or the
            # launcher (which reads game.iso first) would keep using it beside a second, compressed copy (84 GB)
            iso = os.path.join(os.path.dirname(dest), "game.iso")
            if dest.endswith("/game.ciso") and os.path.exists(iso) and not os.path.exists(dest):
                hdr = gc_layout(src)[1]
                with open(iso, "rb") as f:
                    if not verify or f.read(len(hdr)) == hdr:
                        log(f"  gc {label}: same (full-size game.iso)")
                        continue
                log(f"  gc {label}: game.iso there is another disc/build; game.ciso written beside it, remove game.iso "
                    f"(with the owner's OK) so the launcher uses the new one")
            log(f"  gc {label}:", copy_ciso(src, dest, verify))
        else:
            log(f"  wii {label}:", from_nas(src, dest))


def clean_title(t):
    t = t.split("\\0")[0].split("\x00")[0]
    t = t.split(" / ")[0]
    while True:                               # drop trailing "(set 1)", "(NGM-047)(NGH-047)", "(World 910522)"
        m = re.search(r"\s*\([^()]*\)\s*$", t)
        if not m:
            break
        t = t[:m.start()]
    small = {"a", "an", "and", "at", "by", "for", "in", "of", "on", "or", "the", "to", "vs", "vs."}
    words = t.strip().split(" ")              # MAME/FBA names are often lower case: "19XX - the war against destiny"
    return " ".join(w[:1].upper() + w[1:] if w.islower() and (i == 0 or w not in small or words[i - 1] in ("-", ":")
                                                               or words[i - 1].endswith(":")) else w
                    for i, w in enumerate(words))


def file_crc(path):
    c = 0
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            c = zlib.crc32(b, c)
    return c


def read_manifest():
    """dist/manifest.txt -> [(card path, size, crc)]"""
    rows = []
    for line in open(MANIFEST):
        size, crc, path = line.rstrip("\n").split(" ", 2)
        rows.append((path[4:], int(size), int(crc, 16)))
    return rows


def record_installed(card, known=None):
    """sd:/arcade/installed.tsv ("<sd path>\t<size>\t<crc32>"), what the pull updater compares the manifest with:
    every published file (dist/manifest.txt) that is on the card with the published size and CRC, so the cabinet
    neither re-fetches nor re-reads them. Anything that differs is left out, and the cabinet fetches it.
    known: {card path: (size, crc)} already checked on the card by install_published (not read again)."""
    if not os.path.exists(MANIFEST):
        return
    known = known or {}
    rows = []
    for rel, size, crc in read_manifest():
        dest = f"{card}/{rel}"
        if known.get(rel) == (size, crc) or (os.path.exists(dest) and os.path.getsize(dest) == size
                                             and file_crc(dest) == crc):
            rows.append(f"sd:/{rel}\t{size}\t{crc:08x}\n")
    put("".join(rows).encode(), f"{card}/arcade/installed.tsv")
    log(f"installed.tsv: {len(rows)} of the published files are on the card as published")


KEEP_PREV = {"apps/wii-agent/boot.dol": "apps/wii-agent/boot-prev.dol",
             "apps/nintendont/boot.dol": "apps/nintendont/boot-prev.dol"}


def copy_checked(src, dest):
    """Copy via .part, fsynced; returns the CRC of what was written."""
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    tmp, c = dest + ".part", 0
    with open(src, "rb") as fi, open(tmp, "wb") as fo:
        for b in iter(lambda: fi.read(8 << 20), b""):
            fo.write(b)
            c = zlib.crc32(b, c)
        fo.flush(); os.fsync(fo.fileno())
    os.replace(tmp, dest)
    return c


def install_published(card):
    """Every file of dist/manifest.txt, from dist/files (what publish.py staged; the fleet runs exactly this), the
    launcher last. Keeps the card's update.cfg and a cabinet's own screen calibration (as the working-tree install
    does); the replaced launcher / Nintendont stay as boot-prev.dol. Returns {card path: (size, crc)} of the files
    now on the card as published."""
    known, stale, written, same, kept = {}, [], 0, 0, 0
    cabs = os.path.join(KIT, "cabs")
    for rel, size, crc in sorted(read_manifest(), key=lambda r: r[0] == "apps/wii-agent/boot.dol"):
        src, dest = os.path.join(DIST_FILES, rel), f"{card}/{rel}"
        if rel == "arcade/update.cfg" and os.path.exists(dest):
            kept += 1                                   # this card's update server
            continue
        if (rel.startswith("arcade/cabs/") and os.path.exists(dest) and os.path.exists(src)
                and "screen =" in open(dest, errors="replace").read() and "screen =" not in open(src, errors="replace").read()):
            shutil.copyfile(dest, os.path.join(cabs, os.path.basename(rel)))   # the card knows this TV better: keep
            kept += 1                                                          # it, learn it
            continue
        if os.path.exists(dest) and os.path.getsize(dest) == size and file_crc(dest) == crc:
            known[rel] = (size, crc)
            same += 1
            continue
        if not os.path.exists(src) or os.path.getsize(src) != size:
            stale.append(rel)
            continue
        prev = KEEP_PREV.get(rel)
        if prev and os.path.exists(dest) and not os.path.exists(f"{card}/{prev}"):
            shutil.copyfile(dest, f"{card}/{prev}")
        if copy_checked(src, dest) == crc:
            known[rel] = (size, crc)
            written += 1
        else:
            stale.append(rel)                           # dist/files changed under us (a publish running?)
        if rel == "apps/wii-agent/boot.dol":
            log("launcher: written from dist/files")
    log(f"published files (dist/files): {written} written, {same} already there, {kept} kept as the card has them")
    if stale:
        log(f"WARNING: {len(stale)} files in dist/files don't match dist/manifest.txt (publish.py running or not run "
            f"since a change?); left for the cabinet's pull update: {', '.join(stale[:8])}{' ...' if len(stale) > 8 else ''}")
    if os.path.exists(os.path.join(HERE, "agent/wii-agent.dol")) and os.path.exists(os.path.join(DIST_FILES, "apps/wii-agent/boot.dol")) \
            and file_crc(os.path.join(HERE, "agent/wii-agent.dol")) != file_crc(os.path.join(DIST_FILES, "apps/wii-agent/boot.dol")):
        log("note: agent/wii-agent.dol (working tree) is not the published launcher; the card got the published one "
            "(publish.py first, or --working-tree, to give it the new build)")
    return known


def card_check(card, allow_cluster=False):
    """The card volume itself: mounted at exactly this path (so nothing lands on another volume), FAT32, 32 KB
    clusters, writable. Returns (cluster bytes, free bytes). Exits with the reason otherwise."""
    real = os.path.realpath(card)
    if real == "/" or not os.path.ismount(real):
        sys.exit(f"{card} is not the mount point of a card (want the volume itself, e.g. /Volumes/WIISD); nothing written")
    st = os.statvfs(real)
    free, cluster = st.f_bavail * st.f_frsize, st.f_frsize
    if sys.platform == "darwin":
        r = subprocess.run(["diskutil", "info", "-plist", real], capture_output=True)
        if r.returncode:
            sys.exit(f"diskutil doesn't know {card}: {r.stderr.decode(errors='replace').strip()[:200]}")
        d = plistlib.loads(r.stdout)
        if os.path.realpath(d.get("MountPoint") or "") != real:
            sys.exit(f"{card} is inside {d.get('MountPoint')}, not a card volume of its own; nothing written")
        if d.get("FilesystemType") != "msdos" or "FAT32" not in (d.get("FilesystemName") or ""):
            sys.exit(f"{card} is {d.get('FilesystemUserVisibleName') or d.get('FilesystemType')}, not FAT32: the Wii "
                     "(Homebrew Channel, Nintendont, USB Loader GX) needs FAT32. A new, empty card: check the disk with "
                     "`diskutil list`, then `diskutil eraseDisk FAT32 WIISD MBRFormat /dev/diskN` (NEW_WII.md step 1)")
        if d.get("Internal") and d.get("BusProtocol") != "Disk Image":
            sys.exit(f"{card} is on an internal disk ({d.get('DeviceIdentifier')}), not an SD card; nothing written")
        if d.get("WritableVolume") is False:
            sys.exit(f"{card} is read-only (the SD card's lock switch?)")
        cluster = d.get("VolumeAllocationBlockSize") or cluster
        log(f"card: {d.get('DeviceIdentifier')} {d.get('FilesystemName')}, {cluster // 1024} KB clusters, "
            f"{d.get('TotalSize', 0) / 1e9:.1f} GB, {free / 2**30:.1f} GiB free ({d.get('BusProtocol')})")
    else:
        log(f"card: not macOS, so no diskutil: the format isn't checked; {free / 2**30:.1f} GiB free")
    if cluster != WANT_CLUSTER:
        msg = (f"{card} has {cluster // 1024} KB clusters; Nintendont wants 32 KB (smooth disc streaming). macOS gives "
               "32 KB when it formats a 64-128 GB card FAT32 (NEW_WII.md step 1)")
        if not allow_cluster:
            sys.exit(msg + ". Reformat it, or pass --any-cluster-size to use it anyway")
        log("WARNING:", msg)
    return cluster, free


def estimate(card, cluster, worktree, jobs, hidden):
    """Bytes this run will add to the card (rounded to clusters; replaced files count by how much they grow),
    and the biggest single copy (its .part needs room next to the old file)."""
    rnd = lambda n: -(-n // cluster) * cluster
    total, biggest, new_files = 0, 0, 0

    def add(dest, size, in_place=False):
        nonlocal total, biggest, new_files
        old = os.path.getsize(dest) if os.path.exists(dest) else None
        if old == size:
            return
        new_files += old is None
        total += max(0, rnd(size) - (rnd(old) if old is not None else 0))
        if old is not None and not in_place:
            biggest = max(biggest, size)
    for rel, size, _ in read_manifest() if os.path.exists(MANIFEST) else []:   # (--working-tree: about the same)
        add(f"{card}/{rel}", size)
    roms = []
    for row in json.load(open(os.path.join(KIT, "arcade_plan.json"))):
        system, nas_dir, z = row[:3]
        dest = f"{card}/roms/{system}/{'neogeo.zip' if z == 'neogeo (1).zip' else z}"
        if z[:-4] not in hidden["rom"] and not os.path.exists(dest):
            roms.append((f"{nas_dir}/{z}", dest))
    wii = [(f"{NAS_WII}/{f}", f"{card}/wbfs/{f.rsplit('.', 1)[0]}/{re.search(r'\[(\w{6})\]', f).group(1)}.wbfs")
           for f in WII_ARCADE_PICKS if re.search(r"\[(\w{6})\]", f).group(1) not in hidden["id"]]
    wii += [(src, dest) for kind, _, src, dest, _ in jobs if kind == "wii"]
    wii = [(s, d) for s, d in wii if not os.path.exists(d)]
    sizes = nas_sizes([s for s, _ in roms if not nas_local(s)] + [s for s, _ in wii])
    for s, d in roms:
        add(d, os.path.getsize(nas_local(s)) if nas_local(s) else max(sizes[s], 0))
    for s, d in wii:
        for part, n in wbfs_parts(d, max(sizes[s], 0)):
            add(part, n)
    for kind, _, src, dest, verify in jobs:
        if kind == "gc" and not (os.path.exists(dest) and (not verify or ciso_matches(dest, src))):
            add(dest, ciso_size(src), in_place=True)
    return total, biggest, new_files



def remove_appledouble(card):
    """macOS tags every file this script writes (com.apple.provenance), and on FAT32 that becomes a "._<name>"
    AppleDouble file next to each file and folder (~2000 on a new card, a 32 KB cluster each). Wii software doesn't
    want them; remove only real AppleDouble files (magic 00051607) whose companion exists."""
    n = 0
    for dirpath, dirs, files in os.walk(card):
        dirs[:] = [d for d in dirs if d not in (".Spotlight-V100", ".fseventsd", ".Trashes")]
        for f in files:
            p = os.path.join(dirpath, f)
            if f.startswith("._") and os.path.exists(os.path.join(dirpath, f[2:])) and os.path.getsize(p) <= 65536:
                with open(p, "rb") as fh:
                    if fh.read(4) != b"\x00\x05\x16\x07":
                        continue
                os.remove(p)
                n += 1
    if n:
        log(f"removed {n} macOS '._' metadata files")


def main(card, move_wii, remove_wii=(), games_from=None, worktree=False, check_only=False, any_cluster=False):
    card = os.path.realpath(card)
    cluster, free = card_check(card, any_cluster)
    if not worktree and not os.path.exists(MANIFEST):
        sys.exit("no dist/manifest.txt: run publish.py first, or pass --working-tree to install the working tree")
    hidden = load_hidden()
    jobs = disc_jobs(card, games_from, hidden) if games_from else []
    need, biggest, new_files = estimate(card, cluster, worktree, jobs, hidden)
    margin = (256 << 20) + biggest + new_files * cluster      # + the macOS "._" files that exist until the end
    log(f"this run adds about {need / 2**30:.1f} GiB (+{margin / 2**30:.1f} GiB working room); {free / 2**30:.1f} GiB free")
    if need + margin > free:
        sys.exit(f"not enough space on {card}: needs about {(need + margin) / 2**30:.1f} GiB, has {free / 2**30:.1f}. "
                 "Nothing written. A 128 GB card (119 GiB usable) holds a full cabinet.")
    if check_only:
        sys.exit(log("card check passed (--check-only: nothing written)"))
    if games_from:                              # a new card (just formatted, empty): give it the apps folder; the
        os.makedirs(os.path.join(card, "apps"), exist_ok=True)   # check above made sure this is the card volume
    assert os.path.isdir(os.path.join(card, "apps")), f"{card} doesn't look like a Wii SD card"
    published = {r for r, _, _ in read_manifest()} if not worktree else set()
    if worktree:
        log("WARNING: --working-tree: published files come from the working tree, not dist/ (not what the fleet runs)")
        # 1. launcher/agent as the power-on program, 2. Nintendont
        log("launcher:", put(os.path.join(HERE, "agent/wii-agent.dol"), f"{card}/apps/wii-agent/boot.dol",
                              keep_old=f"{card}/apps/wii-agent/boot-prev.dol"))
        put(os.path.join(HERE, "hop/hop.dol"), f"{card}/apps/wii-agent/hop.dol")   # Priiloader's autoboot (NAND main.bin)
        log("nintendont:", put(NINTENDONT, f"{card}/apps/nintendont/boot.dol",
                                keep_old=f"{card}/apps/nintendont/boot-prev.dol"))
        for f in ("meta.xml", "icon.png", "boot.dol", "boot-r1272.dol"):   # r1283: the first that loads Wii games from SD
            put(os.path.join(KIT, "usbloader_gx", f), f"{card}/apps/usbloader_gx/{f}")
        log("usb loader gx: r1283")
    put(os.path.join(HERE, "agent/meta.xml"), f"{card}/apps/wii-agent/meta.xml")
    for f in ("META.XML", "boot.dol", "hacks_hash.ini", "icon.png"):   # Priiloader 0.9.1's installer (cab1's copy):
        dest = f"{card}/apps/priiloader/{f}"                           # recovery, and new Wiis that lack Priiloader
        if not os.path.exists(dest):
            data = subprocess.run(["ssh", "-o", "BatchMode=yes", NAS, f"cat {shlex.quote(f'{BACKUP}/apps/priiloader/{f}')}"],
                                  capture_output=True, check=True).stdout
            put(data, dest)
    # 3. RetroArch (salamander + the arcade cores only) and its config; what's published comes from dist/ below
    for name in ["boot.dol", "meta.xml", "icon.png"] + RA_CORES:
        if f"apps/retroarch-wii/{name}" in published:
            continue
        ours = os.path.join(KIT, "retroarch-swiirl", name)      # our builds (network commands), once tested
        tested = os.path.exists(os.path.join(KIT, "retroarch-swiirl", "TESTED"))
        src = ours if tested and os.path.exists(ours) else os.path.join(RA_SRC, name)
        if os.path.exists(src):
            put(src, f"{card}/apps/retroarch-wii/{name}")
    if worktree:
        put(RETROARCH_CFG.encode(), f"{card}/apps/retroarch-wii/retroarch.cfg")
        put(os.path.join(KIT, "retroarch-core-options.cfg"), f"{card}/retroarch/retroarch-core-options.cfg")
    for d in HISCORE_DESTS:                     # high-score lists: FB Alpha 2012 (2 places) and MAME 2000 (ROM folder)
        if d not in published:
            put(HISCORE_DAT, f"{card}/{d}")
    log("retroarch: salamander +", ", ".join(RA_CORES), "| hiscore.dat incl. roms/arcade (MAME 2000)")
    # 4. arcade sets (plan made by romcheck), BIOS in the ROM folder and RetroArch's system folder
    plan = json.load(open(os.path.join(KIT, "arcade_plan.json")))
    tsv = []
    for row in plan:
        system, nas_dir, z, title, year, maker = row[:6]
        if z[:-4] in hidden["rom"]:           # curated out (low rating / doesn't run): don't spend card space
            continue
        core = row[6] if len(row) > 6 else ("fbalpha2012_neogeo" if system == "neogeo" else "fbalpha2012_cps1")
        dest_name = "neogeo.zip" if z == "neogeo (1).zip" else z
        r = from_nas(f"{nas_dir}/{z}", f"{card}/roms/{system}/{dest_name}")
        if dest_name == "neogeo.zip":
            put(f"{card}/roms/neogeo/neogeo.zip", f"{card}/retroarch/system/neogeo.zip")
        if title:
            tsv.append(f"{system}\t{dest_name}\t{clean_title(title)}\t{year}\t{maker}\t{core}")
        log(f"  {system}/{dest_name}: {r}")
    if worktree:
        install_worktree_published(card, hidden, tsv)
        known = None
    else:
        known = install_published(card)
    cabs = os.path.join(KIT, "cabs")
    for f in sorted(os.listdir(f"{card}/arcade/cabs")) if os.path.isdir(f"{card}/arcade/cabs") else []:
        if f.endswith(".cfg") and not f.startswith("._") and not os.path.exists(os.path.join(cabs, f)):
            shutil.copyfile(f"{card}/arcade/cabs/{f}", os.path.join(cabs, f))   # a cabinet calibrated on this card
    lock_usbloader(card)
    # 6. Wii arcade picks -> wbfs/<Title [ID]>/<ID>.wbfs (none while hidden: cIOS question, 2026-10-16)
    for f in WII_ARCADE_PICKS:
        gid = re.search(r"\[(\w{6})\]", f).group(1)
        folder = f.rsplit(".", 1)[0]
        if gid in hidden["id"]:
            log(f"  - wii {folder}: hidden in sdkit/hidden.txt, not copied")
            continue
        log(f"  wii {folder}:", from_nas(f"{NAS_WII}/{f}", f"{card}/wbfs/{folder}/{gid}.wbfs"))
    # 8. existing Wii discs into USB Loader GX's folder
    if move_wii:
        src = f"{card}/games/Wii"
        for d in sorted(os.listdir(src)) if os.path.isdir(src) else []:
            if d.startswith(".") or not re.search(r"\[\w{6}\]", d):
                continue
            target = f"{card}/wbfs/{d}"
            if not os.path.exists(target):
                os.rename(f"{src}/{d}", target)
                log("  moved", d, "-> wbfs/")
    for gid in remove_wii:                   # e.g. games that need the sensor bar
        for d in os.listdir(f"{card}/wbfs"):
            if d.endswith(f"[{gid}]") and os.path.isdir(f"{card}/wbfs/{d}"):
                shutil.rmtree(f"{card}/wbfs/{d}")
                log("  removed", d)
    for d in ("apps/wii-agent", "arcade/video", "arcade/audio", "arcade/sfx", "arcade"):   # half-done Wi-Fi uploads
        for f in os.listdir(f"{card}/{d}") if os.path.isdir(f"{card}/{d}") else []:
            if f.endswith(".part"):
                os.remove(f"{card}/{d}/{f}")
                log("  removed unfinished upload", f"{d}/{f}")
    record_installed(card, known)
    if jobs:                                 # a new card: the whole game library
        copy_discs(jobs)
    remove_appledouble(card)
    log(card_free(card))


def install_worktree_published(card, hidden, tsv):
    """--working-tree: what publish.py would stage, straight from the working tree (the old installer)."""
    for line in open(os.path.join(KIT, "translations.tsv")):   # English-patched GameCube discs (CISO, staged on the Mac)
        p = line.rstrip("\n").split("\t")
        if len(p) >= 4 and not line.startswith("#") and os.path.exists(os.path.join(HERE, p[3])) and p[0] not in hidden["id"]:
            log(f"  gc {p[2]}:", stream_to(os.path.join(HERE, p[3]), f"{card}/games/{p[2]}/game.ciso", os.path.getsize(os.path.join(HERE, p[3]))))
    for system, f, title, year, maker, core in consoles():   # Genesis / SNES / NES picks, through our RetroArch cores
        if f.rsplit(".", 1)[0] in hidden["rom"]:
            continue
        put(os.path.join(CONSOLE_ROMS, system, f), f"{card}/roms/{system}/{f}")
        tsv.append(f"{system}\t{f}\t{title}\t{year}\t{maker}\t{core}")
    put(("\n".join(tsv) + "\n").encode(), f"{card}/arcade/arcade.tsv")
    log("arcade.tsv:", len(tsv), "games")
    put(os.path.join(KIT, "hidden.txt"), f"{card}/arcade/hidden.txt")
    for f in ("meta.tsv", "hiscores.tsv"):
        if os.path.exists(os.path.join(KIT, f)):
            put(os.path.join(KIT, f), f"{card}/arcade/{f}")
    if not os.path.exists(f"{card}/arcade/update.cfg"):   # pull updates from the update server (publish.py)
        put(UPDATE_CFG, f"{card}/arcade/update.cfg")
    # 5. fonts; every cabinet's settings (screen, idle power-off; picked by console id, so any card fits any
    #    cabinet); the collections; RetroArch bezels and per-game overrides
    for name, src in FONTS.items():
        put(src, f"{card}/arcade/fonts/{name}")
    for f in sorted(os.listdir(UI_ART)):
        if not f.startswith("."): put(os.path.join(UI_ART, f), f"{card}/arcade/ui/{f}")
    cabs = os.path.join(KIT, "cabs")
    for f in sorted(os.listdir(cabs)) if os.path.isdir(cabs) else []:
        dest = f"{card}/arcade/cabs/{f}"
        if not f.endswith(".cfg"):
            continue
        if os.path.exists(dest) and "screen =" in open(dest).read() and "screen =" not in open(os.path.join(cabs, f)).read():
            shutil.copyfile(dest, os.path.join(cabs, f))      # the card knows this TV better: keep it, learn it
            continue
        put(os.path.join(cabs, f), dest)
    if os.path.exists(os.path.join(KIT, "collections.tsv")):
        put(os.path.join(KIT, "collections.tsv"), f"{card}/arcade/collections.tsv")
    ra_tree = os.path.join(KIT, "retroarch")
    for dirpath, _, files in os.walk(ra_tree):
        for f in files:
            src = os.path.join(dirpath, f)
            put(src, f"{card}/retroarch/" + os.path.relpath(src, ra_tree))
    log("cabinets, collections, bezels: done")
    # 7. gameplay clips (arcade + GC/Wii discs), their attract-mode sound, card art (arcade flyers, disc covers)
    media = [(GVID, "arcade/video", None), (os.path.join(HERE, "videos/gvid_discs"), "arcade/video", None),
             (os.path.join(HERE, "videos/gaud"), "arcade/audio", None),
             (os.path.join(HERE, "videos/covers"), "arcade/art/covers", None),
             (os.path.join(HERE, "videos/art"), "arcade/art", "__"),       # art/<system>__<stem>.png
             (os.path.join(KIT, "sfx"), "arcade/sfx", None),               # menu sounds (videos/sfx.py)
             (os.path.join(HERE, "videos/stills"), "arcade/art/stills", None)]  # a frame of each clip (calm cards)
    for src, dest, split in media:
        n = 0
        for f in sorted(os.listdir(src)) if os.path.isdir(src) else []:
            if f.startswith(".") or f.endswith(".part"):
                continue
            target = f"{card}/{dest}/" + (f.replace(split, "/", 1) if split else f)
            n += put(os.path.join(src, f), target) == "written"
        log(f"{dest}: {n} written")


def card_free(card):
    st = os.statvfs(card)
    return f"done; {st.f_bavail * st.f_frsize / 2**30:.1f} GiB free on the card"


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    if "--wii-picks" in sys.argv or "--add-gc" in sys.argv:   # quick card swaps: only these discs, nothing else
        card = os.path.realpath(sys.argv[1])
        cluster, free = card_check(card, "--any-cluster-size" in sys.argv)
        jobs = []
        if "--wii-picks" in sys.argv:                 # explicit: copied even while hidden in hidden.txt
            for f in WII_ARCADE_PICKS:
                gid = re.search(r"\[(\w{6})\]", f).group(1)
                jobs.append(("wii", f.rsplit(".", 1)[0], f"{NAS_WII}/{f}", f"{card}/wbfs/{f.rsplit('.', 1)[0]}/{gid}.wbfs", False))
        if "--add-gc" in sys.argv:                    # a few GameCube discs (CISO) by id from cab1's card backup
            cands = gc_candidates()
            for gid in sys.argv[sys.argv.index("--add-gc") + 1].split(","):
                first, second = gc_pick(gid, None, cands[gid])
                title = DISC_NO.sub("", first.rsplit(".", 1)[0])
                jobs.append(("gc", title, gc_source(first), f"{card}/games/{title} [{gid}]/game.ciso", len(cands[gid]) > 1))
                if second:
                    jobs.append(("gc", f"{title} (disc 2)", gc_source(second), f"{card}/games/{title} [{gid}]/disc2.ciso", True))
        sizes = nas_sizes([s for k_, _, s, d, _ in jobs if k_ == "wii" and not os.path.exists(d)])
        need = sum(n for k_, _, s, d, _ in jobs if k_ == "wii" and not os.path.exists(d) for _, n in wbfs_parts(d, max(sizes[s], 0)))
        need += sum(ciso_size(s) for k_, _, s, d, v in jobs if k_ == "gc" and not (os.path.exists(d) and (not v or ciso_matches(d, s))))
        if need + (256 << 20) > free:
            sys.exit(f"not enough space on {card}: needs about {need / 2**30:.1f} GiB, has {free / 2**30:.1f}; nothing written")
        if "--check-only" in sys.argv:
            sys.exit(log(f"card check passed; this adds about {need / 2**30:.1f} GiB (--check-only: nothing written)"))
        copy_discs(jobs)
        sys.exit(log(card_free(card)))
    rm = sys.argv[sys.argv.index("--remove-wii") + 1].split(",") if "--remove-wii" in sys.argv else []
    games = sys.argv[sys.argv.index("--games") + 1] if "--games" in sys.argv else None
    main(sys.argv[1], "--move-wii-games" in sys.argv, [g for g in rm if g], games,
         worktree="--working-tree" in sys.argv, check_only="--check-only" in sys.argv,
         any_cluster="--any-cluster-size" in sys.argv)
