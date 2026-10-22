#!/usr/bin/env python3
"""A/V test of one game in the Dolphin simulator (slots 7/8 only), with a RetroArch config variant.
Boots our launcher on slotN.raw, PLAYs the game, optionally coins/starts/walks with a pipe GC pad, dumps
lossless frames (FFV1) and the DSP audio (what the Wii's AI plays), and saves PNGs at chosen emulated seconds,
the audio after PLAYING, and the RetroArch log into ~/wii-sim/avfix/out/<tag>/.
    avrun.py <slot 7|8> <spec.json>
spec: {"tag","rom","core_dir" (override folder, e.g. "FB Alpha 2012"), "secs", "coin" (s or null), "walk",
       "shots": [s,...], "base": {key: value} (retroarch.cfg), "game": {key: value} (game override, merged over the
       published one), "core": {key: value} (core override <core_dir>/<core_dir>.cfg)}"""
import glob, json, os, shutil, socket, subprocess, sys, time, threading
HOME = os.path.expanduser("~/wii-sim"); DIST = os.path.expanduser("~/wii-fleet/dist/files")
OUT = f"{HOME}/avfix/out"
PAD = """[GCPad1]
Device = Pipe/0/pad
Buttons/A = `Button A`
Buttons/B = `Button B`
Buttons/X = `Button X`
Buttons/Y = `Button Y`
Buttons/Z = `Button Z`
Buttons/Start = `Button START`
D-Pad/Up = `Button D_UP`
D-Pad/Down = `Button D_DOWN`
D-Pad/Left = `Button D_LEFT`
D-Pad/Right = `Button D_RIGHT`
Triggers/L = `Button L`
Triggers/R = `Button R`
"""
LOGCFG = {"log_verbosity": "true", "log_to_file": "true", "log_to_file_timestamp": "false",
          "log_dir": "sd:/retroarch/logs", "frontend_log_level": "1", "libretro_log_level": "1"}


def sh(c):
    return subprocess.run(c, shell=True, capture_output=True, text=True)


def cfg_parse(text):
    d = {}
    for l in text.splitlines():
        if "=" in l and not l.lstrip().startswith("#"):
            k, v = l.split("=", 1); d[k.strip()] = v.strip().strip('"')
    return d


def cfg_text(d):
    return "".join(f'{k} = "{v}"\n' for k, v in d.items())


def cmd(port, line, timeout=5):
    with socket.create_connection(("127.0.0.1", port), timeout=timeout) as s:
        s.sendall(line.encode() + b"\n"); return s.makefile("rb").readline().decode(errors="replace").strip()


def ra_status(port):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s.settimeout(2)
    try:
        s.sendto(b"GET_STATUS", ("127.0.0.1", port)); return s.recv(512).decode(errors="replace").strip()
    except OSError:
        return None
    finally:
        s.close()


def npk(p):
    r = sh(f"ffprobe -v error -count_packets -show_entries stream=nb_read_packets -of csv=p=0 '{p}'").stdout.strip()
    try: return int(r.splitlines()[0])
    except (ValueError, IndexError): return 0


