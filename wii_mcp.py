#!/usr/bin/env python3
"""Wii MCP server.

Speaks MCP (JSON-RPC 2.0, newline-delimited) over stdio and runs on the Mac. It controls a fleet of
softmodded Wiis (garage arcade cabinets on CRTs) over Wi-Fi, hands-free - nobody touches the consoles:
- wii-agent (./agent, TCP 4300): our homebrew app on each Wii - files on sd:/usb:, screenshots, virtual buttons,
  exit / reboot / power off.
- wiiload (TCP 4299): the Homebrew Channel receives and runs a .dol/.elf; used to start the agent and to run apps.
Wiis are found by scanning the LAN; names live in devices.json ({"<console id>": {"name": ..., "ip": ...}}).
Standard library plus numpy + Pillow (screenshots).

    claude mcp add --scope user wii -- python3 /path/to/wiizard/wii_mcp.py

README.md next to this file is the guide for agents.
"""
import base64
import concurrent.futures as cf
import io
import json
import os
import socket
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import wiiagent  # noqa: E402
import wiiload  # noqa: E402

SERVER_NAME = "wii"
SERVER_VERSION = "0.2.0"
SUPPORTED_PROTOCOLS = ("2025-06-18", "2025-03-26", "2024-11-05")
import wiisite  # noqa: E402
SUBNET = wiisite.SUBNET
DEVICES = os.path.join(HERE, "devices.json")
AGENT_DOL = os.path.join(HERE, "agent", "wii-agent.dol")
AGENT_META = os.path.join(HERE, "agent", "meta.xml")
AGENT_SD_DIR = "sd:/apps/wii-agent"
AGENT_SRC = os.path.join(HERE, "agent", "source", "main.c")
# WPAD_BUTTON_* bits (wiiuse/wpad.h)
BUTTONS = {"2": 0x0001, "1": 0x0002, "B": 0x0004, "A": 0x0008, "MINUS": 0x0010, "HOME": 0x0080, "LEFT": 0x0100,
           "RIGHT": 0x0200, "DOWN": 0x0400, "UP": 0x0800, "PLUS": 0x1000}


def log(*args):
    print("[wii-mcp]", *args, file=sys.stderr, flush=True)


# ---------------------------------------------------------------- fleet

def load_devices():
    try:
        return json.load(open(DEVICES))
    except (OSError, ValueError):
        return {}


def save_devices(d):
    json.dump(d, open(DEVICES, "w"), indent=2, sort_keys=True)


def _port_open(ip, port, timeout=0.6):
    try:
        socket.create_connection((ip, port), timeout=timeout).close()
        return True
    except OSError:
        return False


HEARTBEAT_PORT = 4301


