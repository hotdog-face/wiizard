#!/usr/bin/env python3
"""One-at-a-time job queue for cab1 over Wi-Fi (the agent serves one connection at a time, so parallel jobs starve
each other). Every step reconnects and retries; finished steps are recorded in queue_state.json and skipped on a
rerun.  queue_run.py [step ...]"""
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import wiiagent  # noqa: E402
import wii_mcp as m  # noqa: E402

IP = os.environ.get("WII_CAB_IP", "")   # the cabinet the queue runs on
STATE = os.path.join(HERE, "queue_state.json")


def say(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


def agent():
    for _ in range(90):
        try:
            return wiiagent.Agent(IP, timeout=60)
        except OSError:
            time.sleep(10)
    raise OSError("agent unreachable for 15 minutes")


def with_retry(fn, tries=4):
    for i in range(tries):
        try:
            return fn()
        except OSError as exc:
            if i == tries - 1:
                raise
            say("  retrying after:", exc)
            time.sleep(15)


def rm(path):
    """Delete a file or a whole folder (recursively). Missing paths are fine."""
    def go():
        with agent() as a:
            stack, dirs = [path], []
            try:
                a.cmd(f"STAT {path}")
            except OSError:
                return 0
            n = 0
            while stack:
                p = stack.pop()
                try:
                    entries = a.ls(p)
                except OSError:              # a file
                    a.cmd(f"RM {p}")
                    n += 1
                    continue
                dirs.append(p)
                for name, size in entries:
                    if size is None:
                        stack.append(f"{p}/{name}")
                    else:
                        a.cmd(f"RM {p}/{name}")
                        n += 1
            for d in reversed(dirs):
                a.cmd(f"RM {d}")
            return n
    return with_retry(go)


def remote_size(path):
    with agent() as a:
        try:
            return int(a.cmd(f"STAT {path}").split()[1])
        except OSError:
            return -1


def step_launcher():
    m.upload(IP, "sd:/arcade/fonts/ui.ttf", open("/System/Library/Fonts/Supplemental/Arial Rounded Bold.ttf", "rb").read())
    say(m.tool_start_agent("cab1"))


def step_delete_hidden():
    plan = json.load(open(os.path.join(HERE, "sdkit/delete_plan.json")))
    for kind, path in plan:
        n = rm(path)
        if n:
            say("  deleted", path)


def step_cleanup():
    for path in ["sd:/apps/wiiflow", "sd:/apps/homebrew_browser", "sd:/rvloader", "sd:/apps/arcade-test",
                 "sd:/README.txt", "sd:/README-BootMii.txt", "sd:/README-HBC.txt", "sd:/LICENSE.txt", "sd:/CREDITS.txt",
                 "sd:/APACHE-2.0.txt", "sd:/installer.log", "sd:/chan_install.log", "sd:/boot.dol",
                 "sd:/.Spotlight-V100", "sd:/.Trashes", "sd:/.TemporaryItems"]:
        say("  cleanup", path, rm(path), "files")
    with agent() as a:                       # WiiFlow's data, except the box art the launcher uses
        entries = a.ls("sd:/wiiflow")
    for name, size in entries:
        if name not in ("boxcovers", "covers"):
            say("  cleanup wiiflow/" + name, rm(f"sd:/wiiflow/{name}"), "files")
    # macOS "._" metadata files in the folders we use
    for top in ["sd:/", "sd:/apps", "sd:/games", "sd:/wbfs", "sd:/roms/arcade", "sd:/roms/cps1", "sd:/roms/cps2",
                "sd:/roms/neogeo", "sd:/arcade/video", "sd:/wiiflow/boxcovers"]:
        def sweep():
            with agent() as a:
                try:
                    names = [n for n, s in a.ls(top) if n.startswith("._")]
                except OSError:
                    return 0
                gone = 0
                for n in names:              # some "._" names are listed but can't be removed: skip those
                    try:
                        a.cmd(f"RM {top.rstrip('/')}/{n}")
                        gone += 1
                    except OSError as exc:
                        if "No such file" not in str(exc):
                            raise
                return gone
        say("  ._ files in", top, with_retry(sweep))


def step_disc_clips():
    src = os.path.join(HERE, "videos/gvid_discs")
    for f in sorted(os.listdir(src)):
        if not f.endswith(".gvid"):
            continue
        data = open(os.path.join(src, f), "rb").read()
        if remote_size(f"sd:/arcade/video/{f}") == len(data):
            continue
        with_retry(lambda: m.upload(IP, f"sd:/arcade/video/{f}", data))
        say("  clip", f)


def step_thumbs():
    """Arcade card art: flyers from ScreenScraper (gameplay screenshot where there's no flyer)."""
    src = os.path.join(HERE, "videos/art")
    for f in sorted(os.listdir(src)):
        system, stem = f[:-4].split("__", 1)
        data = open(os.path.join(src, f), "rb").read()
        dest = f"sd:/arcade/art/{system}/{stem}.png"
        if remote_size(dest) == len(data):
            continue
        with_retry(lambda: m.upload(IP, dest, data))
    say("  thumbnails done")


def step_arcade_clips():
    src = os.path.join(HERE, "videos/gvid")
    for f in sorted(os.listdir(src)):
        if not f.endswith(".gvid"):
            continue
        data = open(os.path.join(src, f), "rb").read()
        if remote_size(f"sd:/arcade/video/{f}") == len(data):
            continue
        with_retry(lambda: m.upload(IP, f"sd:/arcade/video/{f}", data))
        say("  clip", f)


def step_restart():
    with agent() as a:
        a.cmd("EXEC sd:/apps/wii-agent/boot.dol")
    time.sleep(15)
    with agent() as a:
        say(a.cmd("INFO"))


def step_ra_config():
    import sdkit_install as k
    m.upload(IP, "sd:/apps/retroarch-wii/retroarch.cfg", k.RETROARCH_CFG.encode())
    m.upload(IP, "sd:/retroarch/retroarch-core-options.cfg", open(os.path.join(HERE, "sdkit/retroarch-core-options.cfg"), "rb").read())
    hs = open(os.path.join(HERE, "downloads/hiscore/hiscore.dat"), "rb").read()
    for d in ("savefiles", "system"):
        m.upload(IP, f"sd:/retroarch/{d}/hiscore.dat", hs)
    m.upload(IP, "sd:/arcade/meta.tsv", open(os.path.join(HERE, "sdkit/meta.tsv"), "rb").read())
    say("  retroarch 240p/high scores/free play + meta.tsv")


def step_audio():
    src = os.path.join(HERE, "videos/gaud")
    for f in sorted(os.listdir(src)):
        if not f.endswith(".gaud"):
            continue
        data = open(os.path.join(src, f), "rb").read()
        if remote_size(f"sd:/arcade/audio/{f}") == len(data):
            continue
        with_retry(lambda: m.upload(IP, f"sd:/arcade/audio/{f}", data))
    say("  audio done")


def step_covers():
    src = os.path.join(HERE, "videos/covers")
    for f in sorted(os.listdir(src)):
        data = open(os.path.join(src, f), "rb").read()
        if remote_size(f"sd:/arcade/art/covers/{f}") == len(data):
            continue
        with_retry(lambda: m.upload(IP, f"sd:/arcade/art/covers/{f}", data))
    say("  covers done")


def step_hidden():
    m.upload(IP, "sd:/arcade/hidden.txt", open(os.path.join(HERE, "sdkit/hidden.txt"), "rb").read())
    import sdkit_install as k, json as _j
    say("  hidden.txt updated")


def step_launcher7():
    say(m.tool_start_agent("cab1"))


def step_v080():
    """0.8.0 extras: cabinets, collections, bezels + per-game overrides, RetroArch config, USB Loader GX lock."""
    import re
    import sdkit_install as k
    kit = os.path.join(HERE, "sdkit")
    for f in sorted(os.listdir(os.path.join(kit, "cabs"))):
        with_retry(lambda: m.upload(IP, f"sd:/arcade/cabs/{f}", open(os.path.join(kit, "cabs", f), "rb").read()))
    with_retry(lambda: m.upload(IP, "sd:/arcade/collections.tsv", open(os.path.join(kit, "collections.tsv"), "rb").read()))
    tree = os.path.join(kit, "retroarch")
    for dirpath, _, files in os.walk(tree):
        for f in files:
            src = os.path.join(dirpath, f)
            data = open(src, "rb").read()
            dest = "sd:/retroarch/" + os.path.relpath(src, tree)
            if remote_size(dest) != len(data):
                with_retry(lambda: m.upload(IP, dest, data))
    with_retry(lambda: m.upload(IP, "sd:/apps/retroarch-wii/retroarch.cfg", k.RETROARCH_CFG.encode()))
    with agent() as a:
        try:
            cfg = a.get("sd:/apps/usbloader_gx/GXGlobal.cfg").decode(errors="replace")
        except OSError:
            cfg = None
    if cfg:
        for key, val in (("godmode", "0"), ("password", k.USBLGX_PASSWORD), ("RememberUnlock", "0")):
            cfg = re.sub(rf"^{key} = .*$", f"{key} = {val}", cfg, flags=re.M)
        with_retry(lambda: m.upload(IP, "sd:/apps/usbloader_gx/GXGlobal.cfg", cfg.encode()))
    say("  cabinets, collections, bezels, retroarch.cfg, usb loader lock")


STEPS = {"launcher": step_launcher, "delete_hidden": step_delete_hidden, "cleanup": step_cleanup,
         "disc_clips": step_disc_clips, "arcade_clips": step_arcade_clips, "thumbs": step_thumbs, "restart": step_restart,
         "ra_config": step_ra_config, "launcher7": step_launcher7, "audio": step_audio,
         "covers": step_covers, "hidden": step_hidden, "v080": step_v080}

if __name__ == "__main__":
    state = json.load(open(STATE)) if os.path.exists(STATE) else {}
    for name in sys.argv[1:] or list(STEPS):
        if state.get(name) == "done" and name != "restart":
            continue
        say("==", name)
        STEPS[name]()
        state[name] = "done"
        json.dump(state, open(STATE, "w"))
    say("QUEUE DONE")
