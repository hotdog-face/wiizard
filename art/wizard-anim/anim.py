# WIIZARD intro animation from Mitchell's own wizard (Desktop/wizards/wizards (1).psd, group "0", his 2017 art).
# His layers are composited with psd-tools into parts (body without eyes/brows/sparkles, eyes, brows, his sparkles),
# then puppeted: pop-in with squash and stretch, blink, the Wii Remote flicked up like a wand with a sparkle burst,
# brows up, a wink, and an idle bob that loops. Nothing is redrawn except the remote (in his flat style) and the
# closed-eye lines.
#   python3 anim.py            -> frames/NNNN.png (RGBA), anim.json, preview.mp4 (on the collage background)
import os, math, json, shutil, subprocess
from PIL import Image, ImageDraw
from psd_tools import PSDImage

HERE = os.path.dirname(os.path.abspath(__file__))
PSD = os.path.expanduser("~/Desktop/wizards/wizards (1).psd")
BOX = (2080, 320, 2310, 650)                       # his blue wizard on the PSD canvas
FPS = 30
K = 1.22                                            # native px -> output px (he is ~330 px tall natively)
CW, CH = 360, 500                                  # output canvas (feet anchored bottom-centre)
SPARK = {"Shape 3 copy", "Shape 3 copy 2", "Shape 3 copy 4", "Shape 3 copy 3"}
BROWS = {"Rounded Rectangle 9 copy", "Rounded Rectangle 9 copy 2"}
EYE_L, EYE_R = (84, 174), (101, 174)               # eye centres, native px relative to BOX
HAND_R, HAND_RAD = (138.5, 270.5), 8.5
FEET_Y, MID_X = 313, 115


# ---------------------------------------------------------------- his parts
def parts():
    psd = PSDImage.open(PSD)
    g0 = [l for l in psd if l.name == "0" and l.is_group()][0]

    def comp(exclude=set(), only=None, exclude_groups=set(), only_groups=None):
        def f(layer):
            if layer.name in exclude:
                return False
            chain, p = [], layer.parent
            while p is not None and hasattr(p, "name"):
                chain.append(p.name)
                p = p.parent
            if any(n in exclude_groups for n in chain):
                return False
            if only_groups is not None and layer.kind != "group" and not any(n in only_groups for n in chain):
                return False
            if only is not None and layer.kind != "group" and layer.name not in only:
                return False
            return layer.is_visible()
        return g0.composite(viewport=BOX, layer_filter=f).convert("RGBA")

    return dict(body=comp(SPARK | BROWS | {"Shadow"}, exclude_groups={"Group 3"}),
                eyes=comp(only_groups={"Group 3"}), brows=comp(only=BROWS))


# ---------------------------------------------------------------- the remote, in his flat style (drawn at 4x)
def remote(length=78, width=20):
    S = 4
    im = Image.new("RGBA", (width * S, length * S))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([0, 0, width * S - 1, length * S - 1], 6 * S, fill=(250, 250, 252))
    d.rounded_rectangle([width * S * 0.55, 0, width * S - 1, length * S - 1], 6 * S, fill=(226, 230, 238))
    d.rectangle([width * S * 0.55, 2 * S, width * S * 0.62, (length - 2) * S], fill=(226, 230, 238))
    d.rounded_rectangle([2 * S, 0, (width - 2) * S, 4 * S], 2 * S, fill=(40, 44, 56))
    cx = width * S / 2
    d.rectangle([cx - 2 * S, 9 * S, cx + 2 * S, 21 * S], fill=(78, 82, 96))
    d.rectangle([cx - 6 * S, 13 * S, cx + 6 * S, 17 * S], fill=(78, 82, 96))
    d.ellipse([cx - 4.5 * S, 27 * S, cx + 4.5 * S, 36 * S], fill=(200, 205, 216))
    for y in (52, 59):
        d.ellipse([cx - 2 * S, y * S, cx + 2 * S, (y + 4) * S], fill=(200, 205, 216))
    for i in range(4):
        d.rectangle([(4.5 + i * 3.4) * S, (length - 7) * S, (6.3 + i * 3.4) * S, (length - 5.4) * S], fill=(80, 170, 255))
    return im.resize((width, length), Image.LANCZOS)


