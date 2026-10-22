#!/usr/bin/env python3
"""Boot-test games on a real cabinet with its own test queue (TESTQUEUE), from the Mac, and watch it.

    cab_queue.py <cab ip> <keys file> <results.json>     keys: one game id / zip per line (from GAMES)

The cabinet runs each game in test mode (arcade/console: our RetroArch quits after 60 s; GameCube: Nintendont exits
after 40 s of play), 20 s apart in attract mode, and appends "<key>\\t<seconds away>\\t<attempt>" to
sd:/arcade/returns.tsv on every return. TESTQUEUE takes one 600-byte line, so keys go in batches: the next batch
when the cabinet's queue file is gone. Every 20 s: INFO (is it back? on which address?), new returns.tsv lines.
Results (per key: seconds, attempt, verdict) and network gaps (how long it was away, and whether it came back on the
cable) go to results.json; one line per event on stdout. Resumable: keys already in results.json are skipped.
Any button on the cabinet stops its queue (a person is playing): the runner then waits and resumes when it's idle.
Hang watchdog: if the cabinet stays unreachable for HANG_SECS (6 min; a test game is away ~55-100 s), the game it was
running (the oldest unreturned key) is recorded as "hang/power-off" and the runner exits with status 3, so the
supervisor stops and a person can look (a hung Wii needs a power cycle; don't retry it unattended).
"""
import json, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wiiagent import Agent

HOST, KEYS, OUT = sys.argv[1], sys.argv[2], sys.argv[3]
keys = [k.strip() for k in open(KEYS) if k.strip()]
res = json.load(open(OUT)) if os.path.exists(OUT) else {"games": {}, "gaps": []}
todo = [k for k in keys if k not in res["games"]]


HANG_SECS = 360


def save():
    tmp = OUT + ".tmp"
    json.dump(res, open(tmp, "w"), indent=1)
    os.replace(tmp, OUT)


def say(msg):
    print(time.strftime("%H:%M:%S"), msg, flush=True)


def agent():
    return Agent(HOST, timeout=15)


def cmd(a, line):
    a.s.sendall((line + "\n").encode())
    return a.line()


def returns_len():
    a = agent()
    try:
        return len(a.get("sd:/arcade/returns.tsv").decode(errors="replace").splitlines())
    finally:
        a.close()


start_lines = returns_len()
say(f"{len(todo)} to test on {HOST}; returns.tsv has {start_lines} lines already")
sent = []                                    # keys handed to the cabinet and not yet returned
seen = start_lines
away_since = None
last_progress = time.time()

while todo or sent:
    try:
        a = agent()
        info = a.info()
        if away_since:
            gap = time.time() - away_since
            res["gaps"].append({"secs": round(gap), "ip": info["ip"], "uptime": info["uptime"]})
            say(f"back after {gap:.0f}s on {info['ip']} ({'cable' if info['ip'] == HOST else 'Wi-Fi?'}), "
                f"launcher up {info['uptime']}s")
            away_since = None
        lines = a.get("sd:/arcade/returns.tsv").decode(errors="replace").splitlines()
        for ln in lines[seen:]:
            parts = ln.split("\t")
            if len(parts) < 3:
                continue
            key, secs, attempt = parts[0], int(parts[1]), int(parts[2])
            if key not in sent and key not in todo:
                continue
            verdict = "not-in-library" if secs < 0 else "booted" if secs >= 45 else "came-back-early"
            prev = res["games"].get(key)
            if verdict == "came-back-early" and attempt < 2:
                say(f"{key}: back after {secs}s (attempt {attempt}), the cabinet retries")
                res["games"][key] = {"secs": secs, "attempt": attempt, "verdict": "retrying"}
            else:
                res["games"][key] = {"secs": secs, "attempt": attempt, "verdict": verdict}
                if key in sent:
                    sent.remove(key)
                say(f"{key}: {verdict} ({secs}s, attempt {attempt}); {len(todo) + len(sent)} left")
            last_progress = time.time()
        seen = len(lines)
        queued = cmd(a, "STAT sd:/arcade/testqueue.txt").startswith("OK")
        if not queued and info.get("mode") == "attract" and todo:
            batch, size = [], len("TESTQUEUE")
            while todo and size + len(todo[0]) + 1 < 580:
                size += len(todo[0]) + 1
                batch.append(todo.pop(0))
            say(f"queue {len(batch)}: {cmd(a, 'TESTQUEUE ' + ' '.join(batch))}")
            sent += batch
        elif not queued and not todo and sent and time.time() - last_progress > 900:
            say(f"no return for 15 min after the queue emptied; unaccounted: {' '.join(sent)}")
            for k in sent:
                res["games"].setdefault(k, {"secs": None, "attempt": None, "verdict": "no-return-record"})
            sent = []
        a.close()
        save()
    except OSError:
        if not away_since:
            away_since = time.time()
        elif time.time() - away_since > HANG_SECS and sent:
            key = sent[0]
            res["games"][key] = {"secs": None, "attempt": None, "verdict": "hang/power-off",
                                 "note": time.strftime("unreachable since %H:%M:%S", time.localtime(away_since))}
            save()
            say(f"HANG: {key} hasn't returned after {time.time() - away_since:.0f}s (cab unreachable); "
                f"recorded hang/power-off, stopping (exit 3). Not yet returned: {' '.join(sent[1:])}")
            sys.exit(3)
    time.sleep(20)

save()
say("done: " + json.dumps({v: sum(1 for g in res["games"].values() if g["verdict"] == v)
                           for v in {g["verdict"] for g in res["games"].values()}}))
