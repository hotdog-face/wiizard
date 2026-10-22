#!/usr/bin/env python3
"""Test the Wii games on cIOS 249 with someone at the cabinet (a working Wii game never returns by itself: it needs
HOME -> Wii Menu, after which Priiloader starts the launcher again).

    wii_games_test.py <cab ip> prep              un-hide the Wii games on the card only, restart the launcher, list them
    wii_games_test.py <cab ip> play <disc id>    start one (PLAYTEST) and judge it from returns.tsv + the launcher log
    wii_games_test.py <cab ip> finish <id>...    keep the passing ids visible: drop them from sdkit/hidden.txt, put the
                                                 others back on the card, publish

Verdict for "play": back within 60 s = FAIL (USB Loader GX gave up, as on the old stub; the launcher retries once and
then shows "Couldn't start"); still away after 90 s = the game is running -> ask for HOME -> Wii Menu; once back,
returns.tsv must show that id with >= 60 s away on attempt 1 = PASS.
"""
import os, re, subprocess, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
WII = os.path.dirname(HERE)
sys.path.insert(0, WII)
from wiiagent import Agent

WII_IDS = ["RNCEH4", "STKE08", "RSBE01", "SVME01"]
host, action, args = sys.argv[1], sys.argv[2], sys.argv[3:]


def agent(wait=600):
    end = time.time() + wait
    while True:
        try:
            return Agent(host, timeout=30)
        except OSError:
            if time.time() > end:
                return None
            time.sleep(3)


def strip_ids(text, ids):
    return "".join(l for l in text.splitlines(keepends=True) if l.strip() not in {f"id:{i}" for i in ids})


if action == "prep":
    a = agent()
    card = a.get("sd:/arcade/hidden.txt").decode()
    a.put("sd:/arcade/hidden.txt", strip_ids(card, WII_IDS).encode())
    print("card hidden.txt: Wii lines removed; restarting the launcher")
    a.cmd("REBOOT")
    a.close()
    time.sleep(10)
    a = agent()
    a.s.sendall(b"GAMES\n")
    while True:
        ln = a.line()
        if ln.startswith(("OK", "ERR")):
            break
        if any(i in ln for i in WII_IDS):
            print("  listed:", ln)

elif action == "play":
    gid = args[0]
    a = agent()
    before = len(a.get("sd:/arcade/returns.tsv").decode().splitlines())
    print("PLAYTEST:", a.cmd(f"PLAYTEST {gid}"))
    a.close()
    started = time.time()
    time.sleep(20)
    a = agent(wait=70)
    if a is not None:
        print(f"FAIL: the launcher was back after {time.time() - started:.0f} s")
    else:
        print("The game is running (away > 90 s).\n\nACTION NEEDED\n  1. Play a few seconds to see it really works.\n"
              "  2. Press HOME on the controller, choose \"Wii Menu\", confirm.\n"
              "  3. The WIIZARD menu comes back within ~20 s.\n")
        a = agent(wait=3600)
    lines = a.get("sd:/arcade/returns.tsv").decode().splitlines()[before:]
    log = [l for l in a.log().splitlines() if gid in l or "USB Loader" in l or "couldn't" in l.lower()]
    print("returns:", lines)
    print("\n".join(log[-8:]))
    mine = [l.split("\t") for l in lines if l.startswith(gid)]
    ok = any(int(s) >= 60 and a_ == "1" for _, s, a_ in mine)
    print("PASS" if ok else "FAIL", gid)

elif action == "finish":
    passing = args
    hid = os.path.join(WII, "sdkit", "hidden.txt")
    open(hid, "w").write(strip_ids(open(hid).read(), passing))
    failing = [i for i in WII_IDS if i not in passing]
    a = agent()
    card = a.get("sd:/arcade/hidden.txt").decode()
    if failing:
        card = card.rstrip("\n") + "\n" + "".join(f"id:{i}\n" for i in failing)
        a.put("sd:/arcade/hidden.txt", card.encode())
    a.close()
    print("visible:", passing, "still hidden:", failing)
    subprocess.run([sys.executable, os.path.join(WII, "publish.py"), "--no-ping"], check=True)
