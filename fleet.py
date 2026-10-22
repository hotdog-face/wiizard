#!/usr/bin/env python3
"""The cabinet fleet: what every Wii is doing, what's being played, what broke.

  fleet.py collect [--root DIR]   every 15 min on the always-on Ubuntu MacBook (cron): finds every cabinet on the LAN
                                  that is switched on, saves its status, play counts, failed starts, auto-hidden games,
                                  cabinet settings and the new part of its log; pushes files staged in <root>/push/
                                  (e.g. collections.tsv) to cabinets sitting idle in attract mode.
  fleet.py report                 on this Mac (the nightly health check): pulls the Ubuntu copy, works out popularity,
                                  rebuilds the collections, stages them for the cabinets, copies cabinet settings into
                                  sdkit/cabs (so every new card knows every cabinet) and writes fleet/report.md.

Default roots: ~/wii-fleet on Linux, ~/.claude/mcp/wii/fleet on the Mac. Needs only wiiagent.py next to it."""
import concurrent.futures as cf
import datetime as dt
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import wiiagent  # noqa: E402

import wiisite  # noqa: E402
SUBNET = wiisite.SUBNET
SIMULATORS = {wiisite.SIM_IP} - {""}            # the Docker Dolphin simulator (sim/sim.sh): not a cabinet
SIM_IDS = {"67349608"}                       # its console id (Dolphin's), wherever it shows up on the LAN
COLLECTOR = wiisite.COLLECTOR
COLLECTOR_ROOT = "wii-fleet"
PULL = ["stats.tsv", "failures.tsv", "autohide.txt"]
LOG_KEEP = 2 * 1024 * 1024
ISSUE_WORDS = ["safe mode", "launch failed", "giving up", "auto-hid", "relaunching", "router unreachable",
               "net_init failed", "retry failed"]


def now():
    return dt.datetime.now()


def default_root():
    return os.path.expanduser("~/wii-fleet") if sys.platform.startswith("linux") else os.path.join(HERE, "fleet")


# ---------------------------------------------------------------- collect (Ubuntu, cron)

def find_cabs():
    """{ip: info} for every agent answering on the LAN."""
    def one(i):
        ip = f"{SUBNET}.{i}"
        if ip in SIMULATORS:
            return None
        try:
            with socket.create_connection((ip, wiiagent.PORT), timeout=0.6):
                pass
        except OSError:
            return None
        info = wiiagent.probe(ip, timeout=3)
        if info and info.startswith("OK") and not any(f"id={sid}" in info for sid in SIM_IDS):
            return ip, dict(kv.split("=", 1) for kv in info.split()[1:] if "=" in kv)
        return None
    with cf.ThreadPoolExecutor(64) as ex:
        return dict(r for r in ex.map(one, range(1, 255)) if r)


