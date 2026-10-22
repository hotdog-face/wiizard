#!/usr/bin/env python3
"""Does every arcade game in the menu start and draw in the core the Wii runs it on? Runs each game headlessly for
40 s in the macOS build of the same libretro core (fbalpha2012*, mame2000) and checks that the core accepts the
ROM set and that the picture has detail and motion. Writes verify_arcade.json: stem -> "ok" | reason."""
import json
import os
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
CORES = HERE.parent / "downloads/cores-macos"


def check(row):
    system, z, core = row[0], row[2], row[6]
    stem = z[:-4]
    with tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, "v.mp4")
        sysdir = str(HERE / "sys")
        try:
            r = subprocess.run(["python3", str(HERE / "record_arcade.py"), str(CORES / f"{core}_libretro.dylib"),
                                str(HERE / "roms" / z), out, "--attract", "--seconds", "40", "--skip", "300",
                                "--keep", "0", "--sysdir", sysdir], capture_output=True, text=True, timeout=300,
                               env={**os.environ, "ARCADE_ZIP": "1"})
        except subprocess.TimeoutExpired:
            return stem, "timed out"
        if "core refused" in (r.stdout + r.stderr):
            return stem, "core refused the ROM set"
        if r.returncode != 0 or not os.path.exists(out):
            return stem, "no picture (" + (r.stderr.strip().splitlines() or ["?"])[-1][:80] + ")"
        # picture check: sample frames, need detail (not one colour) and change over time
        probe = subprocess.run(["ffmpeg", "-v", "error", "-i", out, "-vf", "fps=1,scale=32:24,format=gray",
                                "-f", "rawvideo", "pipe:"], capture_output=True).stdout
        frames = [probe[i:i + 768] for i in range(0, len(probe) - 767, 768)]
        if len(frames) < 5:
            return stem, "too few frames"
        detail = sum(max(f) - min(f) > 40 for f in frames)
        motion = sum(1 for a, b in zip(frames, frames[1:]) if sum(abs(x - y) for x, y in zip(a, b)) > 768 * 3)
        if detail < len(frames) // 3:
            return stem, f"mostly blank picture ({detail}/{len(frames)} frames with detail)"
        if motion < 2:
            return stem, "picture never changes"
        return stem, "ok"


def main():
    plan = json.load(open(HERE.parent / "sdkit/arcade_plan.json"))
    hidden = {l.strip()[4:] for l in open(HERE.parent / "sdkit/hidden.txt") if l.startswith("rom:")}
    rows = [r for r in plan if r[3] and r[2][:-4] not in hidden]
    results = {}
    with ThreadPoolExecutor(4) as ex:
        for stem, verdict in ex.map(check, rows):
            results[stem] = verdict
            if verdict != "ok":
                print(stem, verdict, flush=True)
    json.dump(results, open(HERE / "verify_arcade.json", "w"), indent=1)
    ok = sum(v == "ok" for v in results.values())
    print(f"{ok} of {len(results)} arcade games start and draw")


if __name__ == "__main__":
    main()
