#!/usr/bin/env python3
"""Copy NAND files/folders from a cabinet to the Mac, retrying around a busy agent (games running, one client at a time).
    nandgrab.py <cab ip> <dest dir> <nand path>...   (a path ending in / is listed and copied file by file)"""
import os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from wiiagent import Agent

host, dest, paths = sys.argv[1], sys.argv[2], sys.argv[3:]
PATCH = True                                 # IOSPATCH first: title contents and tickets need the ISFS permission patch

def attempt(fn):
    for _ in range(400):
        try:
            a = Agent(host, timeout=30)
            try:
                r = a.cmd("IOSPATCH") if PATCH else ""
                if PATCH and not r.startswith("OK"):
                    print("  IOSPATCH:", r, flush=True)
                return fn(a)
            finally:
                a.close()
        except OSError as e:
            if e.errno is None and not isinstance(e, TimeoutError):
                print(f"  {e}", flush=True)    # the agent said ERR: the path isn't there
                return None
            time.sleep(5)
    raise SystemExit("cabinet never answered")

todo = []
for p in paths:
    if p.endswith("/"):
        names = attempt(lambda a: a.nls(p.rstrip("/"))) or []
        print(p, "->", names, flush=True)
        todo += [p + n for n in names]
    else:
        todo.append(p)
for p in todo:
    out = os.path.join(dest, p.lstrip("/"))
    if os.path.exists(out):
        continue
    data = attempt(lambda a: a.nget(p))
    if data is None:
        continue
    os.makedirs(os.path.dirname(out), exist_ok=True)
    open(out, "wb").write(data)
    print(f"{p}: {len(data)} bytes", flush=True)
