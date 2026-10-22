#!/usr/bin/env python3
"""Visual check on the Mac simulator (port of the Linux build box ~/wii-sim/vcheck/vrun.py): boot each game through the
launcher with Dolphin frame dumps (AVI of the raw XFB), run until MAXF frames after PLAY, then save one PNG every
STEP frames to sim/mac-run/vcheck/<rom>/f<tenths of s>.png plus retroarch.log and info.json (frames, wall time, speed).
    mac_vrun.py <nslots> rom [rom ...] [--first-slot N] [--dol launcher.dol] [--cores DIR] [--fast] [--out DIR]
env STEP (default 300 frames = 5 s), MAXF (3600 arcade), MAXF_CON (2400 consoles: rom not ending in .zip).
--fast: unthrottled; the dumps are per emulated frame, so the PNGs are the same, just sooner."""
import argparse, glob, json, os, shutil, subprocess, sys, threading, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import macsim as m

STEP = int(os.environ.get("STEP", 300)); MAXF = int(os.environ.get("MAXF", 3600))
MAXF_CON = int(os.environ.get("MAXF_CON", 2400))
lock = threading.Lock()


def sh(c): return subprocess.run(c, shell=True, capture_output=True, text=True)


def avis(fd): return sorted(glob.glob(f"{fd}/*.avi"), key=lambda p: (os.path.getctime(p), int(p.rsplit("_", 1)[1][:-4])))


def npk(p):
    r = sh(f"ffprobe -v error -count_packets -show_entries stream=nb_read_packets -of csv=p=0 '{p}'").stdout.strip()
    try: return int(r.splitlines()[0])
    except (ValueError, IndexError): return 0


def run(slot, rom, a):
    fd = os.path.join(m.user_dir(slot), "Dump/Frames"); od = os.path.join(a.out, rom)
    maxf = MAXF if rom.endswith(".zip") else MAXF_CON
    shutil.rmtree(od, ignore_errors=True); os.makedirs(od)
    m.prepare_card(slot)
    m.mt("mdel", "-i", m.card(slot), "::/retroarch/logs/retroarch.log")
    m.mt("mdel", "-i", m.card(slot), "::/arcade/last_launch.txt")   # a killed run must not look like a failed launch
    m.start(slot, a.dol, frames=True, fast=a.fast, cores=a.cores,
            extra=os.environ.get("SIMCONF", "").split())   # e.g. SIMCONF=SYSCONF.IPL.AR=1 (16:9, like cab1)
    t = time.time(); played = None
    m.wait_agent(slot, 240)
    while time.time() - t < 400:
        try:
            played = m.cmd(slot, f"PLAY {rom}")
            if played.startswith("OK"): break
        except OSError: pass
        time.sleep(2)
    info = {"play": played, "wall_boot": round(time.time() - t, 1)}
    if played is None or not played.startswith("OK"):
        m.stop(slot); info["verdict"] = "launcher-not-ready"; return info
    off = m.log_size(slot)
    base = {p: npk(p) for p in avis(fd)}
    t0, last, lastt = time.time(), 0, time.time()
    while True:
        time.sleep(5)
        tot = sum(npk(p) - base.get(p, 0) for p in avis(fd))
        if tot > last: last, lastt = tot, time.time()
        if tot >= maxf: info["stop"] = "done"; break
        if time.time() - lastt > 120: info["stop"] = "no-new-frames"; break
        if time.time() - t0 > 1200: info["stop"] = "wall-timeout"; break
    info["wall_game"] = round(time.time() - t0, 1)
    info["speed"] = m.perf_summary(m.perf(slot, off))
    m.stop(slot)
    g0, files = 0, []
    for p in avis(fd): files.append((p, base.get(p, 0), npk(p)))
    info["files"] = [(os.path.basename(p), b, n) for p, b, n in files]
    want = list(range(STEP, 100000, STEP))
    for p, b, n in files:
        sel = [(g, b + (g - g0)) for g in want if g0 <= g < g0 + (n - b)]
        if p == files[-1][0] and n - 1 > b: sel.append((g0 + n - 1 - b, n - 1))
        if sel:
            expr = "+".join(f"eq(n\\,{k})" for _, k in sel)
            sh(f"ffmpeg -v error -i '{p}' -vf \"select='{expr}'\" -fps_mode passthrough '{od}/tmp_%04d.png'")
            outs = sorted(glob.glob(f"{od}/tmp_*.png"))
            for (g, _), q in zip(sorted(set(sel), key=lambda x: x[1]), outs):
                os.rename(q, f"{od}/f{g // 6:05d}.png")
            for q in glob.glob(f"{od}/tmp_*.png"): os.remove(q)
        g0 += n - b
    info["frames"] = g0
    info["fps_wall"] = round(g0 / info["wall_game"], 1) if info["wall_game"] else None
    shutil.rmtree(fd, ignore_errors=True)
    open(f"{od}/retroarch.log", "w").write(m.ralog(slot))
    json.dump(info, open(f"{od}/info.json", "w"))
    return info


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("n", type=int); ap.add_argument("roms", nargs="+")
    ap.add_argument("--first-slot", type=int, default=1); ap.add_argument("--dol")
    ap.add_argument("--fast", action="store_true"); ap.add_argument("--cores", help="dir of <core>_libretro_wii.dol to install on the card"); ap.add_argument("--out", default=os.path.join(m.RUN, "vcheck"))
    a = ap.parse_args()
    todo = list(a.roms)

    def worker(slot):
        while True:
            with lock:
                if not todo: return
                rom = todo.pop(0)
            try: r = run(slot, rom, a)
            except Exception as e: r = {"error": repr(e)}; m.stop(slot)
            print(time.strftime("%H:%M:%S"), slot, rom, json.dumps({k: v for k, v in r.items() if k != "files"}), flush=True)
    th = [threading.Thread(target=worker, args=(s,)) for s in range(a.first_slot, a.first_slot + a.n)]
    for x in th: x.start()
    for x in th: x.join()
    print("ALL DONE", flush=True)


if __name__ == "__main__":
    main()
