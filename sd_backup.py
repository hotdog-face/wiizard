#!/usr/bin/env python3
"""Back up a mounted Wii SD card to the NAS over plain SSH (the Synology refuses rsync-over-SSH), file by file.
Resumable: files already on the NAS with the same size are skipped. Skips macOS metadata (._*, .Spotlight-V100...).
    sd_backup.py <card mount> <NAS folder>"""
import os
import shlex
import subprocess
import sys
import time

import wiisite

NAS = wiisite.NAS   # user@host
SKIP_DIRS = {".Spotlight-V100", ".Trashes", ".fseventsd", ".TemporaryItems"}
EXCLUDE_TOP = set(os.environ.get("EXCLUDE_TOP", "").split(",")) - {""}   # e.g. EXCLUDE_TOP=games
ONLY_TOP = set(os.environ.get("ONLY_TOP", "").split(",")) - {""}


def remote_sizes(dest):
    cmd = f"cd {shlex.quote(dest)} 2>/dev/null && find . -type f -exec stat -c '%s %n' {{}} +"
    out = subprocess.run(["ssh", "-o", "BatchMode=yes", NAS, cmd], capture_output=True, text=True).stdout
    sizes = {}
    for line in out.splitlines():
        size, _, name = line.partition(" ")
        sizes[name[2:] if name.startswith("./") else name] = int(size)
    return sizes


def main(src, dest):
    files = []
    for root, dirs, names in os.walk(src):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS and not d.startswith("._"))
        if root == src:
            dirs[:] = [d for d in dirs if d not in EXCLUDE_TOP and (not ONLY_TOP or d in ONLY_TOP)]
            if ONLY_TOP:
                names = []
        for n in sorted(names):
            if n.startswith("._") or n == ".DS_Store":
                continue
            full = os.path.join(root, n)
            files.append((os.path.relpath(full, src), os.path.getsize(full)))
    total = sum(s for _, s in files)
    have = remote_sizes(dest)
    done = sum(s for rel, s in files if have.get(rel) == s)
    print(f"{len(files)} files, {total / 2**30:.1f} GiB; {done / 2**30:.1f} GiB already on the NAS", flush=True)
    t0 = time.time()
    copied = 0
    for rel, size in files:
        if have.get(rel) == size:
            continue
        target = os.path.join(dest, rel)
        cmd = f"mkdir -p {shlex.quote(os.path.dirname(target))} && cat > {shlex.quote(target + '.part')} && " \
              f"mv {shlex.quote(target + '.part')} {shlex.quote(target)}"
        for attempt in range(3):
            with open(os.path.join(src, rel), "rb") as f:
                r = subprocess.run(["ssh", "-o", "BatchMode=yes", NAS, cmd], stdin=f)
            if r.returncode == 0:
                break
            print(f"retry {rel} ({r.returncode})", flush=True)
            time.sleep(10)
        else:
            print(f"FAILED {rel}", flush=True)
            continue
        copied += size
        rate = copied / max(time.time() - t0, 1)
        left = total - done - copied
        print(f"{rel}  ({(done + copied) / 2**30:.1f}/{total / 2**30:.1f} GiB, {rate / 2**20:.0f} MiB/s, "
              f"~{left / max(rate, 1) / 60:.0f} min left)", flush=True)
    have = remote_sizes(dest)
    missing = [rel for rel, s in files if have.get(rel) != s]
    print(f"BACKUP {'COMPLETE' if not missing else 'INCOMPLETE'}: {len(files) - len(missing)}/{len(files)} files verified by size",
          flush=True)
    for rel in missing[:20]:
        print("  missing:", rel)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2])
