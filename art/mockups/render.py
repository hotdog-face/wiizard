# Mock WIIZARD menu frames (640x480, as the CRT shows them) in three BUCK-inspired styles.
import os, random, math
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageOps
HERE = os.path.dirname(os.path.abspath(__file__))
STILLS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "../../videos/stills")   # game stills (not in the repo)
SUP = "/System/Library/Fonts/Supplemental/"
def F(name, size, idx=0):
    p = name if name.startswith("/") else SUP + name
    return ImageFont.truetype(p, size, index=idx)
W, H = 640, 480

def vgrad(img, stops):
    d = ImageDraw.Draw(img)
    for y in range(H):
        t = y / (H - 1)
        for i in range(len(stops) - 1):
            (t0, c0), (t1, c1) = stops[i], stops[i + 1]
            if t0 <= t <= t1:
                k = (t - t0) / (t1 - t0)
                d.line([(0, y), (W, y)], fill=tuple(int(c0[j] + (c1[j] - c0[j]) * k) for j in range(3)))
                break

def crt(img, name):
    img = img.filter(ImageFilter.GaussianBlur(0.55))
    sl = Image.new("L", (W, H), 255)
    ds = ImageDraw.Draw(sl)
    for y in range(1, H, 2):
        ds.line([(0, y), (W, y)], fill=200)
    img = Image.composite(img, Image.new("RGB", (W, H), 0), sl)
    img.resize((W * 2, H * 2), Image.BICUBIC).save(os.path.join(HERE, name), quality=92)

def still(name, size):
    im = Image.open(os.path.join(STILLS, name)).convert("RGB")
    return ImageOps.fit(im, size)

def text_c(d, xy, s, font, fill, anchor="mm"):
    d.text(xy, s, font=font, fill=fill, anchor=anchor)

# ---- A: Neon low-poly (Spark Arena Byte)
random.seed(4)
a = Image.new("RGB", (W, H)); vgrad(a, [(0, (40, 10, 90)), (0.45, (190, 30, 170)), (0.62, (255, 120, 90)), (0.66, (255, 210, 80)), (1, (255, 210, 80))])
d = ImageDraw.Draw(a)
pts = [(x, 300 + random.randint(-55, 25)) for x in range(-40, W + 80, 60)]
for i in range(len(pts) - 1):
    (x0, y0), (x1, y1) = pts[i], pts[i + 1]
    mx, my = (x0 + x1) / 2 + random.randint(-15, 15), y0 + random.randint(40, 90)
    for tri, sh in (([(x0, y0), (x1, y1), (mx, my)], 0), ([(x0, y0), (mx, my), (x0 - 10, H)], 1), ([(x1, y1), (mx, my), (x1 + 10, H)], 2), ([(mx, my), (x0 - 10, H), (x1 + 10, H)], 3)):
        base = [(30, 200, 210), (20, 120, 170), (40, 60, 140), (25, 30, 90)][sh]
        j = random.randint(-18, 18)
        d.polygon(tri, fill=tuple(max(0, min(255, c + j)) for c in base))
