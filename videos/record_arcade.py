#!/usr/bin/env python3
"""Record a gameplay preview by running a libretro core headlessly.
(Copy of arcadehub/record_preview.py for the Wii launcher: arcade zips are handed to the core as a path, unopened,
since FBNeo/MAME find the game by the zip's name.)

For games ScreenScraper has no video for (ROM hacks, homebrew). RetroArch's own
--record writes empty files on macOS (video_driver=null quits the frame loop),
so this drives the core itself through ctypes: no window, no audio, no display.

    python3 record_preview.py <core.dylib> <rom> <out.mp4> [--seconds 15] [--skip 8]

A small input bot presses through the title screens during `--skip` and then
plays (badly); `--attract` records the demo loop with no input instead. Frames go to ffmpeg as raw RGB24.
"""
import argparse
import ctypes
import os

import numpy as np
import subprocess
import sys
from ctypes import c_bool, c_char_p, c_double, c_float, c_int16, c_size_t, c_uint, c_void_p, POINTER

ENV_GET_CAN_DUPE = 3
ENV_SET_PIXEL_FORMAT = 10
ENV_GET_SYSTEM_DIRECTORY = 9
ENV_GET_SAVE_DIRECTORY = 31
ENV_GET_VARIABLE = 15
ENV_GET_VARIABLE_UPDATE = 17
ENV_SET_SUPPORT_ACHIEVEMENTS = 42
FMT_0RGB1555, FMT_XRGB8888, FMT_RGB565 = 0, 1, 2


class GameInfo(ctypes.Structure):
    _fields_ = [("path", c_char_p), ("data", c_void_p), ("size", c_size_t), ("meta", c_char_p)]


class Geometry(ctypes.Structure):
    _fields_ = [("base_width", c_uint), ("base_height", c_uint),
                ("max_width", c_uint), ("max_height", c_uint), ("aspect_ratio", c_float)]


class Timing(ctypes.Structure):
    _fields_ = [("fps", c_double), ("sample_rate", c_double)]


class AVInfo(ctypes.Structure):
    _fields_ = [("geometry", Geometry), ("timing", Timing)]


ENV_CB = ctypes.CFUNCTYPE(c_bool, c_uint, c_void_p)
VIDEO_CB = ctypes.CFUNCTYPE(None, c_void_p, c_uint, c_uint, c_size_t)
AUDIO_CB = ctypes.CFUNCTYPE(None, c_int16, c_int16)
AUDIO_BATCH_CB = ctypes.CFUNCTYPE(c_size_t, POINTER(c_int16), c_size_t)
POLL_CB = ctypes.CFUNCTYPE(None)
INPUT_CB = ctypes.CFUNCTYPE(c_int16, c_uint, c_uint, c_uint, c_uint)