def mac_ip():
    """This Mac's address on the Wiis' LAN (the source address used to reach the subnet)."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.connect((f"{SUBNET}.1", 9))
        return s.getsockname()[0]


def listen_heartbeats(seconds=4.0):
    """{ip: "WIIAGENT <ver> <id> <ip>"} heard on UDP 4301 (agents 0.2.4+ send one every 3 s)."""
    heard = {}
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind(("", HEARTBEAT_PORT))
            end = time.time() + seconds
            while time.time() < end:
                s.settimeout(max(0.05, end - time.time()))
                try:
                    data, (ip, _) = s.recvfrom(256)
                except socket.timeout:
                    break
                if data.startswith(b"WIIAGENT"):
                    heard[ip] = data.decode(errors="replace")
    except OSError as exc:
        log(f"heartbeat listen failed: {exc}")
    return heard


def scan():
    """Every Wii on the LAN: {ip: {"agent": info-dict or None, "hbc": bool}}. Agent answers identify the console."""
    def one(i):
        ip = f"{SUBNET}.{i}"
        info = wiiagent.probe(ip, timeout=1)
        if info and info.startswith("OK"):
            return ip, {"agent": dict(kv.split("=", 1) for kv in info.split()[1:] if "=" in kv), "hbc": False}
        if _port_open(ip, wiiload.PORT, timeout=1):
            return ip, {"agent": None, "hbc": True}
        return None
    with cf.ThreadPoolExecutor(128) as ex:
        found = dict(r for r in ex.map(one, range(1, 255)) if r)
    known = [e.get("ip") for e in load_devices().values()]
    known += [ip for ip in listen_heartbeats(4) if ip not in known]
    for ip in known:                         # the Wii's power-saving Wi-Fi can miss a quick probe
        if ip and ip not in found:
            info = wiiagent.probe(ip, timeout=3)
            if info and info.startswith("OK"):
                found[ip] = {"agent": dict(kv.split("=", 1) for kv in info.split()[1:] if "=" in kv), "hbc": False}
            elif wiiload.probe(ip, timeout=3):
                found[ip] = {"agent": None, "hbc": True}
    devs, changed = load_devices(), False
    for ip, st in found.items():
        if st["agent"]:
            cid = st["agent"]["id"]
            entry = devs.setdefault(cid, {"name": f"wii{len(devs) + 1}"})
            if entry.get("ip") != ip:
                entry["ip"], changed = ip, True
            changed = changed or len(entry) == 1
    if changed:
        save_devices(devs)
    return found


def resolve(wii=None):
    """An IP for a Wii given by name, console id or IP; with none given, the only Wii on the network."""
    devs = load_devices()
    if wii:
        for cid, e in devs.items():
            if wii in (cid, e.get("name"), e.get("ip")):
                return e["ip"]
        if wii.count(".") == 3:
            return wii
        raise ValueError(f"unknown Wii {wii!r}; known: {', '.join(e['name'] for e in devs.values()) or 'none'}")
    found = scan()
    if len(found) == 1:
        return next(iter(found))
    if not found:
        raise OSError("no Wii answered on the LAN (agent TCP 4300 or Homebrew Channel TCP 4299)")
    raise ValueError("several Wiis are online; pass wii=<name>: " + ", ".join(found))


def name_of(ip):
    for cid, e in load_devices().items():
        if e.get("ip") == ip:
            return e["name"]
    return ip


def built_agent_version():
    import re
    return re.search(r'#define AGENT_VERSION "([^"]+)"', open(AGENT_SRC).read()).group(1)


def _version_tuple(info_line):
    import re
    m = re.search(r"agent=(\d+)\.(\d+)\.(\d+)", info_line or "")
    return tuple(map(int, m.groups())) if m else (0, 0, 0)


def wait_hbc(ip, seconds=30):
    end = time.time() + seconds
    while time.time() < end:
        if wiiload.probe(ip, timeout=1):
            return True
        time.sleep(1)
    return False


def wait_agent(ip, seconds=60):
    end = time.time() + seconds
    while time.time() < end:
        if wiiagent.probe(ip, timeout=1):
            return True
        time.sleep(2)
    return False


# ---------------------------------------------------------------- tools

def tool_guide():
    return open(os.path.join(HERE, "README.md")).read()


def tool_status():
    found = scan()
    if not found:
        return "No Wii found on the LAN. A Wii is only reachable while wii-agent or the Homebrew Channel is on screen."
    out = []
    for ip, st in sorted(found.items(), key=lambda kv: int(kv[0].rsplit(".", 1)[1])):
        a = st["agent"]
        if a:
            out.append(f"{name_of(ip)} {ip}: wii-agent {a['agent']}, console id {a['id']}, IOS{a['ios']}, "
                       f"sd={a['sd']} usb={a['usb']}, framebuffer {a['fb']}, up {a['uptime']}s")
        else:
            out.append(f"{ip}: Homebrew Channel (wiiload) - run `start_agent` to take control")
    return "\n".join(out)


def tool_start_agent(wii=None, install=True):
    """Push wii-agent through the Homebrew Channel, wait for it, and keep a copy on the SD card."""
    ip = resolve(wii)
    running = wiiagent.probe(ip)
    built = built_agent_version()
    if running and f"agent={built} " in running + " ":
        msg = f"wii-agent {built} was already running"
    else:
        if running and "caps=" in running and "exec" in running.split("caps=")[1]:
            # update in place: new build to SD, then the agent boots it (no Homebrew Channel needed)
            upload(ip, f"{AGENT_SD_DIR}/boot.dol", open(AGENT_DOL, "rb").read())
            with wiiagent.Agent(ip) as a:
                a.put(f"{AGENT_SD_DIR}/meta.xml", open(AGENT_META, "rb").read())
                a.put(f"{AGENT_SD_DIR}/home.txt", (mac_ip() + "\n").encode())
                a.cmd(f"EXEC {AGENT_SD_DIR}/boot.dol")
            time.sleep(3)
            if not wait_agent(ip, 90):
                raise OSError("updated wii-agent on SD and rebooted into it, but it did not answer within 90 s")
            scan()
            return f"{name_of(ip)} ({ip}): updated wii-agent to {built} in place"
        if running:                          # too old to update itself: put the new build on SD, then leave
            with wiiagent.Agent(ip) as a:
                a.cmd(f"MKDIR {AGENT_SD_DIR}")
                a.put(f"{AGENT_SD_DIR}/boot.dol", open(AGENT_DOL, "rb").read())
                a.put(f"{AGENT_SD_DIR}/meta.xml", open(AGENT_META, "rb").read())
                a.cmd("HBC")
            # the Homebrew Channel's own Wi-Fi is unreliable here; whoever comes first: HBC (we push) or the agent
            # relaunched from the SD card by hand
            end = time.time() + 600
            while time.time() < end:
                info = wiiagent.probe(ip, 1)
                if info and _version_tuple(info) >= _version_tuple(f"agent={built}"):
                    scan()
                    return f"{name_of(ip)} ({ip}): wii-agent {built} running (relaunched from SD)"
                if wiiload.probe(ip, 1):
                    break
                time.sleep(2)
            else:
                raise OSError("new wii-agent is on the SD card; waiting for it to be started from the Homebrew Channel")
        if not wiiload.probe(ip):
            raise OSError(f"{ip}: neither wii-agent nor the Homebrew Channel answers")
        wiiload.send(ip, AGENT_DOL, name="boot.dol")
        if not wait_agent(ip):
            raise OSError("sent wii-agent but it did not answer within 60 s (no network on the Wii?)")
        msg = f"started wii-agent {built}"
    scan()
    if install:
        with wiiagent.Agent(ip) as a:
            a.cmd(f"MKDIR {AGENT_SD_DIR}")
            a.put(f"{AGENT_SD_DIR}/boot.dol", open(AGENT_DOL, "rb").read())
            a.put(f"{AGENT_SD_DIR}/meta.xml", open(AGENT_META, "rb").read())
            a.put(f"{AGENT_SD_DIR}/home.txt", (mac_ip() + "\n").encode())
        msg += f"; installed to {AGENT_SD_DIR}"
    return f"{name_of(ip)} ({ip}): {msg}"


def tool_screenshot(wii=None, max_width=640):
    with wiiagent.Agent(resolve(wii)) as a:
        im = a.screenshot()
    if im.width > max_width:
        im = im.resize((max_width, round(im.height * max_width / im.width)))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=85)
    return [{"type": "image", "data": base64.b64encode(buf.getvalue()).decode(), "mimeType": "image/jpeg"}]


def tool_files_list(path="sd:/", wii=None):
    with wiiagent.Agent(resolve(wii)) as a:
        entries = a.ls(path)
    lines = [f"{'<dir>' if s is None else s:>12}  {n}" for n, s in sorted(entries, key=lambda e: (e[1] is not None, e[0].lower()))]
    return f"{path} ({len(entries)} entries)\n" + "\n".join(lines)


def tool_files_get(path, dest, wii=None):
    with wiiagent.Agent(resolve(wii), timeout=120) as a:
        data = a.get(path)
    dest = os.path.expanduser(dest)
    if os.path.isdir(dest):
        dest = os.path.join(dest, path.rsplit("/", 1)[-1])
    open(dest, "wb").write(data)
    return f"copied {len(data)} bytes to {dest}"


def upload(ip, path, data):
    """Resumable chunked upload when the agent supports it, else one PUT."""
    for attempt in range(30):                # the agent may be mid self-restart (Wi-Fi recovery)
        try:
            a = wiiagent.Agent(ip, timeout=60)
            break
        except OSError:
            time.sleep(10)
    else:
        raise OSError(f"{ip}: agent not reachable")
    with a:
        caps = a.info().get("caps", "")
        a.cmd(f"MKDIR {path.rsplit('/', 1)[0]}")
        if "putat" not in caps:
            a.put(path, data)
            return
    wiiagent.put_resumable(ip, path, data, log=log)


def tool_files_put(src, path, wii=None):
    data = open(os.path.expanduser(src), "rb").read()
    t = time.time()
    upload(resolve(wii), path, data)
    dt = time.time() - t
    return f"wrote {len(data)} bytes to {path} in {dt:.1f}s ({len(data) / max(dt, 0.01) / 1024:.0f} KB/s)"


def tool_files_delete(path, wii=None):
    if path.rstrip("/") in ("sd:", "usb:", "sd:/apps", AGENT_SD_DIR) or path.startswith(AGENT_SD_DIR + "/"):
        raise ValueError(f"refusing to delete {path}")
    with wiiagent.Agent(resolve(wii)) as a:
        a.cmd(f"RM {path}")
    return f"deleted {path}"


def tool_disk_free(device="sd:/", wii=None):
    with wiiagent.Agent(resolve(wii)) as a:
        _, free, total = a.cmd(f"DF {device}").split()
    return f"{device} {int(free) / 2**30:.2f} GiB free of {int(total) / 2**30:.2f} GiB"


def tool_press(button, ms=150, wii=None):
    bits = 0
    for b in button.upper().replace(",", "+").split("+"):
        if b.strip() not in BUTTONS:
            raise ValueError(f"unknown button {b}; use {', '.join(BUTTONS)}")
        bits |= BUTTONS[b.strip()]
    with wiiagent.Agent(resolve(wii)) as a:
        a.cmd(f"PAD {bits:x} {ms}")
    return f"pressed {button} (only seen by wii-agent / the launcher, not by games)"


def tool_run(path, args=None, wii=None):
    """Run a .dol/.elf from the Mac through the Homebrew Channel (leaves wii-agent first if it is running)."""
    ip = resolve(wii)
    if wiiagent.probe(ip):
        with wiiagent.Agent(ip) as a:
            a.cmd("HBC")
        end = time.time() + 30
        while not wiiload.probe(ip) and time.time() < end:
            time.sleep(1)
    raw, sent = wiiload.send(ip, os.path.expanduser(path), args or [])
    return f"sent {os.path.basename(path)} ({raw} bytes) to the Homebrew Channel on {name_of(ip)}"


def tool_launch(path, args=None, wii=None):
    """Boot a .dol/.elf that is on the Wii's SD/USB, with arguments (argv[0] is the path)."""
    ip = resolve(wii)
    with wiiagent.Agent(ip) as a:
        reply = a.cmd("EXEC " + "\t".join([path, *(args or [])]))
    return f"{name_of(ip)}: booting {path} ({reply[3:]}). The Wii is unreachable until that program exits."