def append_log(cab_dir, text):
    """Adds the part of the agent's RAM log not saved yet, stamped with the collection time."""
    path = os.path.join(cab_dir, "log.txt")
    tail_path = os.path.join(cab_dir, "log_tail.json")
    lines = [l for l in text.splitlines() if l.strip()]
    tail = json.load(open(tail_path)) if os.path.exists(tail_path) else []
    start = 0
    k = len(tail)
    for i in range(len(lines) - k, -1, -1) if tail else []:   # where the saved tail ends in the new text
        if lines[i:i + k] == tail:
            start = i + k
            break
    new = lines[start:]
    if new:
        stamp = now().strftime("%Y-%m-%d %H:%M")
        with open(path, "a") as f:
            if tail and start == 0:
                f.write(f"{stamp} --- (agent restarted since the last collection)\n")
            for l in new:
                f.write(f"{stamp} {l}\n")
        if os.path.getsize(path) > LOG_KEEP:
            data = open(path, "rb").read()[-LOG_KEEP // 2:]
            open(path, "wb").write(data[data.find(b"\n") + 1:])
    json.dump(lines[-5:], open(tail_path, "w"))
    return len(new)


def collect(root):
    cabs = find_cabs()
    stamp = now()
    push_dir = os.path.join(root, "push")
    for ip, info in cabs.items():
        cid = info.get("id", ip)
        d = os.path.join(root, "cabs", cid)
        os.makedirs(os.path.join(d, "stats"), exist_ok=True)
        state = {"ip": ip, "info": info, "last_seen": stamp.isoformat(timespec="seconds")}
        try:
            with wiiagent.Agent(ip, timeout=20) as a:
                df = a.cmd("DF sd:/").split()
                state["free"], state["total"] = int(df[1]), int(df[2])
                for name in PULL + [f"cabs/{cid}.cfg"]:
                    try:
                        data = a.get(f"sd:/arcade/{name}")
                    except OSError:
                        continue
                    out = os.path.join(d, "cab.cfg" if name.startswith("cabs/") else name)
                    open(out, "wb").write(data)
                a.s.sendall(b"GAMES\n")       # the cabinet's library: the master list for new cards
                rows = []
                while True:
                    ln = a.line()
                    if ln.startswith(("OK", "ERR")):
                        break
                    rows.append(ln)
                open(os.path.join(d, "games.tsv"), "w").write("\n".join(rows) + "\n")
                hs_dir = os.path.join(d, "hiscores")   # arcade high-score saves (.hi), decoded on the Mac
                for core in [n for n, size in a.ls("sd:/retroarch/savefiles") if size is None]:
                    for n, size in a.ls(f"sd:/retroarch/savefiles/{core}"):
                        if n.endswith(".hi") and not n.startswith("._"):
                            os.makedirs(hs_dir, exist_ok=True)
                            open(os.path.join(hs_dir, n), "wb").write(a.get(f"sd:/retroarch/savefiles/{core}/{n}"))
                try:                          # the menu's clock: local time (the Wiis' clocks may be UTC)
                    local = time.time() + dt.datetime.now().astimezone().utcoffset().total_seconds()
                    a.cmd(f"CLOCK {int(local)}")
                except OSError:
                    pass                      # launcher before 0.8.3
                if "log" in info.get("caps", ""):
                    state["new_log_lines"] = append_log(d, a.log())
                # small files staged by the Mac, only while nobody is playing
                idle_attract = info.get("mode") == "attract" and int(info.get("idle", 0)) > 120
                if idle_attract and os.path.isdir(push_dir):
                    for f in sorted(os.listdir(push_dir)):
                        # the pull updater also ships some of these (dist/files/arcade/): the newer copy wins, so
                        # an old staged file can't undo a publish (collections flipped back to 15 Oct every 15 min)
                        pub = os.path.join(root, "dist", "files", "arcade", f)
                        if os.path.exists(pub) and os.path.getmtime(pub) > os.path.getmtime(os.path.join(push_dir, f)):
                            continue
                        data = open(os.path.join(push_dir, f), "rb").read()
                        try:
                            same = a.get(f"sd:/arcade/{f}") == data
                        except OSError:
                            same = False
                        if not same:
                            a.put(f"sd:/arcade/{f}", data)
                            state.setdefault("pushed", []).append(f)
        except OSError as exc:
            state["error"] = str(exc)
        if os.path.exists(os.path.join(d, "stats.tsv")):
            shutil.copy(os.path.join(d, "stats.tsv"), os.path.join(d, "stats", stamp.strftime("%Y-%m-%d") + ".tsv"))
        old = json.load(open(os.path.join(d, "state.json"))) if os.path.exists(os.path.join(d, "state.json")) else {}
        state["seen_days"] = sorted(set(old.get("seen_days", [])) | {stamp.strftime("%Y-%m-%d")})[-120:]
        json.dump(state, open(os.path.join(d, "state.json"), "w"), indent=1)
        print(stamp.strftime("%H:%M"), cid, ip, info.get("agent"), info.get("mode"), state.get("error", "ok"),
              "pushed " + ",".join(state["pushed"]) if state.get("pushed") else "", flush=True)
    if not cabs:
        print(stamp.strftime("%H:%M"), "no cabinets on", flush=True)


# ---------------------------------------------------------------- report (Mac)

def read_stats(path):
    out = {}
    if os.path.exists(path):
        for line in open(path, errors="replace"):
            p = line.rstrip("\n").split("\t")
            if len(p) == 4 and p[1].isdigit():
                out[p[0]] = (int(p[1]), int(p[2] or 0), int(p[3] or 0))
    return out


def titles():
    """key -> title, from the arcade plan and the disc list."""
    t = {}
    plan = json.load(open(os.path.join(HERE, "sdkit/arcade_plan.json")))
    for r in plan:
        if r[3]:
            t[r[2][:-4]] = re.sub(r"\s*\([^()]*\)\s*$", "", r[3].split(" / ")[0]).strip()
    gc = os.path.join(HERE, "videos/gc_ids.txt")
    for line in open(gc) if os.path.exists(gc) else []:
        gid, name = line.rstrip("\n").split("|", 1)
        t[gid] = re.sub(r"\s*[\[(].*$", "", name.rsplit(".", 1)[0]).strip()
    return t


def popularity(root, days=30):
    """{key: {"plays30", "plays", "favs"}} over all cabinets; "_history_days": days of data we have."""
    pop, history = {}, 0
    cutoff = (now() - dt.timedelta(days=days)).strftime("%Y-%m-%d")
    for cid in os.listdir(os.path.join(root, "cabs")) if os.path.isdir(os.path.join(root, "cabs")) else []:
        d = os.path.join(root, "cabs", cid)
        snaps = sorted(os.listdir(os.path.join(d, "stats"))) if os.path.isdir(os.path.join(d, "stats")) else []
        if not snaps:
            continue
        latest = read_stats(os.path.join(d, "stats", snaps[-1]))
        base_name = next((s for s in reversed(snaps) if s[:10] <= cutoff), snaps[0])
        base = read_stats(os.path.join(d, "stats", base_name)) if base_name[:10] <= cutoff else {}
        first = dt.date.fromisoformat(snaps[0][:10])
        history = max(history, (now().date() - first).days)
        for key, (plays, last, fav) in latest.items():
            e = pop.setdefault(key, {"plays30": 0, "plays": 0, "favs": 0})
            e["plays"] += plays
            e["plays30"] += plays - base.get(key, (0, 0, 0))[0]
            e["favs"] += fav
    pop["_history_days"] = history
    return pop


def ago(iso):
    s = (now() - dt.datetime.fromisoformat(iso)).total_seconds()
    if s < 3600:
        return f"{int(s // 60)} min ago"
    if s < 86400:
        return f"{int(s // 3600)} h ago"
    return f"{int(s // 86400)} days ago"


def report():
    root = default_root()
    os.makedirs(root, exist_ok=True)
    subprocess.run(["ssh", "-o", "BatchMode=yes", COLLECTOR, f"mkdir -p {COLLECTOR_ROOT}/cabs"], capture_output=True)
    r = subprocess.run(["rsync", "-a", f"{COLLECTOR}:{COLLECTOR_ROOT}/cabs/", os.path.join(root, "cabs/")],
                       capture_output=True, text=True)
    pulled = r.returncode == 0
    pop = popularity(root)
    json.dump(pop, open(os.path.join(root, "popularity.json"), "w"), indent=1)
    # collections from the latest popularity -> staged for the cabinets (the collector pushes them when idle)
    subprocess.run([sys.executable, os.path.join(HERE, "sdkit/make_collections.py"), os.path.join(root, "popularity.json")],
                   check=True, capture_output=True)
    subprocess.run(["ssh", "-o", "BatchMode=yes", COLLECTOR, f"mkdir -p {COLLECTOR_ROOT}/push"], capture_output=True)
    subprocess.run(["scp", "-q", os.path.join(HERE, "sdkit/collections.tsv"), f"{COLLECTOR}:{COLLECTOR_ROOT}/push/"],
                   capture_output=True)
    import hiscores                          # "HI 12,340" badges: decoded saves -> sdkit/hiscores.tsv -> the cabinets
    undecoded = hiscores.main(root)
    subprocess.run(["scp", "-q", os.path.join(HERE, "sdkit/hiscores.tsv"), f"{COLLECTOR}:{COLLECTOR_ROOT}/push/"],
                   capture_output=True)
    names = titles()
    built = None
    dol = os.path.join(HERE, "agent/wii-agent.dol")
    if os.path.exists(dol):
        m = re.search(rb"\x00(\d+\.\d+\.\d+)\x00", open(dol, "rb").read())
        built = m.group(1).decode() if m else None
    lines = [f"# Garage arcade health report, {now():%a %b %d %H:%M}", ""]
    needs, fixed = [], []
    cabs_dir = os.path.join(root, "cabs")
    cab_ids = sorted(os.listdir(cabs_dir)) if os.path.isdir(cabs_dir) else []
    if not pulled:
        needs.append("The Ubuntu MacBook (fleet collector) didn't answer, so this report may be out of date.")
    if not cab_ids:
        lines.append("No cabinet has been seen yet.")
    since = now() - dt.timedelta(days=1)
    for cid in cab_ids:
        d = os.path.join(cabs_dir, cid)
        st = json.load(open(os.path.join(d, "state.json"))) if os.path.exists(os.path.join(d, "state.json")) else {}
        info = st.get("info", {})
        cfg = open(os.path.join(d, "cab.cfg")).read() if os.path.exists(os.path.join(d, "cab.cfg")) else ""
        os.makedirs(os.path.join(HERE, "sdkit/cabs"), exist_ok=True)
        if cfg:                              # every new card carries every cabinet's settings
            open(os.path.join(HERE, "sdkit/cabs", f"{cid}.cfg"), "w").write(cfg)
        name = info.get("cab", cid)
        last = st.get("last_seen")
        lines.append(f"## {name} (console {cid})")
        on_recently = last and (now() - dt.datetime.fromisoformat(last)).total_seconds() < 1800
        lines.append(f"- {'On now' if on_recently else 'Off'}; last seen {ago(last) if last else 'never'}"
                     f" at {st.get('ip', '?')}, launcher {info.get('agent', '?')}"
                     + (f" (current build {built})" if built and info.get('agent') != built else ""))
        if st.get("total"):
            free = st["free"] / 2**30
            lines.append(f"- Card: {free:.1f} GB free of {st['total'] / 2**30:.0f} GB")
            if free < 2:
                needs.append(f"{name}: the SD card is nearly full ({free:.1f} GB free).")
        snaps = sorted(os.listdir(os.path.join(d, "stats"))) if os.path.isdir(os.path.join(d, "stats")) else []
        if snaps:
            latest = read_stats(os.path.join(d, "stats", snaps[-1]))
            week = next((s for s in reversed(snaps) if s[:10] <= (now() - dt.timedelta(days=7)).strftime("%Y-%m-%d")), None)
            base = read_stats(os.path.join(d, "stats", week)) if week else {}
            played = sorted(((v[0] - base.get(k, (0,))[0], k) for k, v in latest.items()), reverse=True)
            played = [(n, k) for n, k in played if n > 0]
            total = sum(n for n, _ in played)
            top = ", ".join(f"{names.get(k, k)} ({n})" for n, k in played[:5])
            lines.append(f"- Games started in the last 7 days: {total}" + (f"; most: {top}" if top else ""))
        hidden = [l.strip() for l in open(os.path.join(d, "autohide.txt"))] if os.path.exists(os.path.join(d, "autohide.txt")) else []
        for h in hidden:
            key = h.split(":", 1)[-1]
            fixed.append(f"{name}: took {names.get(key, key)} off the menu after it failed to start twice.")
        issues = []
        logp = os.path.join(d, "log.txt")
        for l in open(logp, errors="replace") if os.path.exists(logp) else []:
            try:
                when = dt.datetime.strptime(l[:16], "%Y-%m-%d %H:%M")
            except ValueError:
                continue
            if when >= since and any(w in l for w in ISSUE_WORDS):
                issues.append(l[17:].strip())
        if issues:
            lines.append(f"- Log, last 24 h: {len(issues)} notable lines, e.g. `{issues[-1][:120]}`")
            if any("safe mode" in i for i in issues):
                needs.append(f"{name}: the launcher fell back to safe mode. I can fix it over Wi-Fi.")
        if st.get("error"):
            lines.append(f"- Last collection error: {st['error']}")
        lines.append("")
    if undecoded:
        lines += ["## High scores", f"- Saves without a decoder yet (Claude can add them): {', '.join(undecoded)}", ""]
    lines += ["## Fixed automatically", *(f"- {x}" for x in fixed or ["Nothing needed fixing."]), ""]
    hist = pop.get("_history_days", 0)
    never = sorted(k for k, v in pop.items() if k != "_history_days" and not v["plays"])
    lines += ["## Popularity",
              f"- {hist} days of play data from {len(cab_ids)} cabinet(s); collections are ordered by plays in the "
              f"last 30 days" + ("" if hist >= 30 else " (games nobody plays get dropped after 30 days of data)") + ".", ""]
    lines += ["## Needs you", *(f"- **ACTION NEEDED:** {x}" for x in needs)] if needs else ["## Needs you", "- Nothing."]
    text = "\n".join(lines) + "\n"
    open(os.path.join(root, "report.md"), "w").write(text)
    print(text)
    return needs


if __name__ == "__main__":
    args = sys.argv[1:]
    root = args[args.index("--root") + 1] if "--root" in args else default_root()
    if args and args[0] == "collect":
        os.makedirs(root, exist_ok=True)
        collect(root)
    elif args and args[0] == "report":
        report()
    else:
        sys.exit(__doc__)
