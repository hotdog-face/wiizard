"""Client for wii-agent (the homebrew app in ./agent, TCP 4300). One short connection per call.
  wiiagent.py <host> info | ls <path> | get <remote> <local> | put <local> <remote> | shot <out.png> | <raw command>"""
import socket
import sys
import time

PORT = 4300


def probe(ip, timeout=2.0):
    try:
        with socket.create_connection((ip, PORT), timeout=timeout) as s:
            s.settimeout(2)
            s.sendall(b"INFO\n")
            return s.makefile("rb").readline().decode(errors="replace").strip()
    except OSError:
        return None


class Agent:
    def __init__(self, host, timeout=20):
        self.host = host
        self.s = socket.create_connection((host, PORT), timeout=timeout)
        self.f = self.s.makefile("rb")

    def close(self):
        try:
            self.s.sendall(b"QUIT\n")
        except OSError:
            pass
        self.s.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def line(self):
        ln = self.f.readline()
        if not ln:
            raise OSError("wii-agent closed the connection")
        return ln.decode(errors="replace").rstrip("\r\n")

    def cmd(self, text):
        self.s.sendall(text.encode() + b"\n")
        reply = self.line()
        if reply.startswith("ERR"):
            raise OSError(f"{text.split()[0]}: {reply[4:]}")
        return reply

    def info(self):
        reply = self.cmd("INFO")
        return dict(kv.split("=", 1) for kv in reply.split()[1:] if "=" in kv)

    def ls(self, path):
        self.s.sendall(f"LS {path}\n".encode())
        out = []
        while True:
            ln = self.line()
            if ln.startswith("OK"):
                return out
            if ln.startswith("ERR"):
                raise OSError(f"LS {path}: {ln[4:]}")
            if ln.startswith("D "):
                out.append((ln[2:], None))
            else:
                _, size, name = ln.split(" ", 2)
                out.append((name, int(size)))

    def get(self, path):
        size = int(self.cmd(f"GET {path}").split()[1])
        buf = bytearray()
        while len(buf) < size:
            chunk = self.f.read(min(65536, size - len(buf)))
            if not chunk:
                raise OSError("connection lost during GET")
            buf += chunk
        return bytes(buf)

    def log(self):
        """The agent's recent log from RAM (0.8.0+: LOG)."""
        self.s.sendall(b"LOG\n")
        out = []
        while True:
            ln = self.line()
            if ln.startswith("OK"):
                return "\n".join(out)
            if ln.startswith("ERR"):
                raise OSError(f"LOG: {ln[4:]}")
            out.append(ln)

    def nls(self, path):
        self.s.sendall(f"NLS {path}\n".encode())
        out = []
        while True:
            ln = self.line()
            if ln.startswith("OK"):
                return out
            if ln.startswith("ERR"):
                raise OSError(f"NLS {path}: {ln[4:]}")
            out.append(ln[2:])

    def nget(self, path):
        size = int(self.cmd(f"NGET {path}").split()[1])
        return self.f.read(size)

    def nput(self, path, data):
        self.s.sendall(f"NPUT {len(data)} {path}\n".encode())
        self.s.sendall(data)
        reply = self.line()
        if not reply.startswith("OK"):
            raise OSError(f"NPUT {path}: {reply}")

    def put(self, path, data):
        self.s.sendall(f"PUT {len(data)} {path}\n".encode())
        self.s.sendall(data)
        reply = self.line()
        if not reply.startswith("OK"):
            raise OSError(f"PUT {path}: {reply}")

    def screenshot(self):
        """The Wii's external framebuffer as a PIL image (YUYV 4:2:2 -> RGB, BT.601)."""
        import numpy as np
        from PIL import Image
        _, w, h, n = self.cmd("SHOT").split()
        w, h, n = int(w), int(h), int(n)
        raw = bytearray()
        while len(raw) < n:
            chunk = self.f.read(n - len(raw))
            if not chunk:
                raise OSError("connection lost during SHOT")
            raw += chunk
        px = np.frombuffer(bytes(raw), np.uint8).reshape(h, w // 2, 4).astype(np.float32)
        y = np.empty((h, w), np.float32)
        y[:, 0::2], y[:, 1::2] = px[..., 0], px[..., 2]
        cb = np.repeat(px[..., 1], 2, axis=1) - 128
        cr = np.repeat(px[..., 3], 2, axis=1) - 128
        y = (y - 16) * 1.164
        rgb = np.stack([y + 1.596 * cr, y - 0.392 * cb - 0.813 * cr, y + 2.017 * cb], -1)
        return Image.fromarray(np.clip(rgb, 0, 255).astype(np.uint8), "RGB")


def put_resumable(host, path, data, chunk=128 * 1024, deadline=1200, log=print):
    """Upload in chunks into <path>.part and COMMIT at the end (agents with caps=putat). Survives Wi-Fi drops and
    agent restarts: each reconnect asks how much of the .part arrived and continues from there."""
    end = time.time() + deadline
    first = True
    while time.time() < end:
        try:
            with Agent(host, timeout=30) as a:
                off = 0
                if not first:
                    try:
                        off = min(int(a.cmd(f"STAT {path}.part").split()[1]), len(data))
                    except OSError:
                        off = 0
                first = False
                while off < len(data):
                    piece = data[off:off + chunk]
                    a.s.sendall(f"PUTAT {off} {len(piece)} {path}\n".encode() + piece)
                    reply = a.line()
                    if not reply.startswith("OK"):
                        raise OSError(f"PUTAT: {reply}")
                    off += len(piece)
                a.cmd(f"COMMIT {len(data)} {path}")
                return len(data)
        except OSError as exc:
            if log:
                log(f"upload of {path} interrupted ({exc}); resuming")
            time.sleep(5)
    raise OSError(f"could not upload {path} within {deadline} s")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    host, op, rest = sys.argv[1], sys.argv[2], sys.argv[3:]
    with Agent(host) as a:
        if op == "info":
            print(a.info())
        elif op == "ls":
            for name, size in a.ls(rest[0]):
                print(f"{'<dir>' if size is None else size:>12}  {name}")
        elif op == "get":
            open(rest[1], "wb").write(a.get(rest[0]))
        elif op == "put":
            a.put(rest[1], open(rest[0], "rb").read())
        elif op == "shot":
            a.screenshot().save(rest[0])
        else:
            print(a.cmd(" ".join([op, *rest])))