def tool_nand_list(path="/", wii=None):
    with wiiagent.Agent(resolve(wii)) as a:
        names = a.nls(path)
    return f"NAND {path} ({len(names)} entries)\n" + "\n".join(names)


def tool_nand_get(path, dest, wii=None):
    with wiiagent.Agent(resolve(wii), timeout=60) as a:
        data = a.nget(path)
    dest = os.path.expanduser(dest)
    if os.path.isdir(dest):
        dest = os.path.join(dest, path.rsplit("/", 1)[-1])
    open(dest, "wb").write(data)
    return f"copied {len(data)} bytes from NAND {path} to {dest}"


PRII_SETTINGS = "/title/00000001/00000002/data/loader.ini"
PRII_AUTOBOOT = {"off": 0, "hbc": 1, "bootmii": 2, "system_menu": 3, "file": 4}
# Priiloader's Settings struct (src/priiloader/include/settings.h): u8 autoboot first, 32 bytes in all. Priiloader
# resets everything to defaults if the file size ever changes, so only that exact layout is edited.
PRII_SETTINGS_SIZE = 32


def tool_priiloader_autoboot(mode=None, wii=None):
    """Read (mode omitted) or set Priiloader's autoboot. The previous settings file is saved next to this script."""
    ip = resolve(wii)
    with wiiagent.Agent(ip) as a:
        try:
            data = a.nget(PRII_SETTINGS)
        except OSError as exc:
            return f"{name_of(ip)}: can't read Priiloader's settings ({exc}). Priiloader may not be installed."
        names = {v: k for k, v in PRII_AUTOBOOT.items()}
        current = data[0]
        version = int.from_bytes(data[4:8], "big") if len(data) >= 8 else 0
        if mode is None:
            return (f"{name_of(ip)}: Priiloader installed (settings version {version:#x}), "
                    f"autoboot = {names.get(current, current)}, settings {len(data)} bytes")
        if mode not in PRII_AUTOBOOT:
            raise ValueError(f"mode must be one of {', '.join(PRII_AUTOBOOT)}")
        if len(data) != PRII_SETTINGS_SIZE or data[1:4] != b"\0\0\0":
            raise OSError(f"unexpected Priiloader settings layout ({len(data)} bytes: {data[:8].hex()}); not editing")
        backups = os.path.join(HERE, "backups")
        os.makedirs(backups, exist_ok=True)
        bak = os.path.join(backups, f"{name_of(ip)}-loader.ini.{time.strftime('%Y%m%d-%H%M%S')}")
        open(bak, "wb").write(data)
        new = bytes([PRII_AUTOBOOT[mode]]) + data[1:]
        a.nput(PRII_SETTINGS, new)
        check = a.nget(PRII_SETTINGS)
    if check != new:
        raise OSError("Priiloader settings did not read back as written")
    return f"{name_of(ip)}: Priiloader autoboot {names.get(current, current)} -> {mode} (backup: {bak})"


