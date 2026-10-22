# Style C ("kinetic poster", after BUCK's VALORANT Champions / Adobe MAX work) explored on WIIZARD's real screens:
# the main menu (card carousel, category pills, bottom bar, clock), full-screen attract, and the intro with the wizard.
# 640x480 as the CRT shows it, then a light blur + scanlines and 2x for viewing.
import os, math
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageOps

HERE = os.path.dirname(os.path.abspath(__file__))
STILLS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "../../videos/stills")   # game stills (not in the repo)
SUP = "/System/Library/Fonts/Supplemental/"
W, H = 640, 480


def F(name, size, idx=0):
    return ImageFont.truetype(SUP + name, size, index=idx)


DIN = lambda s: F("DIN Condensed Bold.ttf", s)
FUT = lambda s: F("Futura.ttc", s, 4)        # Futura Condensed ExtraBold
NAR = lambda s: F("Arial Narrow Bold.ttf", s)


def crt(img, name):
    img = img.convert("RGB").filter(ImageFilter.GaussianBlur(0.55))
    sl = Image.new("L", (W, H), 255)
    ds = ImageDraw.Draw(sl)
    for y in range(1, H, 2):
        ds.line([(0, y), (W, y)], fill=205)
    img = Image.composite(img, Image.new("RGB", (W, H), 0), sl)
    img.resize((W * 2, H * 2), Image.BICUBIC).save(os.path.join(HERE, name), quality=92)


def still(name, size, duo=None):
    im = ImageOps.fit(Image.open(os.path.join(STILLS, name)).convert("RGB"), size)
    if duo:
        im = ImageOps.colorize(ImageOps.autocontrast(ImageOps.grayscale(im)), duo[0], duo[1])
    return im


