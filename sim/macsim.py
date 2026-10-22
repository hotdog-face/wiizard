#!/usr/bin/env python3
"""The Wii simulator on this Mac: Dolphin 2609a NoGUI (built from source, native arm64, Metal, headless, no window,
no sound) running the launcher DOL with a raw FAT32 card image as its SD card. Several slots can run side by side.

Slot N uses:  card  sim/mac-cards/slotN.raw   (an APFS clone of mac-cards/master.raw, made on first use: no extra disk)
              user  sim/mac-run/userN         (copy of the sim/mac-user template: NAND, SYSCONF, GFX.ini, ...)
              ports agent TCP 4300+10N, RetroArch UDP 55355+10N on 127.0.0.1 only (--lan: also this Mac's LAN IP;
                    off by default so the wii MCP's LAN scan / fleet.py never mistake the simulator for a cabinet)
              log   sim/mac-run/slotN.log     (Dolphin's stdout, with a "perf speed=..% max=..%" line every 5 s)
Slot 0 answers on the normal port 4300, so wiiagent.py / the wii MCP tools work against 127.0.0.1.

    macsim.py start [-s N] [--dol launcher.dol] [--fresh] [--frames] [--audio] [--fast] [--lan] [-C Sys.Sec.Key=Val]
    macsim.py stop  [-s N | --all]
    macsim.py shot  out.png [-s N]            the launcher's SHOT (its own framebuffer; never the Mac's screen)
    macsim.py cmd   "PLAY dkong.zip" [-s N]   one raw agent command
    macsim.py perf  [-s N]                    recent emulation speed (100% = a real Wii)
    macsim.py ralog [-s N]                    RetroArch's log from the slot's card (mtools)
    macsim.py press START [-s N]              a GameCube pad press through Dolphin's pipe (works in games too;
                                              A B X Y Z START L R D_UP D_DOWN D_LEFT D_RIGHT)
    macsim.py status

The launcher DOL is also installed as the card's sd:/apps/wii-agent/boot.dol (what our RetroArch starts on quit;
--no-install to keep the card's); --cores DIR installs DIR/*_libretro_wii.dol into sd:/apps/retroarch-wii/.
--fresh re-clones the card from master.raw. --fast runs unthrottled (as fast as the Mac can; emulated time, so game
timers and RetroArch's autotest still count Wii seconds). --frames / --audio dump to mac-run/userN/Dump/{Frames,Audio}.
"""
import argparse, os, re, shutil, signal, socket, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
WII = os.path.dirname(HERE)
BIN = os.path.join(HERE, "DolphinNoGUI.app/Contents/MacOS/dolphin-emu-nogui")
TEMPLATE = os.path.join(HERE, "mac-user")
CARDS = os.path.join(HERE, "mac-cards")
RUN = os.path.join(HERE, "mac-run")
MASTER = os.path.join(CARDS, "master.raw")
DEFAULT_DOL = os.path.join(WII, "agent/wii-agent.dol")
os.makedirs(RUN, exist_ok=True)


def agent_port(slot): return 4300 + 10 * slot
def ra_port(slot): return 55355 + 10 * slot
def user_dir(slot): return os.path.join(RUN, f"user{slot}")
def card(slot): return os.path.join(CARDS, f"slot{slot}.raw")
def log_path(slot): return os.path.join(RUN, f"slot{slot}.log")
def pid_path(slot): return os.path.join(RUN, f"slot{slot}.pid")


def pad_dol(src, dst):
    """Dolphin 2609a (2512 did not) rejects a DOL whose last section runs to the end of the file with a size that isn't a multiple of
    32 ("Could not boot the specified file" / Qt: "Failed to init core"). Our launcher DOL is like that: pad it."""
    b = open(src, "rb").read()
    open(dst, "wb").write(b + b"\0" * (-len(b) % 32))
    return dst


def mt(*args, check=False):
    """mtools on a card image: mt('mtype', '-i', img, '::/path')."""
    return subprocess.run(list(args), capture_output=True, text=True, check=check,
                          env=dict(os.environ, MTOOLS_SKIP_CHECK="1"))


def prepare_card(slot, fresh=False, src=None):
    c = card(slot)
    if fresh or not os.path.exists(c):
        if os.path.exists(c): os.remove(c)
        subprocess.run(["cp", "-c", src or MASTER, c], check=True)   # APFS clone: instant, shares blocks
    return c