def sparkle(d, cx, cy, r, alpha=255):
    pts = []
    for i in range(8):
        rr = r if i % 2 == 0 else r * 0.28
        a = math.radians(-90 + i * 45)
        pts.append((cx + rr * math.cos(a), cy + rr * math.sin(a)))
    d.polygon(pts, fill=(255, 255, 255, alpha))


# ---------------------------------------------------------------- timing helpers
def ease_out_back(t, s=1.7):
    t -= 1
    return t * t * ((s + 1) * t + s) + 1


def smooth(t):
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)


def window(t, a, b):
    return smooth((t - a) / (b - a)) if b > a else float(t >= a)


# ---------------------------------------------------------------- one frame
def frame(P, rem, t, hand_col):
    # 1. the character in native px: body, eyes (open / blink / wink), brows (lifted), remote (flick), mitt
    W0, H0 = P["body"].size
    ch = Image.new("RGBA", (W0 + 80, H0 + 60))
    ox, oy = 0, 60                                 # room above for the raised remote and sparkles
    ch.alpha_composite(P["body"], (ox, oy))
    blink = 0.9 < t < 1.02 or 3.35 < t < 3.47
    wink = 2.55 < t < 2.95
    d = ImageDraw.Draw(ch)
    ink = (30, 24, 40, 255)
    if blink:
        for ex, ey in (EYE_L, EYE_R):
            d.rounded_rectangle([ox + ex - 6, oy + ey - 1, ox + ex + 6, oy + ey + 2], 2, fill=ink)
    else:
        eyes = P["eyes"]
        if wink:                                   # keep his left eye open, close the right one in a happy arc
            left = eyes.crop((0, 0, int((EYE_L[0] + EYE_R[0]) / 2), eyes.height))
            ch.alpha_composite(left, (ox, oy))
            ex, ey = EYE_R
            d.arc([ox + ex - 7, oy + ey - 5, ox + ex + 7, oy + ey + 6], 200, 340, fill=ink, width=3)
        else:
            ch.alpha_composite(eyes, (ox, oy))
    lift = -5 * window(t, 1.75, 1.95) * (1 - window(t, 3.0, 3.3)) - (2 if wink else 0)
    ch.alpha_composite(P["brows"], (ox, int(oy + lift)))
    # remote: held down-forward, anticipation dip, then flicked up; settles with a little overshoot, then sways
    if t < 1.3:                                    # degrees from straight up, clockwise (90 = pointing right)
        ang = 120 + 8 * window(t, 1.1, 1.3)
    elif t < 1.7:
        ang = 128 - 113 * ease_out_back((t - 1.3) / 0.4, 2.2)
    else:
        ang = 15 + 6 * math.sin((t - 1.7) * 2.4)
    hx, hy = ox + HAND_R[0], oy + HAND_R[1]
    r = rem.rotate(-ang, expand=True, resample=Image.BICUBIC)
    a = math.radians(ang)
    tipdir = (math.sin(a), -math.cos(a))
    cx, cy = hx + tipdir[0] * 0.3 * rem.height, hy + tipdir[1] * 0.3 * rem.height   # gripped a fifth up from its end
    ch.alpha_composite(r, (int(cx - r.width / 2), int(cy - r.height / 2)))
    d = ImageDraw.Draw(ch)
    d.ellipse([hx - HAND_RAD, hy - HAND_RAD, hx + HAND_RAD, hy + HAND_RAD], fill=hand_col)
    tip = (hx + tipdir[0] * rem.height * 0.85, hy + tipdir[1] * rem.height * 0.85)
    # sparkles: a burst from the tip at the flick, then a slow twinkle around it
    if t >= 1.55:
        b = t - 1.55
        for k in range(7):
            ang_k = math.radians(-160 + k * 26)
            dist = 8 + 46 * smooth(b / 0.5)
            fade = 1 - smooth((b - 0.5) / 0.4) if b < 0.9 else 0
            if fade > 0:
                sparkle(d, tip[0] + math.cos(ang_k) * dist, tip[1] + math.sin(ang_k) * dist, 5 + 4 * (1 - b), int(255 * fade))
        for k, (dx, dy, rr, ph) in enumerate(((14, -12, 8, 0.0), (28, 4, 5, 1.3), (0, -26, 5, 2.1), (24, -28, 4, 0.7))):
            if b > 0.4:
                tw = 0.55 + 0.45 * math.sin(t * 5 + ph)
                sparkle(d, tip[0] + dx, tip[1] + dy, rr * tw, 255)
    # 2. whole-body motion in output px: pop-in with squash and stretch, then an idle bob
    if t < 0.55:
        p = t / 0.55
        s = ease_out_back(p, 2.4)
        sx, sy = s * (1 + 0.12 * math.sin(p * math.pi)), s * (1 - 0.1 * math.sin(p * math.pi))
        dy = 0
    else:
        bob = math.sin((t - 0.55) * 3.2)
        sx, sy = 1 - 0.015 * bob, 1 + 0.015 * bob
        dy = 0
        if 1.3 < t < 1.7:                          # little hop with the flick
            dy = -10 * math.sin((t - 1.3) / 0.4 * math.pi)
    out = Image.new("RGBA", (CW, CH))
    if sx < 0.02 or sy < 0.02:
        return out
    w, h = int(ch.width * K * sx), int(ch.height * K * sy)
    big = ch.resize((max(1, w), max(1, h)), Image.LANCZOS)
    fx = int(CW / 2 - (ox + MID_X) * K * sx)
    fy = int(CH - 10 - (oy + FEET_Y) * K * sy + dy)
    # a soft contact shadow, his style (flat translucent pill)
    sd = ImageDraw.Draw(out)
    sw = 64 * K * sx * (1 + dy / 60)
    sd.rounded_rectangle([CW / 2 - sw / 2, CH - 16, CW / 2 + sw / 2, CH - 4], 6, fill=(60, 30, 60, 70))
    out.alpha_composite(big, (fx, fy))
    return out


