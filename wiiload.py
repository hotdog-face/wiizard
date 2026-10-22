"""wiiload client: send a .dol/.elf to the Homebrew Channel (TCP 4299) and run it with arguments.
Protocol 0.5 (HBC 1.0.5+): "HAXX", version 0.5, u16 args length, u32 compressed size, u32 uncompressed size,
the zlib-compressed file, then the NUL-separated argument list (file name first).
  wiiload.py <host> <file> [args...]"""
import os
import socket
import sys
import zlib

PORT = 4299


def probe(ip, timeout=2.0):
    try:
        socket.create_connection((ip, PORT), timeout=timeout).close()
        return True
    except OSError:
        return False


def send(host, path, args=(), name=None, timeout=60):
    data = open(path, "rb").read()
    packed = zlib.compress(data, 6)
    argv = b"".join(a.encode() + b"\0" for a in [name or os.path.basename(path), *args])
    with socket.create_connection((host, PORT), timeout=timeout) as s:
        s.sendall(b"HAXX" + bytes([0, 5]) + len(argv).to_bytes(2, "big")
                  + len(packed).to_bytes(4, "big") + len(data).to_bytes(4, "big"))
        s.sendall(packed)
        s.sendall(argv)
    return len(data), len(packed)


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    raw, sent = send(sys.argv[1], sys.argv[2], sys.argv[3:])
    print(f"sent {sent} bytes ({raw} uncompressed)")