def tiled(img, word, font, col, angle, step_y, shift=0):
    lay = Image.new("RGBA", (W * 3, H * 3))
    d = ImageDraw.Draw(lay)
    line = (word + " ") * 12
    for r in range(0, H * 3 // step_y + 1):
        d.text((-(r * 90 + shift) % 400 - 400, r * step_y), line, font=font, fill=col)
    lay = lay.rotate(angle, resample=Image.BICUBIC)
    img.paste(lay, (-W, -H), lay)


def text_w(d, s, font):
    return d.textlength(s, font=font)


def fit_font(d, s, maker, start, maxw):
    sz = start
    while sz > 10 and text_w(d, s, maker(sz)) > maxw:
        sz -= 2
    return maker(sz)


def button(d, x, y, letter, label, box, ink, lab):
    d.rectangle([x, y, x + 26, y + 26], fill=box)
    d.text((x + 13, y + 14), letter, font=DIN(22), fill=ink, anchor="mm")
    d.text((x + 34, y + 14), label, font=DIN(22), fill=lab, anchor="lm")
    return 34 + text_w(d, label, DIN(22)) + 18


def clock(d, x, y, col, bars=3):
    for b in range(3):
        h = 6 + b * 4
        d.rectangle([x - 70 + b * 7, y + 14 - h, x - 66 + b * 7, y + 14], fill=col if b < bars else None, outline=col)
    d.text((x, y + 8), "7:42", font=DIN(24), fill=col, anchor="rm")


def heart(d, cx, cy, s, col):
    d.ellipse([cx - s, cy - s * .7, cx, cy + s * .3], fill=col)
    d.ellipse([cx, cy - s * .7, cx + s, cy + s * .3], fill=col)
    d.polygon([(cx - s * .95, cy - s * .05), (cx + s * .95, cy - s * .05), (cx, cy + s)], fill=col)


def carousel(img, d, games, pal, center_y=178, card_w=262, gap=232, frame=6, neighbours_duo=True):
    """games: [(still, ...)] of 5, index 2 is centred. Neighbours duotone in the palette, centre in full colour."""
    ink, paper, accent = pal["ink"], pal["paper"], pal["accent"]
    for i in (0, 4, 1, 3, 2):
        name = games[i]
        off = i - 2
        sc = 1.0 if off == 0 else 0.74
        w = int(card_w * sc)
        h = int(w * 3 / 4)
        cx = W // 2 + off * gap
        x, y = cx - w // 2, center_y - h // 2
        if off == 0:
            d.rectangle([x + 10, y + 10, x + w + 10 + frame, y + h + 10 + frame], fill=ink)
            d.rectangle([x - frame, y - frame, x + w + frame, y + h + frame], fill=paper)
            img.paste(still(name, (w, h)), (x, y))
        else:
            img.paste(still(name, (w, h), (pal["duo_dark"], pal["duo_light"]) if neighbours_duo else None), (x, y))


def pills(d, y, names, sel, pal, x0=None):
    font = DIN(22)
    widths = [text_w(d, n, font) + 22 for n in names]
    x = (W // 2 - widths[sel] // 2 - sum(widths[:sel]) - 6 * sel) if x0 is None else x0
    for i, n in enumerate(names):
        if i == sel:
            d.rectangle([x, y, x + widths[i], y + 28], fill=pal["paper"])
            d.text((x + widths[i] / 2, y + 15), n, font=font, fill=pal["sel_ink"], anchor="mm")
        else:
            d.rectangle([x, y, x + widths[i], y + 28], outline=pal["line"], width=2)
            d.text((x + widths[i] / 2, y + 15), n, font=font, fill=pal["line"], anchor="mm")
        x += widths[i] + 6


SECTIONS = ["FAVORITES", "QUICK PICKS", "FIGHTING", "SHOOTERS", "NEO GEO", "CPS-2", "GAMECUBE"]

# ---------------------------------------------------------------- 1: red poster, the section name tiled behind
pal = dict(bg=(222, 36, 42), ink=(24, 10, 14), paper=(250, 236, 214), accent=(250, 236, 214),
           duo_dark=(24, 10, 14), duo_light=(240, 110, 100), line=(250, 236, 214), sel_ink=(222, 36, 42))
img = Image.new("RGB", (W, H), pal["bg"]); d = ImageDraw.Draw(img)
tiled(img, "FIGHTING", DIN(120), (192, 22, 32), -10, 104)
d = ImageDraw.Draw(img)
d.rectangle([20, 18, 170, 46], fill=pal["ink"]); d.text((95, 33), "WIIZARD ARCADE", font=DIN(22), fill=pal["paper"], anchor="mm")
clock(d, 620, 20, pal["paper"])
carousel(img, d, ["samsho2.jpg", "kof98.jpg", "sf2ce.jpg", "garou.jpg", "mvsc.jpg"], pal, center_y=160)
d = ImageDraw.Draw(img)
d.rectangle([207, 68, 249, 90], fill=pal["ink"]); d.text((228, 80), "2P", font=DIN(20), fill=pal["paper"], anchor="mm")
d.rectangle([253, 68, 345, 90], fill=pal["ink"]); d.text((299, 80), "HI 248,300", font=DIN(20), fill=pal["paper"], anchor="mm")
heart(d, 414, 82, 10, pal["paper"])
title = "STREET FIGHTER II'"
tf = fit_font(d, title, DIN, 70, 600)
d.text((W // 2 + 3, 290 + 3), title, font=tf, fill=pal["ink"], anchor="mm"); d.text((W // 2, 290), title, font=tf, fill=pal["paper"], anchor="mm")
d.text((W // 2, 328), "1992  /  CAPCOM  /  CPS-1", font=DIN(22), fill=pal["ink"], anchor="mm")
pills(d, 352, SECTIONS, 2, pal)
d.rectangle([0, 404, W, H], fill=pal["ink"])
d.text((24, 440), "FIGHTING", font=DIN(44), fill=pal["paper"], anchor="lm")
d.text((24 + text_w(d, "FIGHTING", DIN(44)) + 12, 446), "3 / 31", font=DIN(24), fill=(240, 110, 100), anchor="lm")
x = 336
for L, lab in (("B", "BACK"), ("Y", "FAVORITE"), ("A", "PLAY")):
    x += button(d, x, 427, L, lab, pal["paper"] if L != "A" else pal["bg"], pal["ink"] if L != "A" else pal["paper"], pal["paper"])
crt(img, "C1-menu-red-poster.jpg")

# ---------------------------------------------------------------- 2: black + yellow, giant vertical section name
pal = dict(bg=(18, 18, 20), ink=(18, 18, 20), paper=(255, 214, 0), accent=(255, 214, 0),
           duo_dark=(18, 18, 20), duo_light=(255, 214, 0), line=(255, 214, 0), sel_ink=(18, 18, 20))
img = Image.new("RGB", (W, H), pal["bg"]); d = ImageDraw.Draw(img)
lay = Image.new("RGBA", (H, 140)); ImageDraw.Draw(lay).text((H // 2, 70), "QUICK PICKS", font=DIN(150), fill=(255, 214, 0), anchor="mm")
lay = lay.rotate(90, expand=True); img.paste(lay, (-30, 0), lay); d = ImageDraw.Draw(img)
d.rectangle([0, 0, 76, H], fill=None)
clock(d, 620, 16, pal["paper"])
d.text((114, 30), "WIIZARD", font=DIN(30), fill=(255, 255, 255), anchor="lm")
# cards slide in from the right: centre big, the next two stacked
img.paste(still("mslug.jpg", (300, 225)), (120, 70)); d.rectangle([120, 70, 420, 295], outline=pal["paper"], width=5)
img.paste(still("1944.jpg", (170, 128), (pal["duo_dark"], pal["duo_light"])), (440, 70))
img.paste(still("dkong.jpg", (170, 128), (pal["duo_dark"], pal["duo_light"])), (440, 214))
d.rectangle([608, 70, 640, 342], fill=pal["paper"])
d.rectangle([130, 80, 172, 102], fill=pal["paper"]); d.text((151, 92), "2P", font=DIN(20), fill=pal["ink"], anchor="mm")
d.text((120, 330), "METAL SLUG", font=DIN(64), fill=(255, 255, 255), anchor="lm")
d.text((122, 368), "1996  /  SNK  /  NEO GEO  /  RUN & GUN", font=DIN(22), fill=pal["paper"], anchor="lm")
d.line([(114, 398), (620, 398)], fill=pal["paper"], width=2)
pills(d, 408, ["FAVORITES", "QUICK PICKS", "FIGHTING", "SHOOTERS", "NEO GEO"], 1, pal, x0=114)
d.text((620, 456), "1 / 24", font=DIN(24), fill=pal["paper"], anchor="rm")
x = 114
for L, lab in (("A", "PLAY"), ("Y", "FAVORITE")):
    x += button(d, x, 446, L, lab, pal["paper"], pal["ink"], (255, 255, 255))
crt(img, "C2-menu-black-yellow.jpg")

# ---------------------------------------------------------------- 3: cream editorial, each section its own colour
pal = dict(bg=(244, 234, 214), ink=(20, 20, 24), paper=(244, 234, 214), accent=(30, 90, 220),
           duo_dark=(20, 30, 90), duo_light=(150, 185, 255), line=(20, 20, 24), sel_ink=(244, 234, 214))
img = Image.new("RGB", (W, H), pal["bg"]); d = ImageDraw.Draw(img)
d.rectangle([0, 0, W, 132], fill=pal["accent"])
d.text((20, 70), "NEO GEO", font=DIN(150), fill=(60, 120, 240), anchor="lm")
d.text((24, 26), "WIIZARD", font=DIN(26), fill=(244, 234, 214), anchor="lm")
clock(d, 620, 14, (244, 234, 214))
carousel(img, d, ["samsho.jpg", "kof97.jpg", "garou.jpg", "mslug2.jpg", "kof2002.jpg"], dict(pal, paper=pal["ink"]), center_y=204, card_w=226, gap=214)
d = ImageDraw.Draw(img)
d.text((W // 2, 322), "GAROU: MARK OF THE WOLVES", font=fit_font(d, "GAROU: MARK OF THE WOLVES", DIN, 44, 600), fill=pal["ink"], anchor="mm")
d.text((W // 2, 352), "1999  /  SNK  /  1-2P FIGHTING", font=DIN(22), fill=pal["accent"], anchor="mm")
d.text((W - 24, 112), "07", font=DIN(64), fill=(244, 234, 214), anchor="rs"); d.text((W - 24, 124), "OF 29", font=DIN(20), fill=(244, 234, 214), anchor="rm")
d.line([(20, 378), (620, 378)], fill=pal["ink"], width=3)
pals = dict(pal, paper=pal["ink"], sel_ink=pal["bg"])
pills(d, 390, ["FIGHTING", "SHOOTERS", "NEO GEO", "CPS-1", "CPS-2", "GAMECUBE"], 2, pals)
x = 330
for L, lab in (("B", "BACK"), ("Y", "FAVORITE"), ("A", "PLAY")):
    x += button(d, x, 446, L, lab, pal["ink"] if L != "A" else pal["accent"], pal["bg"], pal["ink"])
crt(img, "C3-menu-cream-section-colour.jpg")

# ---------------------------------------------------------------- 4: the title IS the background, small cards on top
pal = dict(bg=(20, 60, 50), ink=(10, 24, 20), paper=(240, 250, 230), accent=(255, 90, 60),
           duo_dark=(10, 24, 20), duo_light=(90, 200, 160), line=(240, 250, 230), sel_ink=(20, 60, 50))
img = Image.new("RGB", (W, H), pal["bg"]); d = ImageDraw.Draw(img)
d.text((W // 2, 120), "DONKEY", font=DIN(190), fill=(30, 90, 74), anchor="mm")
d.text((W // 2, 290), "KONG", font=DIN(190), fill=(30, 90, 74), anchor="mm")
d.text((22, 30), "WIIZARD", font=DIN(26), fill=pal["paper"], anchor="lm"); clock(d, 620, 16, pal["paper"])
carousel(img, d, ["galaga88.jpg", "pacman.jpg", "dkong.jpg", "bublbobl.jpg", "rtype.jpg"], dict(pal, paper=pal["accent"]), center_y=206, card_w=230, gap=210)
d = ImageDraw.Draw(img)
d.rectangle([205, 300, 435, 334], fill=pal["accent"]); d.text((W // 2, 318), "DONKEY KONG", font=DIN(30), fill=pal["ink"], anchor="mm")
d.text((W // 2, 352), "1981  /  NINTENDO  /  ARCADE CLASSICS", font=DIN(22), fill=pal["paper"], anchor="mm")
pills(d, 380, ["FAVORITES", "QUICK PICKS", "CLASSICS", "FIGHTING", "NES"], 2, pal)
d.rectangle([0, 424, W, H], fill=pal["ink"])
d.text((22, 452), "ARCADE CLASSICS   12 / 78", font=DIN(26), fill=pal["paper"], anchor="lm")
x = 380
for L, lab in (("Y", "FAVORITE"), ("A", "PLAY")):
    x += button(d, x, 439, L, lab, pal["paper"] if L != "A" else pal["accent"], pal["ink"], pal["paper"])
crt(img, "C4-menu-title-as-background.jpg")

# ---------------------------------------------------------------- attract: the clip full screen, a poster lower third
img = ImageOps.fit(Image.open(os.path.join(STILLS, "sf2ce.jpg")).convert("RGB"), (W, H)); d = ImageDraw.Draw(img)
d.rectangle([0, 372, W, H], fill=(222, 36, 42))
d.rectangle([0, 364, 210, 372], fill=(222, 36, 42))
d.text((20, 404), "STREET FIGHTER II'", font=DIN(52), fill=(250, 236, 214), anchor="lm")
d.text((22, 446), "1992  /  CAPCOM  /  FIGHTING", font=DIN(22), fill=(24, 10, 14), anchor="lm")
for i, (t, w) in enumerate((("2P", 40), ("HI 248,300", 100))):
    x0 = 300 + sum((40, 100)[:i]) + i * 6
    d.rectangle([x0, 436, x0 + w, 458], fill=(24, 10, 14)); d.text((x0 + w / 2, 448), t, font=DIN(20), fill=(250, 236, 214), anchor="mm")
d.rectangle([462, 386, 620, 424], fill=(250, 236, 214)); d.text((541, 406), "PRESS A TO PLAY", font=DIN(26), fill=(222, 36, 42), anchor="mm")
crt(img, "C5-attract-fullscreen.jpg")

# ---------------------------------------------------------------- intro: the wizard as a flat poster figure
img = Image.new("RGB", (W, H), (222, 36, 42)); d = ImageDraw.Draw(img)
tiled(img, "WIIZARD", DIN(118), (192, 22, 32), -10, 100)
d = ImageDraw.Draw(img)
INK, CREAM, RED = (24, 10, 14), (250, 236, 214), (222, 36, 42)
cx = 470
d.polygon([(cx - 120, 470), (cx + 120, 470), (cx + 70, 250), (cx - 70, 250)], fill=INK)                 # robe
d.polygon([(cx - 95, 214), (cx + 95, 214), (cx + 60, 196), (cx - 60, 196)], fill=INK)                   # hat brim
d.polygon([(cx - 62, 200), (cx + 62, 200), (cx + 40, 20)], fill=INK)                                    # hat cone
for sx, sy, s in ((cx - 10, 150, 10), (cx + 22, 104, 7), (cx + 10, 60, 5)):                              # cut-out stars
    pts = [(sx + s * math.cos(a * math.pi / 5 - math.pi / 2) * (1 if a % 2 == 0 else .45),
            sy + s * math.sin(a * math.pi / 5 - math.pi / 2) * (1 if a % 2 == 0 else .45)) for a in range(10)]
    d.polygon(pts, fill=RED)
d.rectangle([cx - 38, 214, cx + 38, 240], fill=CREAM)                                                   # face band
d.rectangle([cx - 24, 222, cx - 12, 230], fill=INK); d.rectangle([cx + 12, 222, cx + 24, 230], fill=INK)  # eyes
d.polygon([(cx - 44, 240), (cx + 44, 240), (cx, 360)], fill=CREAM)                                      # beard
d.polygon([(cx - 66, 276), (cx - 168, 168), (cx - 148, 154), (cx - 52, 254)], fill=INK)                 # arm, raised
d.rounded_rectangle([cx - 190, 60, cx - 158, 160], 8, fill=CREAM)                                       # Wii Remote
d.ellipse([cx - 180, 74, cx - 168, 86], fill=RED); d.rectangle([cx - 182, 100, cx - 166, 106], fill=INK)
for a, l in ((-150, 26), (-120, 34), (-90, 40), (-60, 34), (-30, 26)):                                             # spell lines
    r = math.radians(a)
    d.line([(cx - 174 + 26 * math.cos(r), 52 + 26 * math.sin(r)), (cx - 174 + (26 + l) * math.cos(r), 52 + (26 + l) * math.sin(r))], fill=CREAM, width=7)
d.text((24, 290), "WIIZARD", font=DIN(110), fill=CREAM, anchor="lm")
d.text((28, 372), "ARCADE", font=DIN(56), fill=INK, anchor="lm")
d.rectangle([28, 410, 250, 440], fill=INK); d.text((139, 425), "289 GAMES  /  8 SYSTEMS", font=DIN(22), fill=CREAM, anchor="mm")
crt(img, "C6-intro-wizard.jpg")
print("ok")
