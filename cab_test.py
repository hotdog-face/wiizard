#!/usr/bin/env python3
"""Boot test on a real cabinet, unattended: GameCube games through our Nintendont's test mode (PLAYTEST: it returns
to the launcher by itself after 40 s of play), arcade games through our RetroArch's network commands (PLAY, then
GET_STATUS / QUIT on UDP 55355). Needs launcher 0.9.7+, nintendont-swiirl, and for arcade retroarch-swiirl.
    cab_test.py gc|arcade [ip] [key ...]       -> cab_test_<kind>.json (resumable)
Verdicts: "booted" (came back after the timed exit / answered PLAYING), "failed" (back within FAIL_SECS: Nintendont
or RetroArch refused it), "hung" (never came back: needs a person; the run stops there)."""
import json, os, socket, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import wiiagent

FAIL_SECS = 55          # back sooner than this: it never ran (a Nintendont error screen waits 10 s, then returns)
HANG_SECS = 600          # Wi-Fi can take several launcher restarts to reconnect after a game

def info(ip):
    r = wiiagent.probe(ip, timeout=3)
    return dict(kv.split("=", 1) for kv in r.split()[1:] if "=" in kv) if r and r.startswith("OK") else None

def wait_menu(ip, timeout):
    t = time.time()
    while time.time() - t < timeout:
        i = info(ip)
        if i and i.get("mode") in ("attract", "browsing"):
            return i
        time.sleep(5)
    return None

def games(ip, system):
    with wiiagent.Agent(ip) as a:
        a.s.sendall(b"GAMES\n")
        rows = []
        while True:
            ln = a.line()
            if ln.startswith(("OK", "ERR")): break
            p = ln.split("\t")
            if len(p) >= 4 and p[1] == system: rows.append((p[2], p[3]))
    return rows

def udp(ip, text, wait=2):
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.settimeout(wait); s.sendto(text.encode(), (ip, 55355))
        try: return s.recvfrom(4096)[0].decode(errors="replace").strip()
        except socket.timeout: return None

def reclassify(ip, key, res, out):
    """The launcher logs "back from <key> after <n>s" (launch to return, by the Wii's clock). A game that came back
    by itself after its timed exit took ~60-150 s, and only Wi-Fi was slow; one that needed a power cycle took longer."""
    import re
    try:
        with wiiagent.Agent(ip, timeout=60) as a:     # the card's log too: Wi-Fi restarts clear the one in RAM
            log = a.get("sd:/apps/wii-agent/agent.log").decode(errors="replace") + "\n" + a.log()
    except OSError:
        return
    try:                                             # launcher 0.9.10+: every return recorded on the card
        with wiiagent.Agent(ip, timeout=60) as a:
            rets = a.get("sd:/arcade/returns.tsv").decode(errors="replace")
        log += "".join(f"back from {l.split(chr(9))[0]} after {l.split(chr(9))[1]}s\n" for l in rets.splitlines() if l.count(chr(9)) >= 2)
    except OSError:
        pass
    m = re.findall(rf"back from {re.escape(key)}\S* after (\d+)s", log)
    if m:
        n = int(m[-1])
        res[key]["note"] = f"returned after {n}s by the Wii's clock"
        res[key]["verdict"] = "booted" if n < 200 else "hung"
        json.dump(res, open(out, "w"), indent=1)
        print(time.strftime("%H:%M:%S"), key, "->", res[key]["verdict"], res[key]["note"], flush=True)

def main():
    kind = sys.argv[1]
    ip = sys.argv[2] if len(sys.argv) > 2 and sys.argv[2].count(".") == 3 else sys.exit("usage: give the cabinet's IP")
    only = [a for a in sys.argv[2:] if a.count(".") != 3]
    out = os.path.join(HERE, f"cab_test_{kind}.json")
    res = json.load(open(out)) if os.path.exists(out) else {}
    while not wait_menu(ip, 3600): pass                     # wait as long as it takes for the cabinet
    for k, v in list(res.items()):                          # a game left "hung" by an earlier run: ask the log
        if v.get("verdict") == "hung": reclassify(ip, k, res, out)
    todo = games(ip, "NINTENDO GAMECUBE" if kind == "gc" else None) if kind == "gc" else None
    if kind == "arcade":
        with wiiagent.Agent(ip) as a:
            a.s.sendall(b"GAMES\n"); todo = []
            while True:
                ln = a.line()
                if ln.startswith(("OK", "ERR")): break
                p = ln.split("\t")
                if len(p) >= 4 and p[1] not in ("NINTENDO GAMECUBE", "NINTENDO WII"): todo.append((p[2], p[3]))
    todo = [(k, t) for k, t in todo if (not only or k in only) and k not in res]
    print(len(todo), "to test", flush=True)
    for key, title in todo:
        if not wait_menu(ip, 600): print("cabinet gone"); break
        try:
            with wiiagent.Agent(ip) as a:
                r = a.cmd(f"{'PLAYTEST' if kind == 'gc' else 'PLAY'} {key}")
        except OSError as exc:                       # e.g. no longer in the library (hidden meanwhile)
            r = f"ERR {exc}"
        if not r.startswith("OK"):
            res[key] = {"title": title, "verdict": "not-started", "secs": 0, "note": r}
            json.dump(res, open(out, "w"), indent=1)
            continue
        t0 = time.time()
        for _ in range(30):                          # the launcher leaves for the game: its agent goes away
            if not info(ip): break
            time.sleep(1)
        verdict, note = None, ""
        if kind == "arcade":
            for _ in range(40):                       # RetroArch's command port comes up a few seconds in
                time.sleep(3)
                st = udp(ip, "GET_STATUS")
                if st:
                    note = st
                    verdict = "booted" if "PLAYING" in st else "failed"
                    time.sleep(10)
                    udp(ip, "QUIT", 0.3)
                    break
                if info(ip):                          # already back in the launcher: it never ran
                    verdict = "failed"; break
        time.sleep(15)                               # never mistake the launcher's last breath for a return
        back = wait_menu(ip, HANG_SECS)
        dt = time.time() - t0
        if not back: verdict = "hung"
        elif verdict is None: verdict = "failed" if dt < FAIL_SECS else "booted"
        res[key] = {"title": title, "verdict": verdict, "secs": round(dt), "note": note}
        json.dump(res, open(out, "w"), indent=1)
        print(time.strftime("%H:%M:%S"), key, title, verdict, round(dt), note, flush=True)
        if verdict == "hung":                       # stuck in the game, or only Wi-Fi: wait for it, then ask the log
            print(time.strftime("%H:%M:%S"), "waiting for the cabinet to come back (power cycle)", flush=True)
            while not wait_menu(ip, 3600): pass
            reclassify(ip, key, res, out)
    print("CAB TEST DONE", flush=True)

if __name__ == "__main__":
    main()
