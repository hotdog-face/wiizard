# Mitchell's blue wizard holding a Wii Remote, drawn in his flat style (no outline, two-tone flat shading, rounded),
# gripped in his right mitt with his four-point sparkles at the tip. Drawn at 4x, downsampled.
import os, math
from PIL import Image, ImageDraw
HERE = os.path.dirname(os.path.abspath(__file__))
S = 4


def sparkle(d, cx, cy, r, col):
    pts = []
    for i in range(8):
        rr = r if i % 2 == 0 else r * 0.28
        a = math.radians(-90 + i * 45)
        pts.append(((cx + rr * math.cos(a)) * S, (cy + rr * math.sin(a)) * S))
    d.polygon(pts, fill=col)


def build(src="wiz1.png", out="wiz1-remote.png", hand=(126, 254), hand_r=10, tilt=20, length=78):
    base = Image.open(os.path.join(HERE, src)).convert("RGBA")
    pad_top, pad_r = 70, 60
    W, H = base.width + pad_r, base.height + pad_top
    big = Image.new("RGBA", (W * S, H * S))
    big.alpha_composite(base.resize((base.width * S, base.height * S), Image.LANCZOS), (0, pad_top * S))
    hx, hy = hand[0], hand[1] + pad_top
    hand_col = base.getpixel(hand)
    # the remote, drawn upright then rotated about its grip
    rw, rl = 20, length
    rem = Image.new("RGBA", (rw * S, rl * S))
    rd = ImageDraw.Draw(rem)
    rd.rounded_rectangle([0, 0, rw * S - 1, rl * S - 1], 6 * S, fill=(250, 250, 252))
    rd.rounded_rectangle([rw * S * 0.55, 0, rw * S - 1, rl * S - 1], 6 * S, fill=(226, 230, 238))      # his flat shade band
    rd.rectangle([rw * S * 0.55, 2 * S, rw * S * 0.62, (rl - 2) * S], fill=(226, 230, 238))
    rd.rounded_rectangle([2 * S, 0, (rw - 2) * S, 4 * S], 2 * S, fill=(40, 44, 56))                       # IR window
    cx = rw * S / 2
    rd.rectangle([cx - 2 * S, 9 * S, cx + 2 * S, 21 * S], fill=(78, 82, 96))                               # D-pad
    rd.rectangle([cx - 6 * S, 13 * S, cx + 6 * S, 17 * S], fill=(78, 82, 96))
    rd.ellipse([cx - 4.5 * S, 27 * S, cx + 4.5 * S, 36 * S], fill=(200, 205, 216))                         # A
    for y in (52, 59):
        rd.ellipse([cx - 2 * S, y * S, cx + 2 * S, (y + 4) * S], fill=(200, 205, 216))                     # 1, 2
    for i in range(4):
        rd.rectangle([(4.5 + i * 3.4) * S, (rl - 7) * S, (6.3 + i * 3.4) * S, (rl - 5.4) * S], fill=(80, 170, 255))
    rem = rem.rotate(-tilt, expand=True, resample=Image.BICUBIC)
    # place so the lower fifth of the remote sits in the hand
    ang = math.radians(tilt)
    grip = (-math.sin(ang) * rl * 0.36, math.cos(ang) * rl * 0.36)         # from the remote's centre down to the grip
    cxp, cyp = hx - grip[0], hy - grip[1]
    big.alpha_composite(rem, (int(cxp * S - rem.width / 2), int(cyp * S - rem.height / 2)))
    d = ImageDraw.Draw(big)
    d.ellipse([(hx - hand_r) * S, (hy - hand_r) * S, (hx + hand_r) * S, (hy + hand_r) * S], fill=hand_col)  # mitt over it
    tip = (cxp + math.sin(ang) * rl * 0.55, cyp - math.cos(ang) * rl * 0.55)
    for dx, dy, r in ((12, -12, 9), (26, 2, 6), (0, -24, 5), (24, -24, 4)):
        sparkle(d, tip[0] + dx, tip[1] + dy, r, (255, 255, 255))
    out_im = big.resize((W, H), Image.LANCZOS)
    out_im = out_im.crop(out_im.getbbox())
    out_im.save(os.path.join(HERE, out))
    return out_im


if __name__ == "__main__":
    im = build()
    s = Image.new("RGBA", (im.width * 2 + 20, im.height * 2 + 20), (255, 170, 205, 255))
    s.alpha_composite(im.resize((im.width * 2, im.height * 2), Image.LANCZOS), (10, 10))
    s.convert("RGB").save("/tmp/claude-501/w1r.jpg")
    print(im.size)
