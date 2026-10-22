#!/usr/bin/env python3
"""Record an attract-mode clip for every arcade game in sdkit/arcade_plan.json (FBNeo, then MAME 2003-Plus).
Skips games that already have rec/<stem>.mp4. Writes rec/results.json: stem -> "fbneo" | "mame2003_plus" | "failed"."""
import json
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
CORES = HERE.parent / "downloads/cores-macos"
ROMS, REC, SYS = HERE / "roms", HERE / "rec", HERE / "sys"


def record(stem):
    out = REC / f"{stem}.mp4"
    if out.exists() and out.stat().st_size > 100_000:
        return stem, "existing"
    for core in ("fbneo", "mame2003_plus"):
        r = subprocess.run(["python3", str(HERE / "record_arcade.py"), str(CORES / f"{core}_libretro.dylib"),
                            str(ROMS / f"{stem}.zip"), str(out), "--attract", "--seconds", "75", "--skip", "600",
                            "--sysdir", str(SYS)], capture_output=True, text=True, timeout=600,
                           env={**os.environ, "ARCADE_ZIP": "1"})
        if r.returncode == 0 and out.exists() and out.stat().st_size > 100_000:   # an error screen is ~70 KB
            return stem, core
        out.unlink(missing_ok=True)
    return stem, "failed"


def main():
    REC.mkdir(exist_ok=True)
    plan = json.load(open(HERE.parent / "sdkit/arcade_plan.json"))
    stems = sorted({row[2].rsplit(".", 1)[0] for row in plan if row[3]})
    results = {}
    with ThreadPoolExecutor(3) as ex:
        for stem, how in ex.map(record, stems):
            results[stem] = how
            print(stem, how, flush=True)
    json.dump(results, open(REC / "results.json", "w"), indent=1)
    print(sum(v != "failed" for v in results.values()), "of", len(results), "recorded")


if __name__ == "__main__":
    main()