def main():
    slot = int(sys.argv[1]); spec = json.load(open(sys.argv[2]))
    assert slot in (7, 8)
    tag, rom = spec["tag"], spec["rom"]
    od = f"{OUT}/{tag}"; shutil.rmtree(od, ignore_errors=True); os.makedirs(od)
    json.dump(spec, open(f"{od}/spec.json", "w"), indent=1)
    user = f"{HOME}/userav{slot}"
    if not os.path.exists(user):
        shutil.copytree(f"{HOME}/user{slot}", user, symlinks=True, ignore=shutil.ignore_patterns("Dump"))
    open(f"{user}/Config/GCPadNew.ini", "w").write(PAD)
    os.makedirs(f"{user}/Pipes", exist_ok=True)
    if not os.path.exists(f"{user}/Pipes/pad"): os.mkfifo(f"{user}/Pipes/pad")
    shutil.rmtree(f"{user}/Dump", ignore_errors=True); os.makedirs(f"{user}/Dump/Frames"); os.makedirs(f"{user}/Dump/Audio")
    # config files for this run
    base = cfg_parse(open(f"{DIST}/apps/retroarch-wii/retroarch.cfg").read()); base.update(LOGCFG); base.update(spec.get("base", {}))
    stage = f"{od}/stage"; os.makedirs(stage)
    open(f"{stage}/retroarch.cfg", "w").write(cfg_text(base))
    cd = spec["core_dir"]; stem = rom.rsplit(".", 1)[0]
    pub_game = f"{DIST}/retroarch/config/{cd}/{stem}.cfg"
    game = cfg_parse(open(pub_game).read()) if os.path.exists(pub_game) else {}
    game.update(spec.get("game", {}))
    core = spec.get("core", {})
    mt = f"docker run --rm -u $(id -u):$(id -g) -e MTOOLS_SKIP_CHECK=1 -v {HOME}:/sim wii-sim"
    img = f"/sim/slot{slot}.raw"; rel = os.path.relpath(stage, HOME)
    cmds = [f"mcopy -o -i {img} /sim/{rel}/retroarch.cfg ::/apps/retroarch-wii/retroarch.cfg",
            f"mdel -i {img} ::/retroarch/logs/retroarch.log",
            f"mmd -i {img} '::/retroarch/config/{cd}'",
            f"mdel -i {img} '::/retroarch/config/{cd}/{stem}.cfg'",
            f"mdel -i {img} '::/retroarch/config/{cd}/{cd}.cfg'"]
    if game:
        open(f"{stage}/game.cfg", "w").write(cfg_text(game))
        cmds.append(f"mcopy -o -i {img} /sim/{rel}/game.cfg '::/retroarch/config/{cd}/{stem}.cfg'")
    pub_core = f"{DIST}/retroarch/config/{cd}/{cd}.cfg"
    if os.path.exists(pub_core):
        c0 = cfg_parse(open(pub_core).read()); c0.update(core); core = c0
    if core:
        open(f"{stage}/core.cfg", "w").write(cfg_text(core))
        cmds.append(f"mcopy -o -i {img} /sim/{rel}/core.cfg '::/retroarch/config/{cd}/{cd}.cfg'")
    for c in spec.get("extra_files", []):            # [local path under ~/wii-sim, card path]
        cmds.append(f"mcopy -o -i {img} /sim/{c[0]} '{c[1]}'")
    for c in spec.get("del_files", []):
        cmds.append(f"mdel -i {img} '{c}'")
    r = sh(f"{mt} sh -c \"" + "; ".join(x.replace('"', '\\"') for x in cmds) + "\"")
    name, port, uport = f"av{slot}", 4330 + slot, 55370 + slot
    sh(f"docker rm -f {name}")
    sh(f"docker run -d --name {name} -p {port}:4300 -p {uport}:55355/udp --shm-size=1g -u $(id -u):$(id -g) -e HOME=/sim "
       f"-v {HOME}:/sim wii-sim /usr/games/dolphin-emu-nogui -p headless -u /sim/userav{slot} -v OGL "
       f"-C Dolphin.Core.WiiSDCardEnableFolderSync=False -C Dolphin.General.WiiSDCardPath=/sim/slot{slot}.raw "
       f"-C SYSCONF.IPL.AR=False -C Dolphin.DSP.DumpAudio=True -C Dolphin.DSP.DumpAudioSilent=True "
       + (("-C Dolphin.Movie.DumpFrames=True -C Dolphin.Movie.DumpFramesSilent=True "
           + (f"-C Graphics.Settings.DumpCodec={spec.get('codec', 'ffv1')} " if spec.get('codec', 'ffv1') else ""))
          if spec.get("frames", True) else "") + " ".join(f"-C {x}" for x in spec.get("dolphin",
          ["Graphics.Settings.InternalResolutionFrameDumps=True", "Graphics.Settings.AspectRatio=6"])) + f" -e /sim/{spec.get('dol', 'wii-agent.dol')}")
    info = {"tag": tag}
    t, played = time.time(), None
    while time.time() - t < 400:
        try:
            played = cmd(port, f"PLAY {rom}")
            if played.startswith("OK"): break
        except OSError: pass
        time.sleep(3)
    info["play"] = played
    if not played or not played.startswith("OK"):
        sh(f"docker rm -f {name}"); info["verdict"] = "launcher-not-ready"; print(json.dumps(info)); return
    t, st = time.time(), None
    while time.time() - t < 300:
        st = ra_status(uport)
        if st and "PLAYING" in st: break
        time.sleep(2)
    info["status"] = st
    time.sleep(2)
    fa = sorted(glob.glob(f"{user}/Dump/Audio/*dspdump*.wav"), key=os.path.getmtime)
    apath = fa[-1]; a0 = os.path.getsize(apath)
    favi = sorted(glob.glob(f"{user}/Dump/Frames/*.avi"), key=os.path.getctime)
    vbase = {p: npk(p) for p in favi}
    def emu(): return (os.path.getsize(apath) - a0) / 4 / 32000.0
    fd = os.open(f"{user}/Pipes/pad", os.O_WRONLY | os.O_NONBLOCK) if spec.get("coin") is not None else None
    def press(btn, hold=0.4):
        os.write(fd, f"PRESS {btn}\n".encode()); time.sleep(hold); os.write(fd, f"RELEASE {btn}\n".encode())
    events, coin, t0 = [], spec.get("coin"), time.time()
    todo = [(coin, "Z"), (coin + 1.5, "START"), (coin + 6, "Z"), (coin + 7.5, "START")] if coin is not None else []
    walk_next = (coin + 10) if (coin is not None and spec.get("walk")) else None
    wdir = 0
    while time.time() - t0 < 3000:
        e = emu()
        if todo and e >= todo[0][0]:
            _, b = todo.pop(0); press(b, 1.0); events.append(f"{b}@{e:.1f}")
        if walk_next is not None and e >= walk_next:
            b = ("D_RIGHT", "D_LEFT")[wdir % 2]; wdir += 1
            os.write(fd, f"PRESS {b}\n".encode()); time.sleep(4); os.write(fd, f"RELEASE {b}\n".encode())
            press("A", 0.5); press("B", 0.5); events.append(f"walk {b}+jump@{e:.1f}")
            walk_next = e + 4
        if e >= spec["secs"]: break
        time.sleep(0.5)
    info["events"] = events; info["emu_secs"] = round(emu(), 1); info["wall"] = round(time.time() - t0)
    info["status_end"] = ra_status(uport)
    sh(f"docker stop -t 20 {name}"); sh(f"docker rm -f {name}")
    # audio after PLAYING
    raw = open(apath, "rb").read()
    start = 44 + a0 - 44; start -= start % 4
    hdr = bytearray(raw[:44]); body = raw[start:]
    import struct
    struct.pack_into("<I", hdr, 4, 36 + len(body)); struct.pack_into("<I", hdr, 40, len(body))
    open(f"{od}/audio.wav", "wb").write(bytes(hdr) + body)
    info["audio_rate"] = struct.unpack("<I", raw[24:28])[0]
    # frames: emulated second s after PLAYING -> frame index (base + s * fps_dump)
    favi = sorted(glob.glob(f"{user}/Dump/Frames/*.avi"), key=os.path.getctime)
    files = [(p, vbase.get(p, 0), npk(p)) for p in favi]
    total = sum(n - b for p, b, n in files)
    info["frames_after_play"] = total
    fps = total / max(1e-6, info["emu_secs"])
    info["dump_fps"] = round(fps, 3)
    for s in spec.get("shots", []):
        g = int(s * fps); acc = 0
        for p, b, n in files:
            if g < acc + (n - b):
                k = b + (g - acc)
                sh(f"ffmpeg -v error -i '{p}' -vf \"select='eq(n\\,{k})'\" -vsync 0 -frames:v 1 '{od}/s{int(s*10):04d}.png'")
                break
            acc += n - b
    # frame pacing after PLAYING: intervals between dumped frames (a 33 ms gap = a frame the VI never showed)
    gaps = {}
    for p, b, n in files:
        pts = sh(f"ffprobe -v error -select_streams v -show_entries packet=pts_time -of csv=p=0 '{p}'").stdout.split()
        t = [float(x) for x in pts[b:] if x.replace('.', '', 1).isdigit()]
        for x, y in zip(t, t[1:]):
            k = str(round((y - x) * 1000 / 16.7)); gaps[k] = gaps.get(k, 0) + 1
    info["frame_gaps_in_fields"] = gaps
    if spec.get("keep_avi"):
        for p, b, n in files: shutil.copy(p, od)
    log = sh(f"{mt} mtype -i {img} ::/retroarch/logs/retroarch.log").stdout
    open(f"{od}/retroarch.log", "w").write(log)
    json.dump(info, open(f"{od}/info.json", "w"), indent=1)
    print(json.dumps(info), flush=True)


if __name__ == "__main__":
    main()