PRII_MAIN_BIN = "/title/00000001/00000002/data/main.bin"


def tool_autoboot_agent(wii=None):
    """Make power-on boot straight into wii-agent: write the agent over Priiloader's autoboot program (main.bin) and
    set autoboot to 'file'. That NAND copy only hands off to the SD copy, so later updates never touch the NAND."""
    ip = resolve(wii)
    dol = open(AGENT_DOL, "rb").read()
    with wiiagent.Agent(ip, timeout=120) as a:
        info = a.info()
        if "nand" not in info.get("caps", ""):
            raise OSError("the running agent can't write the NAND; run start_agent first")
        old = a.nget(PRII_MAIN_BIN)
        if b"wii-agent" not in old:          # keep whatever was there before the first switch
            backups = os.path.join(HERE, "backups")
            os.makedirs(backups, exist_ok=True)
            bak = os.path.join(backups, f"{name_of(ip)}-priiloader-main.bin.{time.strftime('%Y%m%d-%H%M%S')}")
            open(bak, "wb").write(old)
        if len(dol) > len(old):
            raise OSError(f"agent ({len(dol)} bytes) is bigger than the existing main.bin ({len(old)}); "
                          "ISFS can't grow it without extra NAND permissions")
        a.nput(PRII_MAIN_BIN, dol)
        check = a.nget(PRII_MAIN_BIN)
    if check[:len(dol)] != dol:
        raise OSError("main.bin did not read back as written; autoboot left unchanged")
    result = tool_priiloader_autoboot("file", wii=wii or ip)
    return f"{name_of(ip)}: Priiloader's boot program is now wii-agent ({len(dol)} bytes, verified). {result}"