for _ in range(14):
    x, y, s = random.randint(0, W), random.randint(20, 220), random.randint(6, 16)
    d.polygon([(x, y), (x + s, y + s // 2), (x + s // 3, y + s)], fill=(255, 230, 90) if random.random() < .5 else (90, 240, 255))
fr = [(300, 70), (612, 52), (600, 262), (316, 280)]
d.polygon([(p[0] + 8, p[1] + 10) for p in fr], fill=(20, 10, 60))
st = still("mslug.jpg", (300, 210)); mask = Image.new("L", (W, H), 0); ImageDraw.Draw(mask).polygon(fr, fill=255)
tmp = Image.new("RGB", (W, H)); tmp.paste(st.resize((300, 230)), (308, 52)); a.paste(tmp, (0, 0), mask)
d.line(fr + [fr[0]], fill=(90, 240, 255), width=4)
text_c(d, (36, 34), "WIIZARD", F("Futura.ttc", 30, 4), (255, 255, 255), "lm")
d.polygon([(36, 60), (130, 60), (124, 74), (30, 74)], fill=(255, 220, 70)); text_c(d, (78, 67), "NEO GEO", F("Arial Black.ttf", 11), (60, 10, 80))
for dx, col in ((5, (255, 220, 70)), (0, (255, 255, 255))):
    d.text((36 + dx, 300 + dx), "METAL", font=F("Impact.ttf", 74), fill=col if dx else (255, 255, 255)) if False else None
d.text((41, 305), "METAL SLUG", font=F("Impact.ttf", 64), fill=(255, 220, 70)); d.text((36, 300), "METAL SLUG", font=F("Impact.ttf", 64), fill=(255, 255, 255))
d.polygon([(36, 392), (250, 392), (240, 424), (26, 424)], fill=(20, 10, 60)); text_c(d, (133, 408), "PRESS A TO PLAY", F("Futura.ttc", 18, 4), (90, 240, 255))
text_c(d, (604, 450), "1-2P  RUN & GUN", F("Futura.ttc", 14, 4), (40, 10, 70), "rm")
crt(a, "A-neon-lowpoly.jpg")

# ---- B: Toybox (Cartoonito Beepers)
b = Image.new("RGB", (W, H), (255, 190, 215)); d = ImageDraw.Draw(b)
d.ellipse([-120, 260, 360, 640], fill=(255, 160, 200)); d.ellipse([380, -160, 820, 220], fill=(200, 175, 255))
def blob(cx, cy, r, col, eyes=True):
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=col)
    if eyes:
        for ex in (-r * .35, r * .35):
            d.ellipse([cx + ex - r * .28, cy - r * .35, cx + ex + r * .28, cy + r * .2], fill=(255, 255, 255))
            d.ellipse([cx + ex - r * .1, cy - r * .15, cx + ex + r * .14, cy + r * .1], fill=(30, 30, 60))
for i, col in enumerate([(255, 90, 120), (255, 200, 60), (90, 200, 120), (80, 150, 255)]):
    d.rounded_rectangle([40, 360 - i * 34, 150, 392 - i * 34], 16, fill=col)
blob(95, 205, 42, (120, 90, 255))
blob(590, 440, 40, (255, 120, 60)); blob(612, 360, 22, (90, 210, 200))
d.rounded_rectangle([206, 96, 594, 346], 28, fill=(60, 40, 120)); d.rounded_rectangle([196, 84, 584, 334], 28, fill=(255, 255, 255))
st = still("dkong.jpg", (360, 226)); m = Image.new("L", st.size, 0); ImageDraw.Draw(m).rounded_rectangle([0, 0, 359, 225], 20, fill=255); b.paste(st, (210, 98), m)
x = 196
for ch, col, rot in zip("DONKEY KONG", [(255, 80, 110), (255, 170, 40), (60, 180, 110), (70, 130, 255)] * 3, [-6, 4, -3, 7, -5, 0, 5, -4, 6, -2, 3]):
    if ch == " ": x += 16; continue
    g = Image.new("RGBA", (60, 70)); gd = ImageDraw.Draw(g); gd.text((30, 35), ch, font=F("Arial Rounded Bold.ttf", 46), fill=col, anchor="mm")
    sh = Image.new("RGBA", (60, 70)); ImageDraw.Draw(sh).text((32, 38), ch, font=F("Arial Rounded Bold.ttf", 46), fill=(60, 40, 120), anchor="mm")
    b.paste(sh.rotate(rot), (x, 352), sh.rotate(rot)); b.paste(g.rotate(rot), (x, 350), g.rotate(rot)); x += 36
d.rounded_rectangle([206, 420, 430, 456], 18, fill=(60, 40, 120)); text_c(d, (318, 438), "PRESS A TO PLAY!", F("Arial Rounded Bold.ttf", 18), (255, 230, 90))
text_c(d, (30, 38), "wiizard", F("Arial Rounded Bold.ttf", 34), (60, 40, 120), "lm")
d.rounded_rectangle([440, 22, 610, 54], 16, fill=(255, 255, 255)); text_c(d, (525, 38), "ARCADE CLASSICS", F("Arial Rounded Bold.ttf", 13), (255, 80, 110))
crt(b, "B-toybox.jpg")

# ---- C: Kinetic poster (VALORANT Champions / Adobe MAX)
c = Image.new("RGB", (W, H), (226, 38, 44)); d = ImageDraw.Draw(c)
big = F("DIN Condensed Bold.ttf", 150)
layer = Image.new("RGBA", (W * 2, H * 2)); ld = ImageDraw.Draw(layer)
for r in range(6):
    ld.text((-60 + (r % 2) * 120, r * 128), "PLAY PLAY PLAY PLAY", font=big, fill=(150, 15, 25))
layer = layer.rotate(-12, resample=Image.BICUBIC); c.paste(layer, (-300, -260), layer)
st = ImageOps.grayscale(still("hsf2.jpg", (330, 250))); st = ImageOps.colorize(st, (25, 10, 15), (250, 236, 214))
d.rectangle([286, 66, 626, 326], fill=(25, 10, 15)); c.paste(st, (296, 56))
d.text((24, 300), "STREET", font=F("DIN Condensed Bold.ttf", 96), fill=(250, 236, 214))
d.text((24, 372), "FIGHTER II", font=F("DIN Condensed Bold.ttf", 96), fill=(25, 10, 15))
d.rectangle([24, 22, 196, 52], fill=(25, 10, 15)); text_c(d, (110, 38), "WIIZARD ARCADE", F("DIN Condensed Bold.ttf", 22), (250, 236, 214))
text_c(d, (616, 360), "CPS-2", F("DIN Condensed Bold.ttf", 30), (250, 236, 214), "rm")
text_c(d, (616, 395), "1-2P / FIGHTING", F("DIN Condensed Bold.ttf", 22), (25, 10, 15), "rm")
d.rectangle([420, 420, 616, 456], fill=(250, 236, 214)); text_c(d, (518, 438), "PRESS A TO PLAY", F("DIN Condensed Bold.ttf", 22), (226, 38, 44))
crt(c, "C-kinetic-poster.jpg")
print("ok")
