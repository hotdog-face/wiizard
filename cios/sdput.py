#!/usr/bin/env python3
"""Upload a folder's files to the cabinet's SD card, retrying around a busy agent.  sdput.py <cab ip> <local dir> <sd dir>"""
import os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from wiiagent import Agent
host, src, dst = sys.argv[1:4]
for _ in range(400):                         # the folder first (PUT doesn't create folders)
    try:
        a = Agent(host, timeout=30)
        try:
            a.s.sendall(f"MKDIR {dst}\n".encode())
            print("MKDIR", a.line(), flush=True)
        finally:
            a.close()
        break
    except OSError:
        time.sleep(5)
for name in sorted(os.listdir(src)):
    data = open(os.path.join(src, name), "rb").read()
    for _ in range(400):
        try:
            a = Agent(host, timeout=30)
            try:
                a.put(f"{dst}/{name}", data)
                back = a.get(f"{dst}/{name}")
            finally:
                a.close()
            assert back == data, name
            print(f"{name}: {len(data)} bytes ok", flush=True)
            break
        except OSError as e:
            if e.errno is None and not isinstance(e, TimeoutError) and "ERR" in str(e):
                raise                        # the agent refused: not a busy cabinet
            time.sleep(5)
    else:
        raise SystemExit("cabinet never answered")