def prepare_user(slot):
    u = user_dir(slot)
    if not os.path.exists(u):
        shutil.copytree(TEMPLATE, u, symlinks=True, ignore=shutil.ignore_patterns("Dump", "Logs", "Cache"))
    os.makedirs(os.path.join(u, "Pipes"), exist_ok=True)
    fifo = os.path.join(u, "Pipes/pad")
    if not os.path.exists(fifo): os.mkfifo(fifo)
    return u


def pid_of(slot):
    try:
        pid = int(open(pid_path(slot)).read())
        os.kill(pid, 0)
        return pid
    except (OSError, ValueError):
        return None


def alive(slot): return pid_of(slot) is not None


def stop(slot, timeout=20):
    pid = pid_of(slot)
    if pid:
        os.kill(pid, signal.SIGTERM)                 # Dolphin stops cleanly on the first signal
        t = time.time()
        while time.time() - t < timeout:
            try: os.kill(pid, 0)
            except OSError: break
            time.sleep(0.25)
        else:
            os.kill(pid, signal.SIGKILL); time.sleep(0.5)
    try: os.remove(pid_path(slot))
    except OSError: pass


def start(slot=0, dol=None, fresh=False, frames=False, audio=False, fast=False, extra=(), card_src=None, perf_secs=5,
          lan=False, install=True, cores=None):
    stop(slot)
    if os.nice(0) > 0:
        print(f"macsim: warning: running at nice {os.nice(0)} (a zsh '&' job?); Dolphin will be slower. "
              "Use 'setopt NO_BG_NICE' or run in the foreground.", file=sys.stderr)
    u = prepare_user(slot)
    c = prepare_card(slot, fresh, card_src)
    d = pad_dol(dol or DEFAULT_DOL, os.path.join(RUN, f"slot{slot}.dol"))
    if install:      # our RetroArch starts sd:/apps/wii-agent/boot.dol on quit: make that the launcher under test
        mt("mcopy", "-o", "-i", c, d, "::/apps/wii-agent/boot.dol")
    for f in sorted(os.listdir(cores)) if cores else []:     # RetroArch core DOLs to test (<core>_libretro_wii.dol)
        if f.endswith("_libretro_wii.dol"):
            mt("mcopy", "-o", "-i", c, os.path.join(cores, f), f"::/apps/retroarch-wii/{f}")
    for sub in ("Frames", "Audio"):
        shutil.rmtree(os.path.join(u, "Dump", sub), ignore_errors=True)
        os.makedirs(os.path.join(u, "Dump", sub), exist_ok=True)
    conf = ["Dolphin.Core.WiiSDCardEnableFolderSync=False", f"Dolphin.General.WiiSDCardPath={c}",
            "SYSCONF.IPL.AR=False", "Dolphin.DSP.Backend=No Audio Output"]
    if frames: conf += ["Dolphin.Movie.DumpFrames=True", "Dolphin.Movie.DumpFramesSilent=True"]
    if audio: conf += ["Dolphin.DSP.DumpAudio=True", "Dolphin.DSP.DumpAudioSilent=True"]
    if fast: conf += ["Dolphin.Core.EmulationSpeed=0"]
    conf += list(extra)
    argv = [BIN, "-p", "headless", "-u", u, "-v", "Metal"]
    for x in conf: argv += ["-C", x]
    argv += ["-e", d]
    env = dict(os.environ, DOLPHIN_PORT_OFFSET=str(10 * slot), DOLPHIN_PERF_LOG=str(perf_secs),
               DOLPHIN_BIND_ADDR="" if lan else "127.0.0.1")   # (both are our patches to Dolphin's IOS sockets)
    # own session, normal priority (a zsh "&" job would get nice +5), stdout = the slot log
    p = subprocess.Popen(argv, stdout=open(log_path(slot), "w"), stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                         start_new_session=True, env=env, cwd=RUN)
    open(pid_path(slot), "w").write(str(p.pid))
    return p.pid


def cmd(slot, line, timeout=5):
    with socket.create_connection(("127.0.0.1", agent_port(slot)), timeout=timeout) as s:
        s.sendall(line.encode() + b"\n")
        return s.makefile("rb").readline().decode(errors="replace").strip()


