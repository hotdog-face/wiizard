#!/usr/bin/env python3
"""Audio for the clips (attract mode): the same window convert.py takes from each source video, as 16 kHz mono
signed 16-bit big-endian PCM in a .gaud file ("GAU1", u32 rate, u32 samples, samples).
    audio.py videos.json <out dir> [seconds]"""
import json
import os
import struct
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

RATE = 16000


def one(src, dst, seconds):
    r = subprocess.run(["ffmpeg", "-v", "error", "-ss", "2", "-i", src, "-t", str(seconds), "-vn", "-ac", "1",
                        "-ar", str(RATE), "-af", "loudnorm=I=-20:TP=-2", "-f", "s16be", "pipe:"], capture_output=True)
    pcm = r.stdout
    if len(pcm) < RATE:                      # under half a second: no usable sound
        return 0
    tmp = dst + ".part"
    with open(tmp, "wb") as f:
        f.write(b"GAU1" + struct.pack(">II", RATE, len(pcm) // 2) + pcm)
    os.replace(tmp, dst)
    return len(pcm)


def main(videos_json, out_dir, seconds=20):
    os.makedirs(out_dir, exist_ok=True)
    jobs = json.load(open(videos_json))

    def go(item):
        key, src = item
        dst = os.path.join(out_dir, key + ".gaud")
        if os.path.exists(dst):
            return key, os.path.getsize(dst)
        return key, one(src, dst, seconds)

    total = n = 0
    with ThreadPoolExecutor(4) as ex:
        for key, size in ex.map(go, jobs.items()):
            total += size
            n += size > 0
    print(f"{n} of {len(jobs)} clips have sound, {total / 2**20:.0f} MB")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else 20)
