#!/usr/bin/env python3
"""Reference run of an arcade game in the macOS build of the same libretro core the Wii uses: native frames (PNG,
unscaled, unrotated as the core hands them over) and the core's raw audio at its own rate (WAV), with a scripted
coin/start/joystick input. Used to tell the core's own sound apart from what the Wii's RetroArch does to it.
    hostref.py <core.dylib> <rom.zip> <outdir> --seconds 40 [--coin 20] [--frames 600,1500] [--walk]"""
import argparse, ctypes, os, sys, wave
import numpy as np
from PIL import Image
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import record_arcade as ra   # reuse the ctypes structures / pixel conversion

J_B, J_Y, J_SELECT, J_START, J_UP, J_DOWN, J_LEFT, J_RIGHT, J_A = 0, 1, 2, 3, 4, 5, 6, 7, 8


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("core"); ap.add_argument("rom"); ap.add_argument("out")
    ap.add_argument("--seconds", type=float, default=40)
    ap.add_argument("--coin", type=float, default=None, help="emulated seconds: coin, start 1 s later, again +6 s")
    ap.add_argument("--frames", default="", help="frame numbers to save as PNG")
    ap.add_argument("--walk", action="store_true", help="after start: walk left/right and jump now and then")
    ap.add_argument("--sysdir", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "sys"))
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    want = {int(x) for x in a.frames.split(",") if x}
    core = ctypes.CDLL(a.core)
    st = {"fmt": ra.FMT_0RGB1555, "n": 0, "pcm": bytearray(), "rot": 0}
    sysdir_b = ctypes.create_string_buffer(os.path.abspath(a.sysdir).encode())

    def env(cmd, data):
        if cmd == 27:
            ctypes.memmove(data, ctypes.addressof(ra.LOG_IFACE), ctypes.sizeof(ra.LOG_IFACE)); return True
        if cmd == 1:
            st["rot"] = ctypes.cast(data, ctypes.POINTER(ctypes.c_uint)).contents.value % 4; return True
        if cmd == ra.ENV_SET_PIXEL_FORMAT:
            st["fmt"] = ctypes.cast(data, ctypes.POINTER(ctypes.c_uint)).contents.value; return True
        if cmd in (ra.ENV_GET_SYSTEM_DIRECTORY, ra.ENV_GET_SAVE_DIRECTORY):
            ctypes.cast(data, ctypes.POINTER(ctypes.c_char_p)).contents.value = ctypes.addressof(sysdir_b); return True
        if cmd == ra.ENV_GET_VARIABLE_UPDATE:
            ctypes.cast(data, ctypes.POINTER(ctypes.c_bool)).contents.value = False; return True
        return False

    def video(data, w, h, pitch):
        st["n"] += 1
        if data and st["n"] in want:
            rgb = ra.to_rgb24(ctypes.string_at(data, pitch * h), w, h, pitch, st["fmt"])
            Image.frombytes("RGB", (w, h), rgb).save(f"{a.out}/native_f{st['n']:05d}.png")

    def audio_batch(data, frames):
        st["pcm"] += ctypes.string_at(data, frames * 4); return frames

    def inp(port, device, index, id_):
        if port or device != 1 or a.coin is None:
            return 0
        t = st["n"] / 60.0
        for c in (a.coin, a.coin + 6):
            if c <= t < c + 0.2 and id_ == J_SELECT: return 1
            if c + 1 <= t < c + 1.2 and id_ == J_START: return 1
        if a.walk and t > a.coin + 8:
            k = int((t - a.coin) * 60)
            if id_ == (J_RIGHT if (k // 120) % 2 == 0 else J_LEFT): return 1
            if id_ == J_B and k % 150 < 6: return 1
        return 0

    cbs = [ra.ENV_CB(env), ra.VIDEO_CB(video), ra.AUDIO_CB(lambda l, r: None), ra.AUDIO_BATCH_CB(audio_batch),
           ra.POLL_CB(lambda: None), ra.INPUT_CB(inp)]
    core.retro_set_environment(cbs[0]); core.retro_set_video_refresh(cbs[1]); core.retro_set_audio_sample(cbs[2])
    core.retro_set_audio_sample_batch(cbs[3]); core.retro_set_input_poll(cbs[4]); core.retro_set_input_state(cbs[5])
    core.retro_init()
    info = ra.GameInfo(os.path.abspath(a.rom).encode(), None, 0, None)
    if not core.retro_load_game(ctypes.byref(info)):
        sys.exit("core refused")
    av = ra.AVInfo(); core.retro_get_system_av_info(ctypes.byref(av))
    fps, rate = av.timing.fps, av.timing.sample_rate
    print("geometry %dx%d aspect %.4f rot %d fps %.4f rate %.2f" % (av.geometry.base_width, av.geometry.base_height,
          av.geometry.aspect_ratio, st["rot"], fps, rate))
    for _ in range(int(a.seconds * fps)):
        core.retro_run()
    with wave.open(f"{a.out}/native_audio_{int(round(rate))}hz.wav", "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(int(round(rate))); w.writeframes(bytes(st["pcm"]))
    print("frames", st["n"], "audio frames", len(st["pcm"]) // 4)


if __name__ == "__main__":
    main()
