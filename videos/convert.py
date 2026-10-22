#!/usr/bin/env python3
"""Turn gameplay MP4s into the launcher's clip format (.gvid): silent Motion-JPEG frames the Wii decodes with
libjpeg-turbo. 320x240 (4:3, letterboxed/pillarboxed, never cropped), 20 fps, at most 20 s.
    convert.py videos.json <out dir>        (videos.json: launcher key -> mp4, from scrape.py map)
.gvid layout, big-endian: "GVD1", u16 width, u16 height, u16 fps*100, u16 0, u32 frames,
u32 offset[frames + 1] (from the start of the file; the last one is the end), then the JPEG frames."""
import json
import os
import struct
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

W, H, FPS, SECONDS, QUALITY = 320, 240, 20, 20, 6


def jpeg_frames(data):
    frames, i = [], 0
    while True:
        s = data.find(b"\xff\xd8", i)
        if s < 0:
            return frames
        e = data.find(b"\xff\xd9", s + 2)
        if e < 0:
            return frames
        frames.append(data[s:e + 2])
        i = e + 2


def convert(src, dst):
    vf = (f"fps={FPS},scale={W}:{H}:force_original_aspect_ratio=decrease,"
          f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:black,format=yuvj420p")
    r = subprocess.run(["ffmpeg", "-v", "error", "-ss", "2", "-i", src, "-t", str(SECONDS), "-an", "-vf", vf,
                        "-c:v", "mjpeg", "-q:v", str(QUALITY), "-f", "mjpeg", "pipe:"], capture_output=True)
    frames = jpeg_frames(r.stdout)
    if len(frames) < FPS * 3:                # too short (or the -ss skipped everything): try from the start
        r = subprocess.run(["ffmpeg", "-v", "error", "-i", src, "-t", str(SECONDS), "-an", "-vf", vf,
                            "-c:v", "mjpeg", "-q:v", str(QUALITY), "-f", "mjpeg", "pipe:"], capture_output=True)
        frames = jpeg_frames(r.stdout)
    if not frames:
        return 0
    head = struct.pack(">4sHHHHI", b"GVD1", W, H, FPS * 100, 0, len(frames))
    pos = len(head) + 4 * (len(frames) + 1)
    offsets = []
    for f in frames:
        offsets.append(pos)
        pos += len(f)
    offsets.append(pos)
    tmp = dst + ".part"
    with open(tmp, "wb") as out:
        out.write(head + struct.pack(f">{len(offsets)}I", *offsets) + b"".join(frames))
    os.replace(tmp, dst)
    return pos


def main(videos_json, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    jobs = json.load(open(videos_json))

    def one(item):
        key, src = item
        dst = os.path.join(out_dir, key + ".gvid")
        if os.path.exists(dst) and os.path.getmtime(dst) >= os.path.getmtime(src):
            return key, os.path.getsize(dst)
        return key, convert(src, dst)

    total = 0
    with ThreadPoolExecutor(4) as ex:
        for key, size in ex.map(one, jobs.items()):
            total += size
            print(f"{key}: {size / 1024:.0f} KB" if size else f"{key}: FAILED", flush=True)
    print(f"{len(jobs)} clips, {total / 2**20:.0f} MB")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
