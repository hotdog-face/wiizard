#!/usr/bin/env python3
"""Build d2x cIOS 249 from a base IOS copied off the console's own NAND (nandgrab.py), the way the d2x cIOS installer
does it (its patchmii.c / libios.c addModule / title.c), into a folder the launcher's CIOSINSTALL installs from:
tik, tmd (both fakesigned) and <index>.app per content, encrypted with the title key.

    build_cios.py <nand copy dir> <d2x release dir (ciosmaps.xml + d2x-vXX/*.app)> <base ios> <slot> <out dir>

cab1's IOSes are all one version newer than d2x's ciosmaps (Nintendo's last IOS update): those differ from the mapped
versions only in content 0 (the 64-byte version block, which d2x's patches rewrite completely) and the Wi-Fi driver
(WL, untouched by d2x). So a base is accepted when every other content id matches the map, and every patch site
except content 0's still holds the map's original bytes.
"""
import hashlib, os, re, struct, sys
from Crypto.Cipher import AES

NAND, REL, BASE, SLOT, OUT = sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4]), sys.argv[5]
# The Wii common key is not in this repo: put it in WII_COMMON_KEY (32 hex digits), or in the first 16 bytes of a
# common-key.bin next to this script (e.g. from your own console's keys.bin / OTP dump).
_KEYFILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "common-key.bin")
if os.environ.get("WII_COMMON_KEY"):
    COMMON_KEY = bytes.fromhex(os.environ["WII_COMMON_KEY"])
elif os.path.exists(_KEYFILE):
    COMMON_KEY = open(_KEYFILE, "rb").read()[:16]
else:
    sys.exit("build_cios.py needs the Wii common key: set WII_COMMON_KEY or provide cios/common-key.bin")
assert len(COMMON_KEY) == 16 and hashlib.sha1(COMMON_KEY).hexdigest().startswith("ebeae6d2"), "that isn't the Wii common key"
SIG = 0x140                                  # RSA-2048 signature header of tickets and TMDs


def nand(p):
    return open(os.path.join(NAND, p.lstrip("/")), "rb").read()


# ---- the map
xml = re.sub(r"<!--.*?-->", "", open(os.path.join(REL, "ciosmaps.xml")).read(), flags=re.S)
group = re.search(r'<ciosgroup name="([^"]+)" version="(\d+)"', xml)
GROUP, CIOS_VERSION = group.group(1), int(group.group(2))
base = re.search(r'<base ios="%d" version="(\d+)".*?</base>' % BASE, xml, re.S)
MAP_VERSION = int(base.group(1))
entries = []
for m in re.finditer(r'<content id="(0x[0-9a-fA-F]+)"([^>]*?)(/>|>(.*?)</content>)', base.group(0), re.S):
    attrs, body = m.group(2), m.group(4) or ""
    mod = re.search(r'module="(\w+)"', attrs)
    if mod:
        entries.append(dict(module=mod.group(1), tmdid=int(re.search(r'tmdmoduleid="(-?\d+)"', attrs).group(1))))
    else:
        patches = []
        for p in re.finditer(r'<patch offset="(0x[0-9a-fA-F]+)" size="(\d+)"\s+originalbytes="([^"]+)"\s+newbytes="([^"]+)"', body):
            patches.append((int(p.group(1), 16), int(p.group(2)), bytes(int(b, 16) for b in p.group(3).split(",")),
                            bytes(int(b, 16) for b in p.group(4).split(","))))
        entries.append(dict(cid=int(m.group(1), 16), patches=patches))
base_entries = [e for e in entries if "cid" in e]
modules = [e for e in entries if "module" in e]
print(f"{GROUP} (TMD version {CIOS_VERSION}): base IOS{BASE} v{MAP_VERSION}, {len(base_entries)} contents, "
      f"{len(modules)} modules")

# ---- the base, from the console
tmd_raw = nand(f"/title/00000001/{BASE:08x}/content/title.tmd")
h = SIG
access, tver, ncont, boot = struct.unpack(">IHHH", tmd_raw[h + 0x98:h + 0xa2])
contents = []
for i in range(ncont):
    o = h + 0xa4 + 36 * i
    cid, idx, typ, size = struct.unpack(">IHHQ", tmd_raw[o:o + 16])
    contents.append(dict(cid=cid, index=idx, type=typ, size=size, hash=tmd_raw[o + 16:o + 36]))
cmap = nand("/shared1/content.map")
shared = {cmap[i + 8:i + 28]: cmap[i:i + 8].decode() for i in range(0, len(cmap), 28)}
print(f"console IOS{BASE} v{tver}: {ncont} contents, boot index {boot}")
assert tver in (MAP_VERSION, MAP_VERSION + 1), f"IOS{BASE} v{tver} is neither v{MAP_VERSION} nor v{MAP_VERSION + 1}"
assert ncont == len(base_entries), "content count differs from the map"