def tool_screen(width=None, height=None, x=None, y=None, wii=None):
    """CRT overscan calibration of the launcher: picture width/height in % of 640x480 and offset in pixels (+x right,
    +y down). Shows a white edge frame for 20 s so the owner can say what's cut off. No arguments: current values."""
    ip = resolve(wii)
    with wiiagent.Agent(ip) as a:
        cur = a.cmd("SCREEN").split()[1:]
        if width is not None or height is not None or x is not None or y is not None:
            new = [width if width is not None else cur[0], height if height is not None else cur[1],
                   x if x is not None else cur[2], y if y is not None else cur[3]]
        else:
            new = cur                        # re-show the markers
        cur = a.cmd("SCREEN " + " ".join(str(int(v)) for v in new)).split()[1:]
    return f"{name_of(ip)}: screen {cur[0]}% wide x {cur[1]}% tall, offset x {cur[2]} y {cur[3]} (edge markers shown 20 s)"


def tool_games(search=None, system=None, wii=None):
    """The launcher's game library (index, system, id/zip, title), optionally filtered."""
    ip = resolve(wii)
    with wiiagent.Agent(ip, timeout=60) as a:
        a.s.sendall(b"GAMES\n")
        rows = []
        while True:
            ln = a.line()
            if ln.startswith("OK") or ln.startswith("ERR"):
                break
            rows.append(ln.split("\t"))
    if system:
        rows = [r for r in rows if system.lower() in r[1].lower()]
    if search:
        rows = [r for r in rows if search.lower() in r[3].lower() or search.lower() in r[2].lower()]
    return f"{len(rows)} games\n" + "\n".join(f"{r[0]:>4}  {r[1]:<18} {r[2]:<12} {r[3]}" for r in rows[:300])