def main():
    P = parts()
    rem = remote()
    hand_col = P["body"].getpixel((int(HAND_R[0]), int(HAND_R[1])))
    fd = os.path.join(HERE, "frames")
    shutil.rmtree(fd, ignore_errors=True)
    os.makedirs(fd)
    total = 4.2
    n = int(total * FPS)
    for i in range(n):
        frame(P, rem, i / FPS, hand_col).save(os.path.join(fd, f"{i:04d}.png"))
    loop_from = int(2.2 * FPS)
    json.dump({"fps": FPS, "frames": n, "size": [CW, CH], "loop_from": loop_from, "anchor": "bottom-centre",
               "notes": "pop-in 0-0.55 s, blink 0.9 s, remote flick + sparkle burst 1.3-2.2 s, brows up, wink 2.55 s, "
                        "frames from loop_from onward loop (idle bob, twinkle, blink at 3.35 s)"},
              open(os.path.join(HERE, "anim.json"), "w"), indent=1)
    # preview on the collage background, CRT-ish, as an mp4
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(HERE), "mockups"))
    from render_short import kit10, background
    from render20 import star
    bg = background(kit10())
    star(ImageDraw.Draw(bg), 470, 250, 190, (255, 228, 0), 16, .78)
    pv = os.path.join(HERE, "preview")
    shutil.rmtree(pv, ignore_errors=True)
    os.makedirs(pv)
    for i in range(n + 2 * FPS):
        j = i if i < n else loop_from + (i - n) % (n - loop_from)
        f = Image.open(os.path.join(fd, f"{j:04d}.png"))
        im = bg.copy()
        im.paste(f, (470 - CW // 2, 468 - CH), f)
        im.convert("RGB").resize((1280, 960), Image.BICUBIC).save(os.path.join(pv, f"{i:04d}.jpg"), quality=88)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(FPS), "-i", os.path.join(pv, "%04d.jpg"),
                    "-pix_fmt", "yuv420p", "-vf", "scale=960:720", os.path.join(HERE, "preview.mp4")], check=True)
    print(n, "frames; loop from", loop_from)


if __name__ == "__main__":
    main()