data = []
for i, (c, e) in enumerate(zip(contents, base_entries)):
    path = f"/shared1/{shared[c['hash']]}.app" if c["type"] & 0x8000 else \
        f"/title/00000001/{BASE:08x}/content/{c['cid']:08x}.app"
    d = bytearray(nand(path)[:c["size"]])
    assert hashlib.sha1(d).digest() == c["hash"], f"content {i} hash"
    if c["cid"] != e["cid"]:
        # the newer IOS: only the version block and the WL (Wi-Fi) driver may differ
        is_wl = b"/dev/wl" in d and b"/dev/es" not in d and b"/dev/fs\0" not in d
        assert i == 0 or (is_wl and not e["patches"]), f"content {i}: cid {c['cid']:#x} vs map {e['cid']:#x}"
        print(f"  content {i}: console cid {c['cid']:#x}, map {e['cid']:#x} ({'version block' if i == 0 else 'WL driver'})")
    for off, size, orig, new in e["patches"]:
        assert len(orig) == size and len(new) == size
        if i != 0:                           # content 0 is rewritten whole, whatever version string it had
            assert bytes(d[off:off + size]) == orig, f"content {i} patch at {off:#x}: original bytes differ"
        d[off:off + size] = new
    if e["patches"]:
        if i == 0:
            covered = sorted((off, off + size) for off, size, _, _ in e["patches"])
            assert covered[0][0] == 0 and covered[-1][1] == len(d) and all(a[1] == b[0] for a, b in zip(covered, covered[1:]))
        c["hash"] = hashlib.sha1(d).digest()
        if c["type"] == 0x8001:
            c["type"] = 1
        print(f"  content {i} cid {c['cid']:#x}: {len(e['patches'])} patches")
    data.append(bytes(d))

# ---- modules (addModule): new content ids after the highest, appended, or taking a TMD slot (whose old entry moves
# to the end)
free_cid = max(c["cid"] for c in contents)
mod_dir = os.path.join(REL, GROUP)
for e in modules:
    free_cid += 1
    raw = open(os.path.join(mod_dir, e["module"] + ".app"), "rb").read()
    padded = raw + b"\0" * (((len(raw) + 31) & ~31) - len(raw))
    n = len(contents)
    entry = dict(cid=free_cid, index=n, type=1, size=len(padded), hash=hashlib.sha1(padded).digest())
    if 0 <= e["tmdid"] < n:
        contents.append(contents[e["tmdid"]])
        data.append(data[e["tmdid"]])
        contents[e["tmdid"]] = entry
        data[e["tmdid"]] = padded
        where = f"TMD slot {e['tmdid']} (old entry moved to {n})"
    else:
        contents.append(entry)
        data.append(padded)
        where = f"appended at {n}"
    print(f"  {e['module']}: {len(raw)} bytes as cid {free_cid:#x}, index {n}, {where}")

# ---- TMD: new title id, d2x version, the new content list, fakesigned
tid = (1 << 32) | SLOT
body = bytearray(tmd_raw[h:h + 0xa4])
struct.pack_into(">Q", body, 0x4c, tid)
struct.pack_into(">HHH", body, 0x9c, CIOS_VERSION, len(contents), boot)
for c in contents:
    body += struct.pack(">IHHQ", c["cid"], c["index"], c["type"], c["size"]) + c["hash"]


def fakesign(sig, payload, fill_off):
    sig = sig[:4] + b"\0" * (len(sig) - 4)
    for fill in range(65536):
        struct.pack_into(">H", payload, fill_off, fill)
        if hashlib.sha1(payload).digest()[0] == 0:
            return sig + bytes(payload)
    raise SystemExit("couldn't fakesign")


tmd_out = fakesign(tmd_raw[:h], body, 0xa2)

# ---- ticket: the base's, moved to the new title id (title key re-encrypted for it), fakesigned
tik_raw = nand(f"/ticket/00000001/{BASE:08x}.tik")
tik = bytearray(tik_raw[h:])
old_tid = tik[0x9c:0xa4]
assert struct.unpack(">Q", old_tid)[0] == (1 << 32) | BASE and tik[0xb1] == 0, "ticket title id / common key index"
title_key = AES.new(COMMON_KEY, AES.MODE_CBC, bytes(old_tid) + b"\0" * 8).decrypt(bytes(tik[0x7f:0x8f]))
tik[0x9c:0xa4] = struct.pack(">Q", tid)
tik[0x7f:0x8f] = AES.new(COMMON_KEY, AES.MODE_CBC, struct.pack(">Q", tid) + b"\0" * 8).encrypt(title_key)
tik_out = fakesign(tik_raw[:h], tik, 0x122)

# ---- write: contents encrypted with the title key, IV = content index
os.makedirs(OUT, exist_ok=True)
for f in os.listdir(OUT):
    os.remove(os.path.join(OUT, f))
open(os.path.join(OUT, "tmd"), "wb").write(tmd_out)
open(os.path.join(OUT, "tik"), "wb").write(tik_out)
for c, d in zip(contents, data):
    plain = d + b"\0" * (-len(d) % 16)
    enc = AES.new(title_key, AES.MODE_CBC, struct.pack(">H", c["index"]) + b"\0" * 14).encrypt(plain)
    assert AES.new(title_key, AES.MODE_CBC, struct.pack(">H", c["index"]) + b"\0" * 14).decrypt(enc)[:c["size"]] == d[:c["size"]]
    assert hashlib.sha1(d[:c["size"]]).digest() == c["hash"]
    open(os.path.join(OUT, f"{c['index']}.app"), "wb").write(enc)
print(f"wrote {OUT}: tmd {len(tmd_out)} bytes, tik {len(tik_out)} bytes, {len(contents)} contents, "
      f"title {tid:016x} v{CIOS_VERSION}")