def tool_play(game, wii=None):
    """Start a game the way the launcher does (index, disc id or zip from `games`). The Wii goes off the network
    until the player quits the game (hold Start 2 s in arcade games, R+Z+Start in GameCube games)."""
    ip = resolve(wii)
    with wiiagent.Agent(ip) as a:
        reply = a.cmd(f"PLAY {game}")
    return f"{name_of(ip)}: starting {reply[3:]}; unreachable until the game is quit"


def tool_power(action, wii=None):
    cmds = {"hbc": "HBC", "wii_menu": "MENU", "reboot": "REBOOT", "off": "OFF"}
    if action not in cmds:
        raise ValueError(f"action must be one of {', '.join(cmds)}")
    ip = resolve(wii)
    with wiiagent.Agent(ip) as a:
        a.cmd(cmds[action])
    return f"{name_of(ip)}: {action} requested"


def retroarch_cmd(ip, text, wait=1.5):
    """One RetroArch network command (UDP 55355; our RetroArch build brings it up a few seconds into a game)."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.settimeout(wait)
        s.sendto(text.encode(), (ip, 55355))
        try:
            return s.recvfrom(4096)[0].decode(errors="replace").strip()
        except socket.timeout:
            return None


def tool_game(action="status", wii=None):
    """An arcade game running in RetroArch on a cabinet: status (what's playing) or quit (back to the launcher)."""
    devs = load_devices()
    ip = resolve(wii) if wii else (next(iter(devs.values()))["ip"] if len(devs) == 1 else resolve(None))
    if action == "status":
        r = retroarch_cmd(ip, "GET_STATUS")
        if r:
            return f"{name_of(ip)}: {r}"
        return f"{name_of(ip)}: " + ("in the launcher" if wiiagent.probe(ip, 2) else "no answer (a GameCube/Wii game, off, or Wi-Fi down)")
    if action == "quit":
        retroarch_cmd(ip, "QUIT", wait=0.3)
        return f"{name_of(ip)}: quit sent; the launcher comes back in ~15 s"
    raise ValueError("action must be status or quit")


def tool_rename(wii, name):
    ip = resolve(wii)
    devs = load_devices()
    for cid, e in devs.items():
        if e.get("ip") == ip:
            e["name"] = name
            save_devices(devs)
            return f"console {cid} ({ip}) is now {name!r}"
    raise ValueError(f"{wii}: run wii-agent on it first so its console id is known")


def schema(props, required=()):
    return {"type": "object", "properties": props, "required": list(required)}


WII = {"wii": {"type": "string", "description": "Wii name, console id or IP; optional when only one Wii is online"}}
TOOLS = {
    "game": (tool_game, "An arcade game running on a cabinet (our RetroArch build listens on UDP 55355): action "
                        "'status' says what's playing, 'quit' returns to the launcher. GameCube/Wii games can't be reached.",
             schema({**WII, "action": {"type": "string", "enum": ["status", "quit"]}})),
    "guide": (tool_guide, "Read the agent guide: how the Wiis are reached, SD layout, recipes, limits.", schema({})),
    "status": (tool_status, "Scan the LAN for Wiis: which run wii-agent (with console id, storage, uptime) and which sit "
                            "in the Homebrew Channel.", schema({})),
    "start_agent": (tool_start_agent, "Start (or update to the current build) wii-agent on a Wii over Wi-Fi and install "
                                      "it to sd:/apps/wii-agent. Works from the Homebrew Channel or an older agent.",
                    schema({**WII, "install": {"type": "boolean"}})),
    "screenshot": (tool_screenshot, "Capture the Wii's screen (agent/launcher only; games can't be captured).",
                   schema({**WII, "max_width": {"type": "integer"}})),
    "files_list": (tool_files_list, "List a folder on the Wii, e.g. 'sd:/apps' or 'usb:/'.",
                   schema({**WII, "path": {"type": "string"}})),
    "files_get": (tool_files_get, "Copy a file from the Wii to the Mac (dest: file or folder).",
                  schema({**WII, "path": {"type": "string"}, "dest": {"type": "string"}}, ["path", "dest"])),
    "files_put": (tool_files_put, "Copy a file from the Mac to the Wii (creates folders). Wi-Fi is slow: ~0.3-1 MB/s.",
                  schema({**WII, "src": {"type": "string"}, "path": {"type": "string"}}, ["src", "path"])),
    "files_delete": (tool_files_delete, "Delete a file or empty folder on the Wii.",
                     schema({**WII, "path": {"type": "string"}}, ["path"])),
    "disk_free": (tool_disk_free, "Free and total space on sd:/ or usb:/.",
                  schema({**WII, "device": {"type": "string"}})),
    "press": (tool_press, "Press virtual Wiimote buttons in wii-agent/the launcher: A, B, 1, 2, PLUS, MINUS, HOME, UP, "
                          "DOWN, LEFT, RIGHT; combine with '+'.",
              schema({**WII, "button": {"type": "string"}, "ms": {"type": "integer"}}, ["button"])),
    "run": (tool_run, "Run a .dol/.elf from the Mac on the Wii through the Homebrew Channel, with optional arguments.",
            schema({**WII, "path": {"type": "string"}, "args": {"type": "array", "items": {"type": "string"}}}, ["path"])),
    "launch": (tool_launch, "Boot a .dol/.elf already on the Wii (e.g. 'sd:/apps/wiiflow/boot.dol') with optional "
                            "arguments. The Wii is unreachable until that program exits.",
               schema({**WII, "path": {"type": "string"}, "args": {"type": "array", "items": {"type": "string"}}}, ["path"])),
    "nand_list": (tool_nand_list, "List a folder on the Wii's internal NAND (read-only), e.g. '/title/00000001'.",
                  schema({**WII, "path": {"type": "string"}})),
    "nand_get": (tool_nand_get, "Copy a NAND file to the Mac (read-only).",
                 schema({**WII, "path": {"type": "string"}, "dest": {"type": "string"}}, ["path", "dest"])),
    "priiloader_autoboot": (tool_priiloader_autoboot, "Read Priiloader's autoboot setting, or set it: off, hbc, bootmii, "
                                                      "system_menu, file. Backs up the settings first.",
                            schema({**WII, "mode": {"type": "string"}})),
    "autoboot_agent": (tool_autoboot_agent, "Make power-on boot straight into wii-agent (Priiloader autoboot file). "
                                            "Backs up the previous boot program; later agent updates only touch SD.",
                       schema({**WII})),
    "screen": (tool_screen, "CRT overscan calibration for the launcher: width/height (60-110 %), x/y offset in pixels. "
                            "Shows edge markers for 20 s; ask the owner which edges are cut off. No args: show current.",
               schema({**WII, "width": {"type": "integer"}, "height": {"type": "integer"}, "x": {"type": "integer"},
                       "y": {"type": "integer"}})),
    "games": (tool_games, "List the launcher's games (GameCube, Wii, Neo Geo, CPS-1); filter by search text or system.",
              schema({**WII, "search": {"type": "string"}, "system": {"type": "string"}})),
    "play": (tool_play, "Start a game on a Wii like the launcher would (index, disc id or zip from `games`).",
             schema({**WII, "game": {"type": "string"}}, ["game"])),
    "power": (tool_power, "action: hbc (exit to Homebrew Channel), wii_menu, reboot or off.",
              schema({**WII, "action": {"type": "string"}}, ["action"])),
    "rename": (tool_rename, "Give a Wii a friendly name (e.g. cab1) in devices.json.",
               schema({"wii": {"type": "string"}, "name": {"type": "string"}}, ["wii", "name"])),
}


def call_tool(name, args):
    if name not in TOOLS:
        return {"content": [{"type": "text", "text": f"unknown tool {name}"}], "isError": True}
    try:
        result = TOOLS[name][0](**(args or {}))
    except TypeError as exc:
        return {"content": [{"type": "text", "text": f"bad arguments: {exc}"}], "isError": True}
    except Exception as exc:
        log(f"{name} failed: {exc!r}")
        return {"content": [{"type": "text", "text": f"{type(exc).__name__}: {exc}"}], "isError": True}
    if isinstance(result, list):
        return {"content": result, "isError": False}
    return {"content": [{"type": "text", "text": str(result)}], "isError": False}


INSTRUCTIONS = """\
Control of the owner's softmodded Wiis (garage arcade cabinets on CRTs) over Wi-Fi. Hands-free: the owner does not
want to touch the consoles or their menus, so never ask them to press buttons on a Wii; do it through these tools.
- Start with `status`. A Wii in the Homebrew Channel needs `start_agent`; then `screenshot`, files_*, press, power.
- Only wii-agent/the launcher can be seen or controlled; once a game runs, the Wii is unreachable until it exits.
- Never delete sd:/apps/wii-agent, sd:/apps/homebrew_browser-style system apps, or anything outside sd:/ and usb:/.
- Don't take the Wiis online to Nintendo services or install system updates. Call `guide` for recipes.
"""


def send(msg):
    sys.stdout.write(json.dumps(msg, separators=(",", ":")) + "\n")
    sys.stdout.flush()


def handle(msg):
    method, mid = msg.get("method"), msg.get("id")
    if mid is None:
        return
    params = msg.get("params") or {}
    if method == "initialize":
        requested = params.get("protocolVersion")
        result = {"protocolVersion": requested if requested in SUPPORTED_PROTOCOLS else SUPPORTED_PROTOCOLS[0],
                  "capabilities": {"tools": {}},
                  "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
                  "instructions": INSTRUCTIONS}
    elif method == "ping":
        result = {}
    elif method == "tools/list":
        result = {"tools": [{"name": n, "description": d, "inputSchema": s} for n, (_, d, s) in TOOLS.items()]}
    elif method == "tools/call":
        result = call_tool(params.get("name"), params.get("arguments"))
    else:
        send({"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"method not found: {method}"}})
        return
    send({"jsonrpc": "2.0", "id": mid, "result": result})


def main():
    log(f"{SERVER_NAME} {SERVER_VERSION} ready")
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            send({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "parse error"}})
            continue
        try:
            handle(msg)
        except Exception as exc:
            log(f"internal error: {exc!r}")
            if msg.get("id") is not None:
                send({"jsonrpc": "2.0", "id": msg["id"], "error": {"code": -32603, "message": str(exc)}})


if __name__ == "__main__":
    main()
