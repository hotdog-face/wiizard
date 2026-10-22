# The shortlist (03, 08, 10, 15, 17, 20) developed across WIIZARD's screens: intro with the redrawn wizard, attract
# (clip full screen + lower third), a game's loading screen, and the main menu (from render20). One board per style.
import os, math, random
from PIL import Image, ImageDraw, ImageOps, ImageFilter
from render20 import (S, W, H, HERE, still, duo, vgrad, tw, fit, crt, star, heart, tiled, lerp,
                      DIN, FUTB, BLACK, ROUND, IMPACT, AVB, AVC, HELV, HELVC, COPPER, GILL, TYPEW, GEORGIA, SFR)

OUT = os.path.join(HERE, "shortlist")
os.makedirs(OUT, exist_ok=True)
THEMES = {k: (name, ref, fn) for k, name, ref, fn in S}
GAME, GAME_SUB, GAME_STILL = "METAL SLUG", "1996  /  SNK  /  NEO GEO  /  1-2P", "mslug.jpg"
CONTROLS = [("A", "JUMP"), ("B", "FIRE"), ("1", "GRENADE")]


# ---------------------------------------------------------------- the wizard (drawn at 2x, returned at 1x)
def wizard(p, size=(300, 360)):
    S2 = 2
    w, h = size
    im = Image.new("RGBA", (w * S2, h * S2))
    d = ImageDraw.Draw(im)
    ol, ow = p.get("outline"), p.get("ow", 0) * S2
    def P(pts):
        return [(x * S2, y * S2) for x, y in pts]
    def poly(pts, fill):
        d.polygon(P(pts), fill=fill, outline=ol if ol else None, width=ow if ol else 0)
    def ell(box, fill):
        d.ellipse([c * S2 for c in box], fill=fill, outline=ol if ol else None, width=ow if ol else 0)
    def rrect(box, r, fill):
        d.rounded_rectangle([c * S2 for c in box], r * S2, fill=fill, outline=ol if ol else None, width=ow if ol else 0)
    C = p["c"]
    rnd = p.get("round", False)
    # robe
    if rnd:
        rrect((92, 196, 216, 352), 46, C["robe"])
    else:
        poly([(70, 352), (238, 352), (196, 196), (110, 196)], C["robe"])
    d.rectangle([(84 if not rnd else 96) * S2, 322 * S2, (224 if not rnd else 212) * S2, 334 * S2], fill=C["trim"])
    for sx, sy in ((150, 270), (178, 300), (124, 306)):
        star_pts = [(sx + 9 * math.cos(math.radians(-90 + a * 36)) * (1 if a % 2 == 0 else .45),
                     sy + 9 * math.sin(math.radians(-90 + a * 36)) * (1 if a % 2 == 0 else .45)) for a in range(10)]
        d.polygon(P(star_pts), fill=C["trim"])
    # raised arm (sleeve) to the remote
    poly([(120, 214), (98, 232), (62, 150), (82, 138)], C["robe"])
    ell((52, 122, 80, 150), C["face"])                                           # hand
    # the Wii Remote: white body, D-pad, A button, 1/2 dots; tilted like a wand
    rem = Image.new("RGBA", (40 * S2, 108 * S2))
    rd = ImageDraw.Draw(rem)
    rd.rounded_rectangle([2 * S2, 2 * S2, 38 * S2, 106 * S2], 10 * S2, fill=C["remote"], outline=ol or (60, 60, 70), width=max(2, ow or 3))
    rd.rectangle([15 * S2, 14 * S2, 25 * S2, 34 * S2], fill=(70, 70, 80)); rd.rectangle([10 * S2, 19 * S2, 30 * S2, 29 * S2], fill=(70, 70, 80))
    rd.ellipse([12 * S2, 42 * S2, 28 * S2, 58 * S2], fill=C["btn"])
    for yy in (78, 90):
        rd.ellipse([16 * S2, yy * S2, 24 * S2, (yy + 8) * S2], fill=(150, 150, 160))
    rd.rectangle([12 * S2, 2 * S2, 28 * S2, 6 * S2], fill=(40, 40, 50))                  # IR window
    rem = rem.rotate(18, expand=True, resample=Image.BICUBIC)
    im.alpha_composite(rem, (38 * S2 - rem.width // 2 + 10 * S2, 20 * S2))
    # spell sparks from the remote's tip
    for a, l in ((-150, 22), (-120, 30), (-95, 36), (-70, 30), (-40, 22)):
        r = math.radians(a)
        x0, y0 = 46 + 22 * math.cos(r), 22 + 22 * math.sin(r)
        d.line([(x0 * S2, y0 * S2), ((x0 + l * math.cos(r)) * S2, (y0 + l * math.sin(r)) * S2)], fill=C["spark"], width=6 * S2 // 2)
    for sx, sy, s in ((18, 10, 9), (96, 4, 7), (8, 52, 6)):
        pts = [(sx + s * math.cos(math.radians(-90 + a * 45)) * (1 if a % 2 == 0 else .4),
                sy + s * math.sin(math.radians(-90 + a * 45)) * (1 if a % 2 == 0 else .4)) for a in range(8)]
        d.polygon(P(pts), fill=C["spark"])
    # head, beard, face
    ell((118, 132, 186, 200), C["face"])
    if rnd:
        ell((114, 170, 190, 268), C["beard"])
    else:
        poly([(114, 178), (190, 178), (166, 238), (152, 272), (138, 238)], C["beard"])
    ell((128, 176, 176, 196), C["beard"])                                       # moustache
    if p.get("eyes") == "googly":
        for ex in (138, 164):
            ell((ex - 10, 148, ex + 10, 170), (255, 255, 255))
            d.ellipse([(ex - 3) * S2, 156 * S2, (ex + 5) * S2, 164 * S2], fill=(20, 20, 30))
    else:
        for ex in (140, 162):
            d.ellipse([(ex - 5) * S2, 156 * S2, (ex + 5) * S2, 166 * S2], fill=C.get("eye", (20, 20, 30)))
            d.ellipse([(ex - 1) * S2, 157 * S2, (ex + 2) * S2, 160 * S2], fill=(255, 255, 255))
    d.arc([140 * S2, 166 * S2, 162 * S2, 182 * S2], 20, 160, fill=C.get("eye", (20, 20, 30)), width=3 * S2)  # smile
    d.ellipse([124 * S2, 166 * S2, 134 * S2, 174 * S2], fill=C.get("cheek", (255, 140, 140)))
    d.ellipse([168 * S2, 166 * S2, 178 * S2, 174 * S2], fill=C.get("cheek", (255, 140, 140)))
    # hat: brim, cone with a bent tip, stars
    poly([(98, 140), (204, 140), (168, 52), (196, 18), (150, 40)], C["hat"])
    if rnd:
        ell((186, 6, 210, 30), C["trim"])
    ell((84, 128, 218, 152), C["hat"])
    d.rectangle([104 * S2, 128 * S2, 198 * S2, 138 * S2], fill=C["band"])
    for sx, sy, s in ((140, 100, 9), (162, 74, 6)):
        pts = [(sx + s * math.cos(math.radians(-90 + a * 36)) * (1 if a % 2 == 0 else .45),
                sy + s * math.sin(math.radians(-90 + a * 36)) * (1 if a % 2 == 0 else .45)) for a in range(10)]
        d.polygon(P(pts), fill=C["band"])
    out = im.resize(size, Image.LANCZOS)
    if p.get("halftone"):
        a = out.split()[3]
        dots = Image.new("L", size, 0)
        dd = ImageDraw.Draw(dots)
        for y in range(0, size[1], 6):
            for x in range(0, size[0], 6):
                dd.ellipse([x + 1, y + 1, x + 4, y + 4], fill=90)
        shade = Image.new("RGBA", size, p["halftone"] + (0,))
        shade.putalpha(Image.composite(dots, Image.new("L", size, 0), a))
        out = Image.alpha_composite(out, shade)
    if p.get("sticker"):                                                           # white die-cut border
        a = out.split()[3].filter(ImageFilter.MaxFilter(9))
        base = Image.new("RGBA", size, p["sticker"] + (0,)); base.putalpha(a)
        out = Image.alpha_composite(base, out)
    if p.get("tilt"):
        out = out.rotate(p["tilt"], expand=True, resample=Image.BICUBIC)
    return out


# ---------------------------------------------------------------- per-style kits
def kit03():
    INK, Y, PNK, BL = (60, 40, 120), (255, 230, 90), (255, 80, 110), (70, 130, 255)
    cols = [(255, 80, 110), (255, 170, 40), (60, 180, 110), (70, 130, 255)]
    def word(img, d, s, x, y, f, center=False):
        widths = [tw(d, ch, f) + 3 for ch in s]
        if center:
            x = x - sum(widths) / 2
        for i, ch in enumerate(s):
            yy = y + (5 if i % 2 else -5)
            d.text((x + 3, yy + 4), ch, font=f, fill=INK, anchor="lm"); d.text((x, yy), ch, font=f, fill=cols[i % 4], anchor="lm")
            x += widths[i]
    return dict(theme="03", tf=ROUND, uf=ROUND, ink=INK, paper=(255, 255, 255), acc=PNK, acc2=Y, bg=(255, 190, 215),
                wiz=dict(round=True, eyes="googly", c=dict(robe=(120, 90, 255), trim=Y, face=(255, 214, 180), beard=(255, 255, 255),
                                                          hat=(255, 120, 60), band=Y, remote=(250, 250, 255), btn=BL, spark=Y, cheek=(255, 150, 170))),
                word=word, shape="round")


def kit08():
    TEAL, MUST, CORAL, CREAM, INK = (34, 104, 110), (232, 168, 56), (226, 102, 78), (244, 232, 210), (36, 40, 48)
    def word(img, d, s, x, y, f, center=False):
        d.text((x, y), s, font=f, fill=CREAM if not center else INK, anchor="mm" if center else "lm")
    return dict(theme="08", tf=FUTB, uf=FUTB, ink=INK, paper=CREAM, acc=CORAL, acc2=MUST, bg=CREAM, teal=TEAL,
                wiz=dict(round=False, c=dict(robe=TEAL, trim=MUST, face=(236, 190, 150), beard=CREAM, hat=MUST, band=CORAL,
                                             remote=(250, 246, 236), btn=TEAL, spark=MUST, eye=INK, cheek=(230, 140, 120))),
                word=word, shape="round")


def kit10():
    YEL, PNK, BLU, K = (255, 228, 0), (255, 60, 140), (40, 80, 255), (10, 10, 10)
    def word(img, d, s, x, y, f, center=False):
        lay = Image.new("RGBA", (W, 160)); ld = ImageDraw.Draw(lay)
        ax = W // 2 if center else x
        ld.text((ax + 5, 85), s, font=f, fill=K, anchor="mm" if center else "lm")
        ld.text((ax, 80), s, font=f, fill=YEL, anchor="mm" if center else "lm", stroke_width=3, stroke_fill=K)
        lay = lay.rotate(4, resample=Image.BICUBIC); img.paste(lay, (0, y - 80), lay)
    return dict(theme="10", tf=IMPACT, uf=IMPACT, ink=K, paper=(255, 255, 255), acc=PNK, acc2=YEL, bg=(255, 170, 205),
                wiz=dict(halftone=(10, 10, 10), sticker=(255, 255, 255), tilt=-6, outline=K, ow=3,
                         c=dict(robe=BLU, trim=YEL, face=(255, 205, 170), beard=(255, 255, 255), hat=PNK, band=YEL,
                                remote=(255, 255, 255), btn=BLU, spark=YEL)),
                word=word, shape="tag")


def kit15():
    R, Y, B, K, CR = (232, 64, 52), (250, 200, 30), (36, 84, 196), (18, 18, 18), (246, 238, 222)
    def word(img, d, s, x, y, f, center=False):
        d.text((x, y), s, font=f, fill=K, anchor="mm" if center else "lm")
    return dict(theme="15", tf=FUTB, uf=FUTB, ink=K, paper=CR, acc=R, acc2=Y, bg=CR, blue=B,
                wiz=dict(outline=K, ow=4, c=dict(robe=B, trim=Y, face=Y, beard=CR, hat=R, band=K, remote=(255, 255, 255),
                                                 btn=R, spark=K, eye=K, cheek=R)),
                word=word, shape="rect")


def kit17():
    K, WH, ACC = (0, 0, 0), (255, 255, 255), (0, 255, 120)
    def word(img, d, s, x, y, f, center=False):
        lay = Image.new("RGBA", (W, 200)); ImageDraw.Draw(lay).text((W // 2 if center else x, 100), s, font=f, fill=WH, anchor="mm" if center else "lm")
        lay = lay.resize((W, 150)); img.paste(lay, (0, y - 75), lay)
    return dict(theme="17", tf=HELVC, uf=HELV, ink=K, paper=WH, acc=ACC, acc2=WH, bg=K,
                wiz=dict(outline=K, ow=4, c=dict(robe=WH, trim=K, face=WH, beard=WH, hat=WH, band=K, remote=ACC,
                                                 btn=K, spark=ACC, eye=K, cheek=WH)),
                word=word, shape="rect")


def kit20():
    K, Y, R, CY, WH = (14, 10, 30), (255, 220, 0), (255, 40, 60), (0, 210, 255), (255, 255, 255)
    def word(img, d, s, x, y, f, center=False):
        lay = Image.new("RGBA", (W, 140)); ld = ImageDraw.Draw(lay)
        ld.text((W // 2 if center else x, 70), s, font=f, fill=Y, anchor="mm" if center else "lm", stroke_width=7, stroke_fill=R)
        lay = lay.transform((W, 140), Image.AFFINE, (1, 0.2, -14, 0, 1, 0), resample=Image.BICUBIC)
        img.paste(lay, (0, y - 70), lay)
    return dict(theme="20", tf=IMPACT, uf=IMPACT, ink=K, paper=WH, acc=R, acc2=Y, bg=K, cy=CY,
                wiz=dict(outline=K, ow=4, tilt=-8, c=dict(robe=CY, trim=Y, face=(255, 200, 160), beard=WH, hat=R, band=Y,
                                                           remote=WH, btn=CY, spark=Y, eye=K, cheek=(255, 120, 120))),
                word=word, shape="tag")


KITS = {"03": kit03, "08": kit08, "10": kit10, "15": kit15, "17": kit17, "20": kit20}


def background(k):
    t = THEMES[k["theme"]][2]()
    img = Image.new("RGB", (W, H), t.get("bg", k["bg"]))
    if "paint_bg" in t:
        t["paint_bg"](img)
    return img


def chip(d, x, y, s, f, bg, fg, shape, h=28, pad=16):
    w = tw(d, s, f) + pad * 2
    if shape == "round":
        d.rounded_rectangle([x, y, x + w, y + h], h // 2, fill=bg)
    elif shape == "tag":
        d.polygon([(x, y), (x + w, y), (x + w - 8, y + h), (x - 8, y + h)], fill=bg)
    else:
        d.rectangle([x, y, x + w, y + h], fill=bg)
    d.text((x + w / 2, y + h / 2 + 1), s, font=f, fill=fg, anchor="mm")
    return w


def btn(d, x, y, L, label, f, k, a=False):
    s = 28
    col = k["acc"] if a else k["ink"] if k["theme"] != "17" else (255, 255, 255)
    ink = (255, 255, 255) if k["theme"] != "17" or a else (0, 0, 0)
    if k["shape"] == "round":
        d.ellipse([x, y, x + s, y + s], fill=col)
    else:
        d.rectangle([x, y, x + s, y + s], fill=col)
    d.text((x + s / 2, y + s / 2 + 1), L, font=f, fill=ink, anchor="mm")
    return s


# ---------------------------------------------------------------- screens
def intro(k):
    img = background(k)
    d = ImageDraw.Draw(img)
    if k["theme"] == "17":
        lay = Image.new("RGBA", (W, 300)); ImageDraw.Draw(lay).text((W // 2, 150), "WIIZARD", font=HELVC(250), fill=(36, 36, 36), anchor="mm")
        img.paste(lay.resize((W, 420)), (0, 20), lay.resize((W, 420)))
    if k["theme"] == "20":
        star(d, 450, 230, 230, (60, 30, 90), 18, .78)
    wz = wizard(k["wiz"], (300, 360))
    img.paste(wz, (340 + (300 - wz.width) // 2, 112 + (360 - wz.height) // 2), wz)
    d = ImageDraw.Draw(img)
    k["word"](img, d, "WIIZARD", 30, 196, fit(d, "WIIZARD", k["tf"], 86 if k["theme"] not in ("03",) else 64, 290))
    d = ImageDraw.Draw(img)
    chip(d, 34, 262, "ARCADE", k["uf"](22), k["acc"], (255, 255, 255) if k["theme"] != "17" else (0, 0, 0), k["shape"], h=34)
    sub = "289 GAMES  /  8 SYSTEMS"
    d.text((36, 322), sub, font=k["uf"](20), fill=k["ink"] if k["theme"] not in ("17", "20") else (255, 255, 255), anchor="lm")
    return img


def attract(k):
    img = ImageOps.fit(Image.open(os.path.join(os.path.join(HERE, "../../videos/stills"), GAME_STILL)).convert("RGB"), (W, H))
    d = ImageDraw.Draw(img)
    th = k["theme"]
    band_col = {"03": (255, 255, 255), "08": k.get("teal", (34, 104, 110)), "10": k["acc"], "15": k["paper"], "17": (0, 0, 0), "20": k["acc"]}[th]
    if th == "03":
        d.rounded_rectangle([16, 356, W - 16, H - 14], 28, fill=band_col)
    elif th == "10":
        d.polygon([(0, 372), (W, 350), (W, H), (0, H)], fill=band_col)
        for x in range(0, W, 14):
            for y in range(360, H, 14):
                d.ellipse([x, y, x + 4, y + 4], fill=(255, 120, 180))
    elif th == "15":
        d.rectangle([0, 360, W, H], fill=band_col); d.rectangle([0, 360, W, 368], fill=k["ink"])
        d.ellipse([570, 330, 640, 400], fill=k["acc2"])
    elif th == "20":
        d.polygon([(0, 360), (W, 380), (W, H), (0, H)], fill=band_col); d.rectangle([0, 352, W, 360], fill=k["acc2"])
    else:
        d.rectangle([0, 362, W, H], fill=band_col)
    tcol = {"03": k["ink"], "08": k["paper"], "10": k["acc2"], "15": k["ink"], "17": (255, 255, 255), "20": k["acc2"]}[th]
    if th in ("03", "10", "20"):
        k["word"](img, d, GAME, 36, 404, fit(d, GAME + "   ", k["tf"], 48, 360))
        d = ImageDraw.Draw(img)
    else:
        d.text((32, 404), GAME, font=k["tf"](46 if th != "17" else 58), fill=tcol, anchor="lm")
    subc = {"03": k["acc"], "08": k["acc2"], "10": (255, 255, 255), "15": k["acc"], "17": k["acc"], "20": (255, 255, 255)}[th]
    d.text((34, 446), GAME_SUB, font=k["uf"](18), fill=subc, anchor="lm")
    pbg = {"03": k["ink"], "08": k["acc"], "10": (10, 10, 10), "15": k["ink"], "17": k["acc"], "20": k["acc2"]}[th]
    pfg = {"03": k["acc2"], "08": k["paper"], "10": k["acc2"], "15": k["paper"], "17": (0, 0, 0), "20": (14, 10, 30)}[th]
    f = k["uf"](22)
    w = tw(d, "PRESS A TO PLAY", f) + 32
    chip(d, W - 32 - w, 392, "PRESS A TO PLAY", f, pbg, pfg, k["shape"], h=38)
    return img


def loading(k):
    img = background(k)
    d = ImageDraw.Draw(img)
    th = k["theme"]
    dark_bg = th in ("17", "20")
    txt = (255, 255, 255) if dark_bg else k["ink"]
    # box art / still with the style's frame
    t = THEMES[th][2]()
    sx, sy, sw, sh = 330, 70, 280, 210
    t["card"](img, d, sx, sy, sw, sh, still(GAME_STILL, (sw, sh)))
    d = ImageDraw.Draw(img)
    chip(d, 32, 70, "NEO GEO", k["uf"](18), k["acc"], (255, 255, 255) if th != "17" else (0, 0, 0), k["shape"])
    if th in ("03", "10", "20"):
        k["word"](img, d, "METAL", 30, 150, k["tf"](58)); k["word"](img, d, "SLUG", 30, 214, k["tf"](58))
        d = ImageDraw.Draw(img)
    else:
        d.text((30, 150), "METAL", font=k["tf"](62 if th != "17" else 90), fill=txt, anchor="lm")
        d.text((30, 216), "SLUG", font=k["tf"](62 if th != "17" else 90), fill=txt, anchor="lm")
    # progress
    d.rectangle([32, 300, 608, 314], fill=(255, 255, 255) if not dark_bg else (40, 40, 50), outline=txt)
    d.rectangle([32, 300, 32 + int(576 * .62), 314], fill=k["acc"])
    d.text((32, 336), "LOADING", font=k["uf"](20), fill=txt, anchor="lm")
    # controls + exit
    x = 32
    f = k["uf"](20)
    for L, lab in CONTROLS:
        btn(d, x, 372, L, lab, f, k)
        d.text((x + 36, 386), lab, font=f, fill=txt, anchor="lm")
        x += 36 + tw(d, lab, f) + 24
    ex = "EXIT:  L + R + Z + START"
    d.text((32, 432), ex, font=f, fill=k["acc"] if th not in ("08",) else k.get("teal"), anchor="lm")
    d.text((608, 432), "1-2 PLAYERS  /  FREE PLAY", font=k["uf"](18), fill=txt, anchor="rm")
    return img


# ---------------------------------------------------------------- boards
def main():
    lab = HELV(24)
    for key in ("03", "08", "10", "15", "17", "20"):
        name, ref, _ = THEMES[key]
        k = KITS[key]()
        slug = name.lower().replace(" / ", "-").replace(" ", "-")
        frames = []
        for scr, fn in (("intro", intro), ("attract", attract), ("loading", loading)):
            frames.append((scr, crt(fn(k), os.path.join(OUT, f"{key}-{slug}-{scr}.jpg"))))
        menu = Image.open(os.path.join(HERE, "explore", f"{key}-{slug}.jpg"))
        frames.insert(1, ("menu", menu))
        board = Image.new("RGB", (1280, 960 + 48), (255, 255, 255))
        d = ImageDraw.Draw(board)
        d.text((14, 12), f"{key}  {name}  —  " + (ref if ref.startswith("after") else "after " + ref), font=lab, fill=(20, 20, 20))
        for i, (scr, im) in enumerate(frames):
            board.paste(im.resize((640, 480)), ((i % 2) * 640, 48 + (i // 2) * 480))
        board.save(os.path.join(HERE, f"shortlist-{key}-{slug}.jpg"), quality=86)
        print(key, name)


if __name__ == "__main__":
    main()