def to_rgb24(buf, width, height, pitch, fmt):
    """Core framebuffer -> packed RGB24, via numpy (pure Python is ~10x slower)."""
    if fmt == FMT_XRGB8888:
        a = np.frombuffer(buf, dtype=np.uint8).reshape(height, pitch // 4, 4)[:, :width, :3]
        return a[:, :, ::-1].tobytes()  # BGRA -> RGB
    v = np.frombuffer(buf, dtype="<u2").reshape(height, pitch // 2)[:, :width].astype(np.uint16)
    if fmt == FMT_RGB565:
        r, g, b = (v >> 11) & 0x1F, (v >> 5) & 0x3F, v & 0x1F
        scale = (255 // 31, 255 // 63, 255 // 31)
    else:  # 0RGB1555
        r, g, b = (v >> 10) & 0x1F, (v >> 5) & 0x1F, v & 0x1F
        scale = (255 // 31, 255 // 31, 255 // 31)
    out = np.empty((height, width, 3), dtype=np.uint8)
    out[:, :, 0] = (r * scale[0]).astype(np.uint8)
    out[:, :, 1] = (g * scale[1]).astype(np.uint8)
    out[:, :, 2] = (b * scale[2]).astype(np.uint8)
    return out.tobytes()


JOY_B, JOY_START, JOY_UP, JOY_DOWN, JOY_LEFT, JOY_RIGHT, JOY_A = 0, 3, 4, 5, 6, 7, 8


def bot(frame, skip, port, device, id_):
    """A player who knows nothing: START and A through the title screens, then
    mostly forward, a change of direction now and then, and fire. Good enough
    to show what a game looks like being played. Never SELECT (menus)."""
    if port or device != 1:
        return 0
    if frame < skip:                                   # get past the title and menus
        k = frame % 90
        return int((id_ == JOY_START and 10 <= k < 16) or (id_ in (JOY_A, JOY_B) and 55 <= k < 61))
    t = frame - skip
    seg = (t // 70) * 2654435761 & 0xFFFF             # a new direction every ~1.2 s
    way = (JOY_RIGHT, JOY_RIGHT, JOY_RIGHT, JOY_LEFT, JOY_UP, JOY_DOWN, JOY_RIGHT)[seg % 7]
    if id_ == way:
        return 1
    if id_ == JOY_A:
        return int(t % 22 < 5)
    if id_ == JOY_B:
        return int(t % 37 < 4)
    return 0                                           # START in play is pause: never


LOG_FN_T = ctypes.CFUNCTYPE(None, ctypes.c_int, ctypes.c_char_p)


def _core_log(level, fmt):
    if level >= 2 and fmt:                                 # warnings and errors (format string only)
        sys.stderr.write("core: " + fmt.decode(errors="replace").rstrip() + "\n")


LOG_FN = LOG_FN_T(_core_log)


class _LogIface(ctypes.Structure):
    _fields_ = [("log", LOG_FN_T)]


LOG_IFACE = _LogIface(LOG_FN)


def record(core_path, rom_path, out_path, seconds, skip, sysdir, play=True, keep=15):
    core = ctypes.CDLL(core_path)
    state = {"fmt": FMT_0RGB1555, "w": 0, "h": 0, "ff": None, "frames": 0, "kept": 0, "tiny": [],
             "pcm": None, "rate": 44100}
    sysdir_b = ctypes.create_string_buffer(sysdir.encode())

    def environment(cmd, data):
        if cmd == 27:                                      # RETRO_ENVIRONMENT_GET_LOG_INTERFACE
            ctypes.memmove(data, ctypes.addressof(LOG_IFACE), ctypes.sizeof(LOG_IFACE))
            return True
        if cmd == 1:                                       # RETRO_ENVIRONMENT_SET_ROTATION (vertical arcade games)
            state["rot"] = ctypes.cast(data, POINTER(c_uint)).contents.value % 4
            return True
        if cmd == ENV_SET_PIXEL_FORMAT:
            state["fmt"] = ctypes.cast(data, POINTER(c_uint)).contents.value
            return True
        if cmd == ENV_GET_CAN_DUPE:
            ctypes.cast(data, POINTER(c_bool)).contents.value = True
            return True
        if cmd in (ENV_GET_SYSTEM_DIRECTORY, ENV_GET_SAVE_DIRECTORY):
            ctypes.cast(data, POINTER(c_char_p)).contents.value = ctypes.addressof(sysdir_b)
            return True
        if cmd == ENV_GET_VARIABLE_UPDATE:
            ctypes.cast(data, POINTER(c_bool)).contents.value = False
            return True
        return False  # every other request: core falls back to its default

    def video_refresh(data, width, height, pitch):
        state["frames"] += 1
        if not data or state["frames"] <= skip:
            return
        if state["ff"] is None:
            state["w"], state["h"] = width, height
            state["ff"] = subprocess.Popen(
                ["ffmpeg", "-nostdin", "-loglevel", "error", "-y", "-f", "rawvideo",
                 "-pixel_format", "rgb24", "-video_size", "%dx%d" % (width, height),
                 "-framerate", "60", "-i", "-", "-c:v", "libx264", "-profile:v", "baseline",
                 "-level", "3.0", "-pix_fmt", "yuv420p", "-crf", "24", out_path],
                stdin=subprocess.PIPE)
        if (width, height) != (state["w"], state["h"]):
            if state["kept"] < 120:                        # early switch (boot screen size): follow it
                state["ff"].stdin.close(); state["ff"].wait()
                state["ff"] = None; state["kept"] = 0; state["tiny"] = []
                return video_refresh(data, width, height, pitch)
            return  # resolution switch mid-clip (SNES hi-res): drop the odd frames
        buf = ctypes.string_at(data, pitch * height)
        try:
            rgb = to_rgb24(buf, width, height, pitch, state["fmt"])
            state["ff"].stdin.write(rgb)
            a = np.frombuffer(rgb, dtype=np.uint8).reshape(height, width, 3)
            state["tiny"].append(a[::max(1, height // 24), ::max(1, width // 24)].mean(axis=2).astype(np.int16))
            state["kept"] += 1
        except BrokenPipeError:
            pass

    def audio_batch(data, frames):
        """Stereo int16 pairs; kept once video starts so picture and sound line up."""
        if state["pcm"] is not None and state["frames"] > skip:
            state["pcm"].write(ctypes.string_at(data, frames * 4))
        return frames

    cbs = [ENV_CB(environment), VIDEO_CB(video_refresh), AUDIO_CB(lambda l, r: None),
           AUDIO_BATCH_CB(audio_batch), POLL_CB(lambda: None),
           INPUT_CB(lambda port, device, index, id_: bot(state["frames"], skip, port, device, id_) if play else 0)]
    core.retro_set_environment(cbs[0])
    core.retro_set_video_refresh(cbs[1])
    core.retro_set_audio_sample(cbs[2])
    core.retro_set_audio_sample_batch(cbs[3])
    core.retro_set_input_poll(cbs[4])
    core.retro_set_input_state(cbs[5])
    core.retro_init()

    if rom_path.lower().endswith(".zip") and os.environ.get("ARCADE_ZIP"):   # arcade: path only, no data
        info = GameInfo(rom_path.encode(), None, 0, None)
        if not core.retro_load_game(ctypes.byref(info)):
            raise SystemExit("core refused %s" % rom_path)
        data = None
    elif rom_path.lower().endswith(".zip"):              # most cores here read the ROM itself, not a zip
        import zipfile
        with zipfile.ZipFile(rom_path) as z:
            inner = max(z.infolist(), key=lambda i: i.file_size)
            data = z.read(inner)
        rom_path = os.path.join(sysdir, os.path.basename(inner.filename))   # the name picks the mapper
        with open(rom_path, "wb") as f:
            f.write(data)
    else:
        with open(rom_path, "rb") as f:
            data = f.read()
    if data is not None:
        blob = ctypes.create_string_buffer(data, len(data))
        info = GameInfo(rom_path.encode(), ctypes.cast(blob, c_void_p), len(data), None)
        if not core.retro_load_game(ctypes.byref(info)):
            raise SystemExit("core refused %s" % rom_path)
    av = AVInfo()
    core.retro_get_system_av_info(ctypes.byref(av))
    fps = av.timing.fps or 60.0
    state["rate"] = int(av.timing.sample_rate or 44100)
    pcm_path = out_path + ".pcm"
    state["pcm"] = open(pcm_path, "wb")
    for _ in range(int((skip + seconds * fps))):
        core.retro_run()
    if os.environ.get("PROBE_GEOMETRY"):                   # bezels.py: shape of the picture the core reports
        core.retro_get_system_av_info(ctypes.byref(av))
        print("GEOM %d %d %.4f %d" % (av.geometry.base_width, av.geometry.base_height, av.geometry.aspect_ratio,
                                      state.get("rot", 0)), flush=True)
        os._exit(0)
    core.retro_unload_game()
    core.retro_deinit()
    if data is not None and rom_path.startswith(sysdir + os.sep):   # the ROM unpacked from its zip
        os.remove(rom_path)
    if state["ff"]:
        state["ff"].stdin.close()
        state["ff"].wait()
    state["pcm"].close()
    # Mux the captured sound in: attract mode plays it, browsing stays silent.
    if state["kept"] and os.path.getsize(pcm_path) > 4096:
        muxed = out_path + ".mux.mp4"
        r = subprocess.run(["ffmpeg", "-nostdin", "-loglevel", "error", "-y", "-i", out_path,
                            "-f", "s16le", "-ar", str(state["rate"]), "-ac", "2", "-i", pcm_path,
                            "-c:v", "copy", "-c:a", "aac", "-b:a", "48k", "-ac", "1",
                            "-shortest", "-movflags", "+faststart", muxed])
        if r.returncode == 0 and os.path.exists(muxed):
            os.replace(muxed, out_path)
        else:
            os.path.exists(muxed) and os.remove(muxed)
    os.remove(pcm_path)
    if keep and state["kept"] > keep * fps:
        cut_best(out_path, state["tiny"], fps, keep)
    rot = state.get("rot", 0)
    if rot and os.path.exists(out_path):                   # 1 = 90 deg counter-clockwise, 2 = 180, 3 = 270
        vf = {1: "transpose=2", 2: "transpose=2,transpose=2", 3: "transpose=1"}[rot]
        tmp = out_path + ".rot.mp4"
        r = subprocess.run(["ffmpeg", "-nostdin", "-loglevel", "error", "-y", "-i", out_path, "-vf", vf,
                            "-c:v", "libx264", "-profile:v", "baseline", "-level", "3.0", "-pix_fmt", "yuv420p",
                            "-crf", "24", "-c:a", "copy", tmp])
        if r.returncode == 0:
            os.replace(tmp, out_path)
    return state["kept"]


def cut_best(path, tiny, fps, keep):
    """Keep the liveliest `keep` seconds: plenty of motion, not a blank or
    single-colour screen, and a nudge toward later windows (logos come first)."""
    n = len(tiny)
    motion = np.array([0.0] + [float(np.abs(tiny[i] - tiny[i - 1]).mean()) for i in range(1, n)])
    detail = np.array([float(t.std()) for t in tiny])
    blank = detail < 6
    per = int(fps)
    best, best_score = 0, -1e9
    win = int(keep * fps)
    for start in range(0, n - win + 1, per):
        m = motion[start:start + win]
        score = np.minimum(m, 12).mean() + 0.15 * detail[start:start + win].mean() \
            - 20 * blank[start:start + win].mean() + 0.5 * start / n
        if score > best_score:
            best, best_score = start, score
    tmp = path + ".cut.mp4"
    r = subprocess.run(["ffmpeg", "-nostdin", "-loglevel", "error", "-y", "-ss", "%.2f" % (best / fps), "-i", path,
                        "-t", str(keep), "-c:v", "libx264", "-profile:v", "baseline", "-level", "3.0",
                        "-pix_fmt", "yuv420p", "-crf", "24", "-c:a", "aac", "-b:a", "48k", "-ac", "1",
                        "-movflags", "+faststart", tmp])
    if r.returncode == 0 and os.path.exists(tmp):
        os.replace(tmp, path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("core")
    ap.add_argument("rom")
    ap.add_argument("out")
    ap.add_argument("--seconds", type=float, default=60, help="played; the best --keep of it is kept")
    ap.add_argument("--keep", type=float, default=15)
    ap.add_argument("--skip", type=int, default=240, help="frames to drop (title screens)")
    ap.add_argument("--attract", action="store_true", help="no input: record the attract loop")
    ap.add_argument("--sysdir", default="/tmp")
    a = ap.parse_args()
    kept = record(a.core, a.rom, a.out, a.seconds, a.skip, a.sysdir, not a.attract, a.keep)
    print("%s: %d frames" % (a.out, kept))
    return 0 if kept else 1


if __name__ == "__main__":
    sys.exit(main())