def wait_agent(slot, timeout=180):
    t = time.time()
    while time.time() - t < timeout:
        if not alive(slot): return None
        try:
            r = cmd(slot, "INFO", 3)
            if r.startswith("OK"): return r
        except OSError:
            pass
        time.sleep(1)
    return None


def ra_status(slot):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s.settimeout(2)
    try:
        s.sendto(b"GET_STATUS", ("127.0.0.1", ra_port(slot))); return s.recv(512).decode(errors="replace").strip()
    except OSError:
        return None
    finally:
        s.close()


def shot(slot, out):
    sys.path.insert(0, WII)
    import wiiagent
    wiiagent.PORT = agent_port(slot)
    with wiiagent.Agent("127.0.0.1", timeout=60) as a:
        a.screenshot().save(out)
    return out


PERF = re.compile(rb"perf speed=(\d+)% max=(\d+)%")


def log_size(slot):
    try: return os.path.getsize(log_path(slot))
    except OSError: return 0


def perf(slot, since=0):
    """[(speed%, max%)] from the slot log after byte offset `since`."""
    try: data = open(log_path(slot), "rb").read()[since:]
    except OSError: return []
    return [(int(a), int(b)) for a, b in PERF.findall(data)]


def perf_summary(samples):
    if not samples: return {}
    sp = sorted(s for s, _ in samples); mx = sorted(m for _, m in samples)
    return {"n": len(samples), "speed_avg": round(sum(sp) / len(sp)), "speed_min": sp[0],
            "speed_median": sp[len(sp) // 2], "max_median": mx[len(mx) // 2]}


def ralog(slot, img=None):
    return mt("mtype", "-i", img or card(slot), "::/retroarch/logs/retroarch.log").stdout


def press(slot, button, hold=0.3):
    """Press a button on the emulated GameCube pad 1 (Dolphin Pipes input: mac-run/userN/Pipes/pad)."""
    fd = os.open(os.path.join(user_dir(slot), "Pipes/pad"), os.O_WRONLY | os.O_NONBLOCK)
    try:
        os.write(fd, f"PRESS {button}\n".encode()); time.sleep(hold); os.write(fd, f"RELEASE {button}\n".encode())
    finally:
        os.close(fd)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("action", choices=["start", "stop", "shot", "cmd", "perf", "ralog", "status", "press"])
    ap.add_argument("arg", nargs="?")
    ap.add_argument("-s", "--slot", type=int, default=0)
    ap.add_argument("--dol"); ap.add_argument("--fresh", action="store_true")
    ap.add_argument("--frames", action="store_true"); ap.add_argument("--audio", action="store_true")
    ap.add_argument("--fast", action="store_true"); ap.add_argument("--all", action="store_true")
    ap.add_argument("--lan", action="store_true"); ap.add_argument("--cores")
    ap.add_argument("--no-install", action="store_true")
    ap.add_argument("-C", dest="conf", action="append", default=[])
    a = ap.parse_args()
    s = a.slot
    if a.action == "start":
        pid = start(s, a.dol or a.arg, a.fresh, a.frames, a.audio, a.fast, a.conf, lan=a.lan, install=not a.no_install,
                    cores=a.cores)
        r = wait_agent(s)
        if r: print(f"simulator slot {s} up (pid {pid}, 127.0.0.1:{agent_port(s)}): {r}")
        else: print(f"slot {s}: agent did not answer; see {log_path(s)}"); sys.exit(1)
    elif a.action == "stop":
        for n in (range(100) if a.all else [s]):
            if os.path.exists(pid_path(n)): stop(n)
    elif a.action == "shot":
        print(shot(s, a.arg or os.path.join(RUN, f"shot{s}.png")))
    elif a.action == "cmd":
        print(cmd(s, a.arg))
    elif a.action == "perf":
        p = perf(s)
        print(" ".join(f"{x}%/{y}%" for x, y in p[-12:]), "(speed/max, every 5 s)")
    elif a.action == "press":
        press(s, a.arg)
    elif a.action == "ralog":
        print(ralog(s), end="")
    elif a.action == "status":
        for f in sorted(os.listdir(RUN)):
            m = re.match(r"slot(\d+)\.pid$", f)
            if m:
                n = int(m.group(1)); p = perf(n)
                print(f"slot {n}: {'running' if alive(n) else 'dead'} port {agent_port(n)} last perf {p[-1] if p else '-'}")


if __name__ == "__main__":
    main()
