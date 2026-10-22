#!/usr/bin/env python3
"""Install a built cIOS (build_cios.py, uploaded with sdput.py) on a cabinet through the launcher's agent.

    install_cios.py <cab ip> <sd dir> <expected title id hex> <expected version>

Stops the cabinet's test queue first (a game starting mid-install would reload IOS under ES), applies IOSPATCH, runs
CIOSINSTALL, then reads the installed TMD back. Run with the Mac-side test runner (cab_queue.py) stopped; it resumes
from its results file afterwards.
"""
import os, struct, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from wiiagent import Agent

host, sddir, tid, version = sys.argv[1], sys.argv[2], int(sys.argv[3], 16), int(sys.argv[4])

while True:                                  # wait for a gap between games
    try:
        a = Agent(host, timeout=180)
        break
    except OSError:
        time.sleep(3)
print("INFO", a.info())
print("TESTQUEUE stop:", a.cmd("TESTQUEUE"))
print("mode:", a.info().get("mode"))
local = os.path.join(os.path.dirname(os.path.abspath(__file__)), sys.argv[5]) if len(sys.argv) > 5 else None
if local:                                    # the upload must match the build, file by file
    for name in sorted(os.listdir(local)):
        want = os.path.getsize(os.path.join(local, name))
        got = a.cmd(f"STAT {sddir}/{name}")
        assert got.split()[1] == str(want), f"{name}: card {got}, build {want}"
        assert a.get(f"{sddir}/{name}") == open(os.path.join(local, name), "rb").read(), name
    print(f"upload verified: {len(os.listdir(local))} files match {local}")
print("IOSPATCH:", a.cmd("IOSPATCH"))
print("CIOSINSTALL:", a.cmd(f"CIOSINSTALL {sddir}"))
tmd = a.nget(f"/title/{tid >> 32:08x}/{tid & 0xffffffff:08x}/content/title.tmd")
h = 0x140
got_tid = struct.unpack(">Q", tmd[h + 0x4c:h + 0x54])[0]
got_ver, n = struct.unpack(">HH", tmd[h + 0x9c:h + 0xa0])
print(f"installed TMD: {got_tid:016x} v{got_ver}, {n} contents")
print("ok" if (got_tid, got_ver) == (tid, version) else "MISMATCH")
print("\n".join(l for l in a.log().splitlines() if "cios" in l or "iospatch" in l))
