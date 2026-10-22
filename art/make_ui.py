# The launcher's "Maximal collage" look (art direction 10, after Studio Moross): the static pictures it draws under
# everything, pre-rendered here with anti-aliasing (the Wii's GX draws polygons without it), plus Mitchell's wizard
# animation packed for streaming. Spec: art/mockups/render20.py s10 (menu) and render_short.py kit10 (attract/loading).
#   python3 art/make_ui.py   -> sdkit/ui/bg.png, band.png, wizard.wza (installed as sd:/arcade/ui/)
# wizard.wza: "WZA1", u16 w, u16 h, u16 fps*100, u16 loop_from, u32 frames, u32 offset[frames + 1], then each frame
# as zlib-compressed GX RGB5A3 4x4-tiled texels (inflated straight into a texture on the Wii, no re-tiling).
import os, math, json, struct, zlib
from PIL import Image, ImageDraw, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(os.path.dirname(HERE), "sdkit", "ui")
ANIM = os.path.join(HERE, "wizard-anim")
W, H = 640, 480
YEL, PNK, BLU, K = (255, 228, 0), (255, 60, 140), (40, 80, 255), (10, 10, 10)
PAPER, DOT = (255, 170, 205), (255, 140, 190)
SS = 4                                               # supersampling for smooth edges


def star(d, cx, cy, r, col, k, inner, rot=-90):
    pts = []
    for a in range(k * 2):
        rr = r if a % 2 == 0 else r * inner
        ang = math.radians(rot + a * 180 / k)
        pts.append((cx + rr * math.cos(ang), cy + rr * math.sin(ang)))
    d.polygon(pts, fill=col)


def big(fn, size=(W, H), mode="RGB", bg=PAPER):
    """Draw at SS x with a scaled ImageDraw, return the downsampled image."""
    im = Image.new(mode, (size[0] * SS, size[1] * SS), bg)
    d = ImageDraw.Draw(im)
    class D:                                          # coordinates in 1x units
        def polygon(self, pts, fill): d.polygon([(x * SS, y * SS) for x, y in pts], fill=fill)
        def ellipse(self, box, fill): d.ellipse([c * SS for c in box], fill=fill)
    fn(D())
    return im.resize(size, Image.LANCZOS)


def menu_bg():
    def f(d):
        for y in range(0, H + 12, 12):
            for x in range(0, W + 12, 12):
                r = 3 + 2 * math.sin((x + y) / 60)
                d.ellipse([x - r, y - r, x + r, y + r], fill=DOT)
        d.polygon([(0, 0), (260, 0), (180, 120), (0, 160)], fill=BLU)
        d.polygon([(460, 260), (W, 220), (W, 400), (520, 420)], fill=YEL)
        star(d, 560, 70, 46, YEL, 12, .7)
        star(d, 80, 440, 34, BLU, 10, .6)
    return big(f)


def attract_band():
    """The slanted pink lower third (kit10 attract), y 340..480 of the screen, transparent above the slant."""
    top = 340
    def f(d):
        d.polygon([(0, 372 - top), (W, 350 - top), (W, H - top), (0, H - top)], fill=PNK + (255,))
    band = big(f, (W, H - top), "RGBA", (0, 0, 0, 0))
    dots = Image.new("RGBA", band.size, (0, 0, 0, 0))
    dd = ImageDraw.Draw(dots)
    for x in range(0, W, 14):
        for y in range(360 - top, H - top, 14):
            dd.ellipse([x, y, x + 4, y + 4], fill=(255, 120, 180, 255))
    mask = band.split()[3]
    dots.putalpha(Image.composite(dots.split()[3], Image.new("L", band.size, 0), mask.point(lambda v: 255 if v > 250 else 0)))
    return Image.alpha_composite(band, dots)


def rgb5a3_tiled(im):
    w, h = im.size
    px = im.load()
    out = bytearray()
    for by in range(0, h, 4):
        for bx in range(0, w, 4):
            for y in range(by, by + 4):
                for x in range(bx, bx + 4):
                    r, g, b, a = px[x, y]
                    if a >= 0xE0:
                        v = 0x8000 | (r >> 3) << 10 | (g >> 3) << 5 | (b >> 3)
                    else:
                        v = (a >> 5) << 12 | (r >> 4) << 8 | (g >> 4) << 4 | (b >> 4)
                    out += struct.pack(">H", v)
    return bytes(out)


def wizard():
    meta = json.load(open(os.path.join(ANIM, "anim.json")))
    names = sorted(f for f in os.listdir(os.path.join(ANIM, "frames")) if f.endswith(".png"))
    frames = []
    for n in names:                                    # a white die-cut sticker edge around him (collage look)
        im = Image.open(os.path.join(ANIM, "frames", n)).convert("RGBA")
        mask = im.split()[3].point(lambda v: 255 if v > 40 else 0)
        # only around his body (the part connected to his robe): sparkles and the ground shadow stay free
        px = mask.load()
        seed = next(((x, 400) for x in range(150, 260) if px[x, 400] == 255), None)
        if seed:
            ImageDraw.floodfill(mask, seed, 128)
            mask = mask.point(lambda v: 255 if v == 128 else 0)
        edge = mask.filter(ImageFilter.MaxFilter(11)).filter(ImageFilter.GaussianBlur(0.7))
        base = Image.new("RGBA", im.size, (255, 255, 255, 0)); base.putalpha(edge)
        frames.append(Image.alpha_composite(base, im))
    box = None
    for im in frames:
        b = im.getbbox()
        box = b if box is None else (min(box[0], b[0]), min(box[1], b[1]), max(box[2], b[2]), max(box[3], b[3]))
    x0, y0 = box[0] & ~3, box[1] & ~3
    w, h = (box[2] - x0 + 3) & ~3, (box[3] - y0 + 3) & ~3
    blobs = [zlib.compress(rgb5a3_tiled(im.crop((x0, y0, x0 + w, y0 + h))), 6) for im in frames]
    head = b"WZA1" + struct.pack(">HHHHI", w, h, int(meta["fps"] * 100), meta.get("loop_from", 0), len(blobs))
    offs, pos = [], len(head) + 4 * (len(blobs) + 1)
    for bl in blobs:
        offs.append(pos); pos += len(bl)
    offs.append(pos)
    with open(os.path.join(OUT, "wizard.wza"), "wb") as f:
        f.write(head + struct.pack(">%dI" % len(offs), *offs) + b"".join(blobs))
    # where the crop sits in his 360x500 canvas (feet anchored bottom-centre): the launcher places the crop itself
    print("wizard.wza", w, "x", h, "crop at", x0, y0, "of", meta["size"], len(blobs), "frames", pos // 1024, "KB")


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    menu_bg().save(os.path.join(OUT, "bg.png"), optimize=True)
    attract_band().save(os.path.join(OUT, "band.png"), optimize=True)
    wizard()
    for f in sorted(os.listdir(OUT)):
        print(f, os.path.getsize(os.path.join(OUT, f)) // 1024, "KB")
