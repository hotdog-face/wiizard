#!/usr/bin/env python3
"""Boot test on the Mac simulator (port of the Linux build box ~/wii-sim/atest3.py): for each game, start a simulated Wii from
its slot's card, PLAY (or PLAYTEST) it through the launcher, let it run, stop, and read RetroArch's own log from the
card with mtools. Records the emulation speed while the game ran. Results: sim/mac-run/atest_results.json
{rom: {"verdict", "speed": {...}, "status", "log": [...]}}.
    mac_atest.py <slots> <run secs> [rom ...] [--first-slot N] [--dol launcher.dol] [--cores DIR] [--playtest] [--fast] [--fresh]
                 [--results file.json]
--playtest: PLAYTEST (RetroArch quits by itself after 60 Wii seconds) and wait for the launcher to come back
(verdict gets "+returned" and "return_secs"); otherwise the game is stopped after <run secs>.
Games given as rom file names (dkong.zip, snsmw.sfc) or launcher ids; no roms = every game the launcher lists."""
import argparse, json, os, sys, threading, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import macsim as m

lock = threading.Lock()


def verdict(log):
    text = "\n".join(log)
    if any(w in text for w in ("Failed to load content", "Failed to load", "could not", "Out of memory", "out of memory")):
        return "FAILED"
    if "[Content]" in text or "Loading content" in text or "content file" in text:
        return "loaded" if ("Version of libretro API" in text or "Set geometry" in text or "Audio" in text) else "loading"
    return "no-log" if not log else "unclear"


def run(slot, rom, secs, a):
    m.prepare_card(slot, a.fresh)
    m.mt("mdel", "-i", m.card(slot), "::/retroarch/logs/retroarch.log")
    m.mt("mdel", "-i", m.card(slot), "::/arcade/last_launch.txt")   # a killed run must not look like a failed launch
    m.start(slot, a.dol, frames=False, fast=a.fast, cores=a.cores)
    t0 = time.time()
    if not m.wait_agent(slot, 240):
        m.stop(slot); return {"verdict": "launcher-not-ready"}
    played = None
    while time.time() - t0 < 400:            # the list loads behind the start-up sign: retry until it's there
        try:
            played = m.cmd(slot, f"{'PLAYTEST' if a.playtest else 'PLAY'} {rom}")
            if played.startswith("OK"): break
            if "no such game" in played and time.time() - t0 > 120: break   # the list may still be loading
        except OSError:
            pass
        time.sleep(2)
    res = {"play": played, "wall_boot": round(time.time() - t0, 1)}
    if not played or not played.startswith("OK"):
        m.stop(slot); res["verdict"] = "launcher-not-ready" if not played else "no-such-game"; return res
    off, tp = m.log_size(slot), time.time()
    st, returned = None, None
    while time.time() - tp < secs:
        time.sleep(2)
        if not m.alive(slot): break
        s = m.ra_status(slot)
        if s: st = s
        if a.playtest and time.time() - tp > 20:
            try:
                if m.cmd(slot, "INFO", 2).startswith("OK"): returned = round(time.time() - tp, 1); break
            except OSError:
                pass
    alive = m.alive(slot)
    res["speed"] = m.perf_summary(m.perf(slot, off))
    res["status"] = st
    m.stop(slot)
    log = m.ralog(slot).splitlines()
    v = verdict(log)
    if not alive and v != "FAILED": v = "emulator-stopped:" + v
    if a.playtest: v += "+returned" if returned else "+no-return"; res["return_secs"] = returned
    res["verdict"] = v; res["log"] = log[-25:]
    return res


def all_games(slot, a):
    m.start(slot, a.dol); m.wait_agent(slot)
    import socket
    out = []
    with socket.create_connection(("127.0.0.1", m.agent_port(slot)), timeout=10) as s:
        s.sendall(b"GAMES\n"); f = s.makefile("rb")
        while True:
            ln = f.readline().decode(errors="replace").rstrip("\n")
            if not ln or ln.startswith("OK") or ln.startswith("ERR"): break
            out.append(ln.split("\t")[2])
    m.stop(slot)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("slots", type=int); ap.add_argument("secs", type=int); ap.add_argument("roms", nargs="*")
    ap.add_argument("--first-slot", type=int, default=1); ap.add_argument("--dol")
    ap.add_argument("--playtest", action="store_true"); ap.add_argument("--fast", action="store_true"); ap.add_argument("--cores", help="dir of <core>_libretro_wii.dol to install on the card")
    ap.add_argument("--fresh", action="store_true")
    ap.add_argument("--results", default=os.path.join(m.RUN, "atest_results.json"))
    a = ap.parse_args()
    if a.playtest and a.secs < 120: a.secs = 120          # 60 s autotest + boot + return
    todo = a.roms or all_games(a.first_slot, a)
    res = json.load(open(a.results)) if os.path.exists(a.results) else {}
    if not a.roms: todo = [g for g in todo if g not in res]

    def worker(slot):
        while True:
            with lock:
                if not todo: return
                rom = todo.pop(0)
            t = time.time()
            try: r = run(slot, rom, a.secs, a)
            except Exception as e: r = {"verdict": "error", "error": repr(e)}; m.stop(slot)
            r["wall_total"] = round(time.time() - t, 1)
            with lock:
                res[rom] = r
                json.dump(res, open(a.results, "w"), indent=1)
            print(time.strftime("%H:%M:%S"), slot, rom, r["verdict"], json.dumps(r.get("speed", {})), flush=True)
    th = [threading.Thread(target=worker, args=(s,)) for s in range(a.first_slot, a.first_slot + a.slots)]
    for t in th: t.start()
    for t in th: t.join()
    print("ALL DONE", flush=True)


if __name__ == "__main__":
    main()
