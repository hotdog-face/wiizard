# 20 art-direction explorations of WIIZARD's main menu, after style-heavy motion/design studios (BUCK and peers).
# Same screen and content in every frame (FIGHTING section, Street Fighter II' selected) so only the style changes.
# 640x480 as the CRT shows it -> light blur + scanlines -> 2x. Output: explore/NN-name.jpg + two labelled sheets.
import os, math, random
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageOps, ImageChops

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "explore")
os.makedirs(OUT, exist_ok=True)
STILLS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "../../videos/stills")   # game stills (not in the repo)
W, H = 640, 480
SUP, SYS = "/System/Library/Fonts/Supplemental/", "/System/Library/Fonts/"


def face(path, style=None):
    """A font face by file (+ style name for .ttc collections)."""
    def mk(size):
        if style is None:
            return ImageFont.truetype(path, size)
        for i in range(20):
            try:
                f = ImageFont.truetype(path, size, index=i)
            except Exception:
                break
            if f.getname()[1].lower() == style.lower():
                return f
        return ImageFont.truetype(path, size)
    return mk


DIN = face(SUP + "DIN Condensed Bold.ttf")
FUTB = face(SUP + "Futura.ttc", "Bold")
FUTC = face(SUP + "Futura.ttc", "Condensed ExtraBold")
BLACK = face(SUP + "Arial Black.ttf")
ROUND = face(SUP + "Arial Rounded Bold.ttf")
IMPACT = face(SUP + "Impact.ttf")
AVC = face(SYS + "Avenir Next Condensed.ttc", "Heavy")
AVB = face(SYS + "Avenir Next.ttc", "Bold")
HELV = face(SYS + "HelveticaNeue.ttc", "Bold")
HELVC = face(SYS + "HelveticaNeue.ttc", "Condensed Black")
DIDOT = face(SUP + "Didot.ttc", "Bold")
BODONI = face(SUP + "Bodoni 72.ttc", "Bold")
COPPER = face(SUP + "Copperplate.ttc", "Bold")
TYPEW = face(SUP + "AmericanTypewriter.ttc", "Bold")
MARKER = face(SYS + "MarkerFelt.ttc", "Wide")
CHALK = face(SUP + "ChalkboardSE.ttc", "Bold")
GEORGIA = face(SUP + "Georgia Bold.ttf")
GILL = face(SUP + "GillSans.ttc", "UltraBold")
SFR = face(SYS + "SFNSRounded.ttf")

# ---------------------------------------------------------------- content (the same in every frame)
SECTION, COUNT = "FIGHTING", "3 / 31"
TITLE, SUB = "STREET FIGHTER II'", "1992  /  CAPCOM  /  CPS-1"
CENTER, NEIGH = "sf2ce.jpg", ["samsho2.jpg", "kof98.jpg", "garou.jpg", "mvsc.jpg"]   # far left, left, right, far right
PILLS = ["FAVORITES", "QUICK PICKS", "FIGHTING", "SHOOTERS", "NEO GEO", "CPS-2", "GAMECUBE"]
SEL = 2
_cache = {}


def still(name, size):
    k = (name, size)
    if k not in _cache:
        _cache[k] = ImageOps.fit(Image.open(os.path.join(STILLS, name)).convert("RGB"), size)
    return _cache[k].copy()


def duo(im, dark, light):
    return ImageOps.colorize(ImageOps.autocontrast(ImageOps.grayscale(im)), dark, light)


def lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def vgrad(img, stops, box=(0, 0, W, H)):
    d = ImageDraw.Draw(img)
    x0, y0, x1, y1 = box
    for y in range(y0, y1):
        t = (y - y0) / max(1, y1 - y0 - 1)
        for i in range(len(stops) - 1):
            (t0, c0), (t1, c1) = stops[i], stops[i + 1]
            if t0 <= t <= t1:
                d.line([(x0, y), (x1, y)], fill=lerp(c0, c1, (t - t0) / max(1e-6, t1 - t0)))
                break


def tw(d, s, f):
    return d.textlength(s, font=f)


def fit(d, s, mk, size, maxw):
    while size > 10 and tw(d, s, mk(size)) > maxw:
        size -= 2
    return mk(size)


def crt(img, path):
    img = img.convert("RGB").filter(ImageFilter.GaussianBlur(0.55))
    sl = Image.new("L", (W, H), 255)
    ds = ImageDraw.Draw(sl)
    for y in range(1, H, 2):
        ds.line([(0, y), (W, y)], fill=205)
    img = Image.composite(img, Image.new("RGB", (W, H), 0), sl)
    img = img.resize((W * 2, H * 2), Image.BICUBIC)
    img.save(path, quality=92)
    return img


def heart(d, cx, cy, s, col):
    d.ellipse([cx - s, cy - s * .7, cx, cy + s * .3], fill=col)
    d.ellipse([cx, cy - s * .7, cx + s, cy + s * .3], fill=col)
    d.polygon([(cx - s * .95, cy - s * .05), (cx + s * .95, cy - s * .05), (cx, cy + s)], fill=col)


def star(d, cx, cy, r, col, k=5, inner=.45, rot=-90):
    pts = []
    for a in range(k * 2):
        rr = r if a % 2 == 0 else r * inner
        ang = math.radians(rot + a * 180 / k)
        pts.append((cx + rr * math.cos(ang), cy + rr * math.sin(ang)))
    d.polygon(pts, fill=col)


# ---------------------------------------------------------------- the menu, drawn from a theme
def layout():
    """Card rects: center + 4 neighbours (x0, y0, w, h)."""
    cw, ch = 262, 196
    cx, cy = W // 2, 168
    rects = {"c": (cx - cw // 2, cy - ch // 2, cw, ch)}
    nw, nh = int(cw * .72), int(ch * .72)
    for key, off in (("l2", -2), ("l1", -1), ("r1", 1), ("r2", 2)):
        x = cx + off * 232 - nw // 2
        rects[key] = (x, cy - nh // 2, nw, nh)
    return rects


def draw_menu(t):
    img = Image.new("RGB", (W, H), t.get("bg", (20, 20, 20)))
    if "paint_bg" in t:
        t["paint_bg"](img)
    d = ImageDraw.Draw(img)
    R = layout()
    names = {"l2": NEIGH[0], "l1": NEIGH[1], "r1": NEIGH[2], "r2": NEIGH[3]}
    for k in ("l2", "r2", "l1", "r1"):
        x, y, w, h = R[k]
        im = still(names[k], (w, h))
        im = t["neigh"](im) if "neigh" in t else im
        if "neigh_card" in t:
            t["neigh_card"](img, d, x, y, w, h, im)
        else:
            img.paste(im, (x, y))
    x, y, w, h = R["c"]
    t["card"](img, d, x, y, w, h, still(CENTER, (w, h)))
    d = ImageDraw.Draw(img)
    # badges + favourite
    if "badges" in t:
        t["badges"](img, d, x, y, w, h)
    # title + sub line
    t["title"](img, d)
    d = ImageDraw.Draw(img)
    t["pills"](img, d)
    d = ImageDraw.Draw(img)
    t["bottom"](img, d)
    d = ImageDraw.Draw(img)
    t["top"](img, d)
    if "post" in t:
        img = t["post"](img)
    return img


# ---------------------------------------------------------------- reusable parts
def card_frame(paper, shadow, frame=6, off=10):
    def f(img, d, x, y, w, h, im):
        if shadow:
            d.rectangle([x - frame + off, y - frame + off, x + w + frame + off, y + h + frame + off], fill=shadow)
        d.rectangle([x - frame, y - frame, x + w + frame, y + h + frame], fill=paper)
        img.paste(im, (x, y))
    return f


def card_round(border, rad=18, bw=6, shadow=None, off=8):
    def f(img, d, x, y, w, h, im):
        if shadow:
            d.rounded_rectangle([x - bw + off, y - bw + off, x + w + bw + off, y + h + bw + off], rad + bw, fill=shadow)
        d.rounded_rectangle([x - bw, y - bw, x + w + bw, y + h + bw], rad + bw, fill=border)
        m = Image.new("L", (w, h), 0)
        ImageDraw.Draw(m).rounded_rectangle([0, 0, w - 1, h - 1], rad, fill=255)
        img.paste(im, (x, y), m)
    return f


def neigh_round(rad=14, border=None, bw=4):
    def f(img, d, x, y, w, h, im):
        if border:
            d.rounded_rectangle([x - bw, y - bw, x + w + bw, y + h + bw], rad + bw, fill=border)
        m = Image.new("L", (w, h), 0)
        ImageDraw.Draw(m).rounded_rectangle([0, 0, w - 1, h - 1], rad, fill=255)
        img.paste(im, (x, y), m)
    return f


def badges_boxes(bg, fg, font, rad=0, gap=6, h=22):
    def f(img, d, x, y, w, hh):
        bx = x + 8
        for s in ("2P", "HI 248,300"):
            bw = tw(d, s, font) + 16
            if rad:
                d.rounded_rectangle([bx, y + 8, bx + bw, y + 8 + h], rad, fill=bg)
            else:
                d.rectangle([bx, y + 8, bx + bw, y + 8 + h], fill=bg)
            d.text((bx + bw / 2, y + 8 + h / 2 + 1), s, font=font, fill=fg, anchor="mm")
            bx += bw + gap
        heart(d, x + w - 20, y + 20, 9, fg if bg != fg else bg)
    return f


def title_std(font_mk, size, col, sub_font, sub_col, y=292, shadow=None, soff=3, case=str.upper, sy=None):
    def f(img, d):
        s = case(TITLE)
        tf = fit(d, s, font_mk, size, 600)
        if shadow:
            d.text((W // 2 + soff, y + soff), s, font=tf, fill=shadow, anchor="mm")
        d.text((W // 2, y), s, font=tf, fill=col, anchor="mm")
        d.text((W // 2, sy or y + 34), case(SUB), font=sub_font, fill=sub_col, anchor="mm")
    return f


def pills_std(font, sel_bg, sel_fg, fg, outline=None, shape="rect", y=346, h=28, pad=22, gap=6, rad=14, case=str.upper):
    def f(img, d):
        names = [case(p) for p in PILLS]
        ws = [tw(d, n, font) + pad for n in names]
        x = W // 2 - ws[SEL] // 2 - sum(ws[:SEL]) - gap * SEL
        for i, n in enumerate(names):
            box = [x, y, x + ws[i], y + h]
            if i == SEL:
                if shape == "round":
                    d.rounded_rectangle(box, rad, fill=sel_bg)
                elif shape == "underline":
                    d.rectangle([x + 6, y + h - 4, x + ws[i] - 6, y + h], fill=sel_bg)
                elif shape == "tag":
                    d.polygon([(x, y), (x + ws[i], y), (x + ws[i] - 8, y + h), (x - 8, y + h)], fill=sel_bg)
                else:
                    d.rectangle(box, fill=sel_bg)
                tc = sel_fg if shape != "underline" else sel_fg
            else:
                if outline:
                    if shape == "round":
                        d.rounded_rectangle(box, rad, outline=outline, width=2)
                    elif shape == "tag":
                        d.polygon([(x, y), (x + ws[i], y), (x + ws[i] - 8, y + h), (x - 8, y + h)], outline=outline)
                    elif shape != "underline":
                        d.rectangle(box, outline=outline, width=2)
                tc = fg
            d.text((x + ws[i] / 2, y + h / 2 + 1), n, font=font, fill=tc, anchor="mm")
            x += ws[i] + gap
    return f


def buttons(d, x, y, font, box_col, ink, lab, shape="rect", a_col=None, s=26, case=str.upper, items=None):
    for L, label in items or (("B", "BACK"), ("Y", "FAVORITE"), ("A", "PLAY")):
        bc = a_col if (L == "A" and a_col) else box_col
        if shape == "circle":
            d.ellipse([x, y, x + s, y + s], fill=bc)
        elif shape == "round":
            d.rounded_rectangle([x, y, x + s, y + s], 7, fill=bc)
        else:
            d.rectangle([x, y, x + s, y + s], fill=bc)
        d.text((x + s / 2, y + s / 2 + 1), L, font=font, fill=ink, anchor="mm")
        lab_s = case(label)
        d.text((x + s + 8, y + s / 2 + 1), lab_s, font=font, fill=lab, anchor="lm")
        x += s + 8 + tw(d, lab_s, font) + 18
    return x


def bottom_std(bar, name_font, name_col, count_col, btn_font, box_col, ink, lab, shape="rect", a_col=None, y=404,
               case=str.upper, btn_x=342):
    def f(img, d):
        if bar:
            d.rectangle([0, y, W, H], fill=bar)
        nm = case(SECTION)
        d.text((24, y + 36), nm, font=name_font, fill=name_col, anchor="lm")
        d.text((24 + tw(d, nm, name_font) + 12, y + 40), COUNT, font=btn_font, fill=count_col, anchor="lm")
        buttons(d, btn_x, y + 23, btn_font, box_col, ink, lab, shape, a_col, case=case)
    return f


def top_std(font, col, brand="WIIZARD", bfont=None, bcol=None, case=str.upper):
    def f(img, d):
        d.text((24, 30), case(brand), font=bfont or font, fill=bcol or col, anchor="lm")
        x, y = 620, 20
        for b in range(3):
            h = 6 + b * 4
            d.rectangle([x - 72 + b * 7, y + 14 - h, x - 68 + b * 7, y + 14], fill=col)
        d.text((x, y + 8), "7:42", font=font, fill=col, anchor="rm")
    return f


def grain(amount=18, seed=1):
    def f(img):
        rnd = Image.effect_noise((W, H), amount * 3).convert("RGB")
        return Image.blend(img.convert("RGB"), rnd, amount / 400)
    return f


def tiled(img, word, font, col, angle, step_y, stagger=90):
    lay = Image.new("RGBA", (W * 3, H * 3))
    d = ImageDraw.Draw(lay)
    line = (word + " ") * 14
    for r in range(0, H * 3 // step_y + 1):
        d.text((-(r * stagger) % 400 - 400, r * step_y), line, font=font, fill=col)
    lay = lay.rotate(angle, resample=Image.BICUBIC)
    img.paste(lay, (-W, -H), lay)


# ---------------------------------------------------------------- the 20 styles
S = []


def tcase(s):
    return s.title().replace("Ii'", "II'").replace("Cps", "CPS").replace("Neo Geo", "Neo Geo")



def style(key, name, ref):
    def deco(fn):
        S.append((key, name, ref, fn))
        return fn
    return deco


@style("01", "Kinetic poster", "BUCK - VALORANT Champions, Adobe MAX")
def s01():
    P, I, C = (222, 36, 42), (24, 10, 14), (250, 236, 214)
    return dict(bg=P, paint_bg=lambda im: tiled(im, SECTION, DIN(120), (192, 22, 32), -10, 104),
                neigh=lambda im: duo(im, I, (240, 110, 100)), card=card_frame(C, I),
                badges=badges_boxes(I, C, DIN(20)), title=title_std(DIN, 68, C, DIN(22), I, shadow=I),
                pills=pills_std(DIN(22), C, P, C, C), bottom=bottom_std(I, DIN(44), C, (240, 110, 100), DIN(22), C, I, C, a_col=P),
                top=top_std(DIN(24), C))


@style("02", "Neon low-poly", "BUCK - Spark Arena Byte")
def s02():
    random.seed(4)
    def bg(img):
        vgrad(img, [(0, (40, 10, 90)), (0.5, (190, 30, 170)), (0.66, (255, 120, 90)), (0.7, (255, 210, 80)), (1, (255, 210, 80))])
        d = ImageDraw.Draw(img)
        pts = [(x, 330 + random.randint(-50, 15)) for x in range(-40, W + 80, 64)]
        for i in range(len(pts) - 1):
            (x0, y0), (x1, y1) = pts[i], pts[i + 1]
            mx, my = (x0 + x1) / 2 + random.randint(-15, 15), y0 + random.randint(35, 70)
            for tri, base in (([(x0, y0), (x1, y1), (mx, my)], (30, 200, 210)), ([(x0, y0), (mx, my), (x0 - 10, H)], (20, 120, 170)),
                              ([(x1, y1), (mx, my), (x1 + 10, H)], (40, 60, 140)), ([(mx, my), (x0 - 10, H), (x1 + 10, H)], (25, 30, 90))):
                j = random.randint(-16, 16)
                d.polygon(tri, fill=tuple(max(0, min(255, c + j)) for c in base))
        for _ in range(12):
            x, y, s = random.randint(0, W), random.randint(50, 250), random.randint(6, 14)
            d.polygon([(x, y), (x + s, y + s // 2), (x + s // 3, y + s)], fill=(255, 230, 90) if random.random() < .5 else (90, 240, 255))
    def card(img, d, x, y, w, h, im):
        fr = [(x - 8, y - 4), (x + w + 10, y - 12), (x + w + 4, y + h + 8), (x - 4, y + h + 14)]
        d.polygon([(p[0] + 8, p[1] + 8) for p in fr], fill=(20, 10, 60))
        d.polygon(fr, fill=(90, 240, 255))
        img.paste(im, (x, y))
    Y, CY, NV = (255, 220, 70), (90, 240, 255), (20, 10, 60)
    return dict(paint_bg=bg, neigh=lambda im: duo(im, (40, 10, 90), (255, 120, 200)), card=card,
                badges=badges_boxes(NV, Y, FUTB(14)), title=title_std(IMPACT, 60, (255, 255, 255), FUTB(16), NV, shadow=Y, soff=4),
                pills=pills_std(FUTB(14), Y, NV, (255, 255, 255), shape="tag"),
                bottom=bottom_std(NV, IMPACT(36), (255, 255, 255), CY, FUTB(15), CY, NV, (255, 255, 255)),
                top=top_std(FUTB(18), (255, 255, 255)))


@style("03", "Toybox", "BUCK - Cartoonito Beepers")
def s03():
    def bg(img):
        d = ImageDraw.Draw(img)
        d.ellipse([-120, 250, 300, 640], fill=(255, 160, 200)); d.ellipse([420, -160, 820, 200], fill=(200, 175, 255))
        for cx, cy, r, col in ((38, 120, 30, (120, 90, 255)), (608, 250, 26, (255, 120, 60)), (600, 120, 16, (90, 200, 120))):
            d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=col)
            for ex in (-r * .35, r * .35):
                d.ellipse([cx + ex - r * .26, cy - r * .35, cx + ex + r * .26, cy + r * .2], fill=(255, 255, 255))
                d.ellipse([cx + ex - r * .1, cy - r * .15, cx + ex + r * .12, cy + r * .08], fill=(30, 30, 60))
    INK = (60, 40, 120)
    def title(img, d):
        x = W // 2 - 200
        cols = [(255, 80, 110), (255, 170, 40), (60, 180, 110), (70, 130, 255)]
        f = ROUND(36)
        widths = [tw(d, ch, f) + 2 for ch in TITLE]
        x = W // 2 - sum(widths) / 2
        for i, ch in enumerate(TITLE):
            yy = 290 + (4 if i % 2 else -4)
            d.text((x + 2, yy + 3), ch, font=f, fill=INK, anchor="lm"); d.text((x, yy), ch, font=f, fill=cols[i % 4], anchor="lm")
            x += widths[i]
        d.text((W // 2, 324), SUB, font=ROUND(15), fill=INK, anchor="mm")
    return dict(bg=(255, 190, 215), paint_bg=bg, neigh=lambda im: im, neigh_card=neigh_round(14, (255, 255, 255)),
                card=card_round((255, 255, 255), 18, 8, INK), badges=badges_boxes(INK, (255, 230, 90), ROUND(13), rad=11),
                title=title, pills=pills_std(ROUND(14), INK, (255, 230, 90), INK, (255, 255, 255), "round"),
                bottom=bottom_std((255, 255, 255), ROUND(30), INK, (255, 80, 110), ROUND(14), INK, (255, 230, 90), INK, "circle", (255, 80, 110)),
                top=top_std(ROUND(20), INK, "wiizard", ROUND(28), case=str.lower if False else str.upper))


@style("04", "Fat-line cartoon", "Golden Wolf")
def s04():
    K = (20, 20, 20)
    def bg(img):
        d = ImageDraw.Draw(img)
        random.seed(2)
        for _ in range(16):
            x, y = random.randint(0, W), random.randint(0, H)
            c = random.choice([(255, 90, 60), (40, 200, 255), (255, 210, 0), (120, 230, 120)])
            pts = [(x + i * 12, y + (8 if i % 2 else -8)) for i in range(6)]
            d.line(pts, fill=K, width=9, joint="curve"); d.line(pts, fill=c, width=5, joint="curve")
    def card(img, d, x, y, w, h, im):
        d.rounded_rectangle([x - 10, y - 10, x + w + 16, y + h + 16], 22, fill=K)
        d.rounded_rectangle([x - 10, y - 10, x + w + 8, y + h + 8], 22, fill=(255, 210, 0), outline=K, width=5)
        m = Image.new("L", (w, h), 0); ImageDraw.Draw(m).rounded_rectangle([0, 0, w - 1, h - 1], 12, fill=255)
        img.paste(im, (x, y), m); d.rounded_rectangle([x, y, x + w, y + h], 12, outline=K, width=4)
    def neigh_card(img, d, x, y, w, h, im):
        d.rounded_rectangle([x - 4, y - 4, x + w + 4, y + h + 4], 14, fill=K)
        m = Image.new("L", (w, h), 0); ImageDraw.Draw(m).rounded_rectangle([0, 0, w - 1, h - 1], 10, fill=255)
        img.paste(im, (x, y), m)
    def title(img, d):
        f = fit(d, TITLE, BLACK, 44, 600)
        d.text((W // 2, 296), TITLE, font=f, fill=(255, 90, 60), anchor="mm", stroke_width=5, stroke_fill=K)
        d.text((W // 2, 332), SUB, font=BLACK(14), fill=K, anchor="mm")
    return dict(bg=(255, 245, 225), paint_bg=bg, neigh=lambda im: im, neigh_card=neigh_card, card=card,
                badges=badges_boxes(K, (255, 255, 255), BLACK(12), rad=10), title=title,
                pills=pills_std(BLACK(12), (40, 200, 255), K, K, K, "round", y=352),
                bottom=bottom_std(K, BLACK(30), (255, 210, 0), (255, 255, 255), BLACK(13), (255, 255, 255), K, (255, 255, 255), "round", (255, 90, 60)),
                top=top_std(BLACK(16), K))


@style("05", "Risograph two-ink", "Gunner")
def s05():
    PINK, BLUE, PAPER = (255, 72, 176), (0, 120, 191), (246, 240, 228)
    def mul(c1, c2):
        return tuple(a * b // 255 for a, b in zip(c1, c2))
    def riso(im, ink):
        g = ImageOps.grayscale(im).point(lambda v: 255 - v)
        return Image.composite(Image.new("RGB", im.size, ink), Image.new("RGB", im.size, PAPER), g.point(lambda v: int(v * .9)))
    def card(img, d, x, y, w, h, im):
        g = ImageOps.autocontrast(ImageOps.grayscale(im))
        blue = Image.composite(Image.new("RGB", im.size, PAPER), Image.new("RGB", im.size, BLUE), g)          # shadows in blue
        pink = Image.composite(Image.new("RGB", im.size, PAPER), Image.new("RGB", im.size, PINK), g.point(lambda v: min(255, v + 90)))
        pink = pink.transform(pink.size, Image.AFFINE, (1, 0, -4, 0, 1, -3), fillcolor=PAPER)            # misregistered
        img.paste(ImageChops.multiply(blue, pink), (x, y))
        d.rectangle([x - 8, y - 8, x + w + 8, y + h + 8], outline=PINK, width=4)
    def title(img, d):
        f = fit(d, TITLE, HELVC, 64, 600)
        d.text((W // 2 + 4, 292 + 3), TITLE, font=f, fill=PINK, anchor="mm")
        lay = Image.new("RGB", (W, H), (255, 255, 255)); ImageDraw.Draw(lay).text((W // 2, 292), TITLE, font=f, fill=BLUE, anchor="mm")
        img.paste(ImageChops.multiply(img, lay))
        d2 = ImageDraw.Draw(img); d2.text((W // 2, 328), SUB, font=HELV(16), fill=BLUE, anchor="mm")
    return dict(bg=PAPER, neigh=lambda im: riso(im, BLUE), card=card, badges=badges_boxes(PINK, PAPER, HELV(13)), title=title,
                pills=pills_std(HELV(13), BLUE, PAPER, BLUE, BLUE, y=352),
                bottom=bottom_std(None, HELVC(40), PINK, BLUE, HELV(14), BLUE, PAPER, BLUE, a_col=PINK),
                top=top_std(HELV(16), BLUE), post=grain(28))


@style("06", "Monochrome precision", "ManvsMachine")
def s06():
    BG, WHT, ACC = (12, 12, 14), (236, 236, 236), (255, 60, 30)
    def bg(img):
        d = ImageDraw.Draw(img)
        for r in range(40, 700, 46):
            d.ellipse([W // 2 - r, 168 - r, W // 2 + r, 168 + r], outline=(30, 30, 34), width=2)
    def card(img, d, x, y, w, h, im):
        img.paste(im, (x, y)); d.rectangle([x - 2, y - 2, x + w + 2, y + h + 2], outline=WHT, width=2)
        d.rectangle([x - 2, y + h + 6, x + 60, y + h + 10], fill=ACC)
    return dict(bg=BG, paint_bg=bg, neigh=lambda im: ImageOps.grayscale(im).point(lambda v: v // 3).convert("RGB"), card=card,
                badges=badges_boxes(BG, WHT, HELV(12)), title=title_std(HELV, 40, WHT, HELV(14), (140, 140, 140), y=300),
                pills=pills_std(HELV(13), ACC, ACC, (140, 140, 140), None, "underline", y=350),
                bottom=bottom_std(None, HELV(28), WHT, ACC, HELV(14), (40, 40, 44), WHT, (170, 170, 170), a_col=ACC),
                top=top_std(HELV(15), WHT))


@style("07", "Candy gloss", "Psyop")
def s07():
    def bg(img):
        vgrad(img, [(0, (255, 120, 200)), (0.5, (255, 180, 120)), (1, (120, 220, 255))])
        d = ImageDraw.Draw(img)
        for cx, cy, r, c in ((60, 110, 46, (255, 80, 160)), (590, 240, 60, (80, 160, 255)), (560, 80, 22, (255, 230, 80))):
            for k in range(r, 0, -2):
                t = k / r
                d.ellipse([cx - k, cy - k, cx + k, cy + k], fill=lerp((255, 255, 255), c, t ** .6))
            d.ellipse([cx - r * .45, cy - r * .55, cx - r * .05, cy - r * .2], fill=(255, 255, 255))
    def card(img, d, x, y, w, h, im):
        for k in range(14, 0, -2):
            d.rounded_rectangle([x - k, y - k, x + w + k, y + h + k], 20 + k, fill=lerp((255, 255, 255), (255, 90, 170), k / 14))
        m = Image.new("L", (w, h), 0); ImageDraw.Draw(m).rounded_rectangle([0, 0, w - 1, h - 1], 16, fill=255)
        img.paste(im, (x, y), m)
    INK = (120, 20, 90)
    return dict(paint_bg=bg, neigh=lambda im: im, neigh_card=neigh_round(16, (255, 255, 255), 5), card=card,
                badges=badges_boxes((255, 255, 255), INK, SFR(13), rad=11),
                title=title_std(AVB, 42, (255, 255, 255), AVB(15), INK, shadow=INK, soff=3, y=298),
                pills=pills_std(AVB(13), (255, 255, 255), INK, (255, 255, 255), (255, 255, 255), "round", y=350),
                bottom=bottom_std(None, AVB(30), (255, 255, 255), INK, AVB(14), (255, 255, 255), INK, (255, 255, 255), "circle", (255, 230, 80)),
                top=top_std(AVB(17), (255, 255, 255)))


@style("08", "Mid-century flat", "Oddfellows")
def s08():
    TEAL, MUST, CORAL, CREAM, INK = (34, 104, 110), (232, 168, 56), (226, 102, 78), (244, 232, 210), (36, 40, 48)
    def bg(img):
        d = ImageDraw.Draw(img)
        d.rectangle([0, 0, W, 250], fill=TEAL)
        d.pieslice([-120, 120, 260, 500], 180, 360, fill=MUST); d.pieslice([430, 150, 760, 480], 180, 360, fill=CORAL)
        for i in range(8):
            d.line([(40 + i * 14, 40), (40 + i * 14, 90)], fill=CREAM, width=4)
        d.ellipse([560, 30, 610, 80], fill=MUST)
    def card(img, d, x, y, w, h, im):
        d.rounded_rectangle([x - 10, y - 10, x + w + 10, y + h + 10], 30, fill=CREAM)
        m = Image.new("L", (w, h), 0); ImageDraw.Draw(m).rounded_rectangle([0, 0, w - 1, h - 1], 22, fill=255)
        img.paste(im, (x, y), m)
    return dict(bg=CREAM, paint_bg=bg, neigh=lambda im: duo(im, INK, CREAM), neigh_card=neigh_round(16),
                card=card, badges=badges_boxes(CORAL, CREAM, FUTB(13), rad=11), title=title_std(FUTB, 40, INK, FUTB(15), TEAL, y=300),
                pills=pills_std(FUTB(13), TEAL, CREAM, INK, INK, "round", y=350),
                bottom=bottom_std(INK, FUTB(28), CREAM, MUST, FUTB(14), CREAM, INK, CREAM, "circle", CORAL),
                top=top_std(FUTB(16), CREAM))


@style("09", "Warm hand-made", "Giant Ant")
def s09():
    PAPER, INK, RUST, SAGE, SKY = (238, 226, 204), (52, 44, 40), (196, 92, 58), (128, 156, 116), (110, 150, 190)
    def bg(img):
        d = ImageDraw.Draw(img)
        random.seed(5)
        for cx, cy, r, c in ((80, 90, 90, SAGE), (580, 320, 120, SKY), (600, 60, 50, RUST), (40, 400, 70, (220, 180, 120))):
            pts = [(cx + r * (0.85 + random.random() * .3) * math.cos(a / 12 * 2 * math.pi),
                    cy + r * (0.85 + random.random() * .3) * math.sin(a / 12 * 2 * math.pi)) for a in range(12)]
            d.polygon(pts, fill=c)
    def card(img, d, x, y, w, h, im):
        d.polygon([(x - 10, y - 6), (x + w + 8, y - 12), (x + w + 12, y + h + 8), (x - 6, y + h + 12)], fill=PAPER, outline=INK)
        img.paste(im, (x, y))
        d.line([(x - 4, y + h + 4), (x + w + 4, y + h + 2)], fill=INK, width=3)
    return dict(bg=PAPER, paint_bg=bg, neigh=lambda im: duo(im, INK, PAPER), card=card,
                badges=badges_boxes(INK, PAPER, TYPEW(12), rad=6), title=title_std(GEORGIA, 40, INK, TYPEW(15), RUST, y=300, case=tcase),
                pills=pills_std(TYPEW(13), RUST, PAPER, INK, None, "round", y=350, case=tcase),
                bottom=bottom_std(None, GEORGIA(30), INK, RUST, TYPEW(14), INK, PAPER, INK, "round", RUST, case=tcase),
                top=top_std(TYPEW(16), INK, "Wiizard", GEORGIA(22), case=tcase), post=grain(16))


@style("10", "Maximal collage", "Studio Moross")
def s10():
    YEL, PNK, BLU, K = (255, 228, 0), (255, 60, 140), (40, 80, 255), (10, 10, 10)
    def bg(img):
        d = ImageDraw.Draw(img)
        for y in range(0, H, 12):
            for x in range(0, W, 12):
                r = 3 + 2 * math.sin((x + y) / 60)
                d.ellipse([x - r, y - r, x + r, y + r], fill=(255, 140, 190))
        d.polygon([(0, 0), (260, 0), (180, 120), (0, 160)], fill=BLU)
        d.polygon([(460, 260), (W, 220), (W, 400), (520, 420)], fill=YEL)
        star(d, 560, 70, 46, YEL, 12, .7); star(d, 80, 440, 34, BLU, 10, .6)
    def card(img, d, x, y, w, h, im):
        im2 = im.rotate(-4, expand=True, fillcolor=(255, 255, 255))
        d.polygon([(x - 14, y - 10), (x + w + 18, y - 22), (x + w + 22, y + h + 6), (x - 8, y + h + 20)], fill=(255, 255, 255))
        img.paste(im2, (x - 6, y - 12))
        d.rectangle([x + w // 2 - 30, y - 22, x + w // 2 + 30, y - 6], fill=(255, 255, 200))   # tape
    def title(img, d):
        f = fit(d, TITLE, IMPACT, 58, 560)
        lay = Image.new("RGBA", (W, 120)); ld = ImageDraw.Draw(lay)
        ld.text((W // 2 + 4, 64), TITLE, font=f, fill=K, anchor="mm"); ld.text((W // 2, 60), TITLE, font=f, fill=YEL, anchor="mm", stroke_width=2, stroke_fill=K)
        lay = lay.rotate(3, resample=Image.BICUBIC); img.paste(lay, (0, 236), lay)
        d.rectangle([W // 2 - 120, 318, W // 2 + 120, 340], fill=K); d.text((W // 2, 330), SUB, font=HELV(14), fill=(255, 255, 255), anchor="mm")
    return dict(bg=(255, 170, 205), paint_bg=bg, neigh=lambda im: duo(im, BLU, (255, 220, 240)), card=card,
                badges=badges_boxes(PNK, (255, 255, 255), IMPACT(14)), title=title,
                pills=pills_std(IMPACT(15), K, YEL, K, K, "tag", y=352),
                bottom=bottom_std(K, IMPACT(36), YEL, PNK, IMPACT(16), YEL, K, (255, 255, 255), a_col=PNK),
                top=top_std(IMPACT(20), K))


@style("11", "Generative particles", "Universal Everything")
def s11():
    def bg(img):
        d = ImageDraw.Draw(img)
        random.seed(9)
        for i in range(900):
            a = random.random() * math.tau
            r = 120 + random.random() * 260
            x, y = W // 2 + r * math.cos(a) * 1.3, 168 + r * math.sin(a)
            c = lerp((60, 240, 200), (255, 80, 200), (math.sin(a * 3) + 1) / 2)
            s = 1 + (r % 4)
            d.ellipse([x - s, y - s, x + s, y + s], fill=c)
    def card(img, d, x, y, w, h, im):
        for k in (10, 7, 4):
            d.rectangle([x - k, y - k, x + w + k, y + h + k], outline=lerp((60, 240, 200), (255, 80, 200), k / 10), width=2)
        img.paste(im, (x, y))
    return dict(bg=(8, 8, 18), paint_bg=bg, neigh=lambda im: ImageOps.grayscale(im).point(lambda v: v // 2).convert("RGB"), card=card,
                badges=badges_boxes((60, 240, 200), (8, 8, 18), AVB(12), rad=11),
                title=title_std(AVB, 40, (255, 255, 255), AVB(14), (60, 240, 200), y=300),
                pills=pills_std(AVB(13), (255, 80, 200), (255, 255, 255), (200, 200, 220), None, "round", y=350),
                bottom=bottom_std(None, AVB(28), (255, 255, 255), (60, 240, 200), AVB(14), (40, 40, 70), (255, 255, 255), (200, 200, 220), "circle", (255, 80, 200)),
                top=top_std(AVB(16), (255, 255, 255)))


@style("12", "Cinematic title", "Imaginary Forces")
def s12():
    GOLD, BG = (214, 182, 120), (6, 6, 8)
    def bg(img):
        d = ImageDraw.Draw(img)
        d.rectangle([0, 0, W, 54], fill=(0, 0, 0)); d.rectangle([0, H - 54, W, H], fill=(0, 0, 0))
        vgrad(img, [(0, (6, 6, 8)), (0.5, (30, 22, 18)), (1, (6, 6, 8))], (0, 54, W, H - 54))
    def card(img, d, x, y, w, h, im):
        img.paste(ImageOps.autocontrast(im), (x, y))
        d.line([(x - 30, y + h + 14), (x + w + 30, y + h + 14)], fill=GOLD, width=1)
    def title(img, d):
        f = fit(d, "Street Fighter II", DIDOT, 44, 600)
        d.text((W // 2, 302), "Street Fighter II", font=f, fill=(240, 232, 220), anchor="mm")
        d.text((W // 2, 334), "1 9 9 2   ·   C A P C O M", font=COPPER(14), fill=GOLD, anchor="mm")
    return dict(paint_bg=bg, neigh=lambda im: ImageOps.grayscale(im).point(lambda v: v // 3).convert("RGB"), card=card,
                badges=badges_boxes(BG, GOLD, COPPER(12)), title=title,
                pills=pills_std(COPPER(13), GOLD, GOLD, (130, 120, 110), None, "underline", y=356),
                bottom=bottom_std(None, DIDOT(26), (240, 232, 220), GOLD, COPPER(13), (40, 34, 30), GOLD, (170, 160, 150), "circle", None, y=414, case=tcase),
                top=top_std(COPPER(15), GOLD, "W I I Z A R D"))


@style("13", "Swiss grid", "Animade")
def s13():
    RED, K, WH = (230, 30, 30), (16, 16, 16), (245, 245, 240)
    def bg(img):
        d = ImageDraw.Draw(img)
        for x in range(0, W, 80):
            d.line([(x, 0), (x, H)], fill=(225, 225, 220), width=1)
        d.rectangle([0, 0, 20, H], fill=RED)
        d.text((620, 120), "03", font=HELV(110), fill=RED, anchor="rs")
    def card(img, d, x, y, w, h, im):
        img.paste(im, (x, y)); d.rectangle([x, y + h, x + w, y + h + 6], fill=RED)
    def title(img, d):
        d.text((40, 300), "Street Fighter II'", font=HELV(42), fill=K, anchor="lm")
        d.text((40, 334), "1992 — Capcom — CPS-1 — 2 players", font=HELV(15), fill=RED, anchor="lm")
    return dict(bg=WH, paint_bg=bg, neigh=lambda im: ImageOps.grayscale(im).convert("RGB"), card=card,
                badges=badges_boxes(K, WH, HELV(12)), title=title,
                pills=pills_std(HELV(13), K, WH, K, None, "rect", y=356, case=tcase),
                bottom=bottom_std(K, HELV(30), WH, RED, HELV(14), WH, K, WH, a_col=RED, case=tcase),
                top=top_std(HELV(16), K, "Wiizard", case=tcase))


@style("14", "Papercraft", "Nexus Studios")
def s14():
    def layer(img, pts, col, off=6):
        d = ImageDraw.Draw(img)
        d.polygon([(x + off, y + off) for x, y in pts], fill=tuple(int(c * .55) for c in col))
        d.polygon(pts, fill=col)
    def bg(img):
        def hill(y0, amp, col, ph):
            pts = [(x, y0 + amp * math.sin(x / 90 + ph)) for x in range(-20, W + 40, 20)] + [(W + 40, H), (-20, H)]
            layer(img, pts, col)
        hill(120, 18, (170, 210, 230), 0); hill(200, 24, (120, 180, 150), 1.4); hill(300, 20, (90, 150, 110), 2.8); hill(400, 14, (60, 110, 80), .5)
        d = ImageDraw.Draw(img); d.ellipse([540, 24, 600, 84], fill=(255, 220, 120))
    def card(img, d, x, y, w, h, im):
        d.rectangle([x - 10 + 8, y - 10 + 8, x + w + 10 + 8, y + h + 10 + 8], fill=(40, 60, 50))
        d.rectangle([x - 10, y - 10, x + w + 10, y + h + 10], fill=(250, 246, 236))
        img.paste(im, (x, y))
    INK = (40, 50, 44)
    def neigh_card(img, d, x, y, w, h, im):
        d.rectangle([x - 6 + 6, y - 6 + 6, x + w + 6 + 6, y + h + 6 + 6], fill=(40, 60, 50))
        d.rectangle([x - 6, y - 6, x + w + 6, y + h + 6], fill=(250, 246, 236)); img.paste(im, (x, y))
    def title(img, d):
        d.rectangle([110, 270, 530, 340], fill=(250, 246, 236)); d.rectangle([116, 276, 536, 346], outline=INK)
        f = fit(d, TITLE, AVC, 40, 400)
        d.text((W // 2, 296), TITLE, font=f, fill=INK, anchor="mm"); d.text((W // 2, 326), SUB, font=AVB(13), fill=(90, 150, 110), anchor="mm")
    return dict(bg=(210, 232, 240), paint_bg=bg, neigh=lambda im: im, neigh_card=neigh_card, card=card,
                badges=badges_boxes(INK, (250, 246, 236), AVB(12)), title=title,
                pills=pills_std(AVB(13), (250, 246, 236), INK, (250, 246, 236), (250, 246, 236), "rect", y=356),
                bottom=bottom_std((40, 60, 50), AVC(30), (250, 246, 236), (255, 220, 120), AVB(13), (250, 246, 236), INK, (250, 246, 236), a_col=(255, 220, 120)),
                top=top_std(AVB(16), INK))


@style("15", "Bauhaus / Memphis", "Ordinary Folk")
def s15():
    R, Y, B, K, CR = (232, 64, 52), (250, 200, 30), (36, 84, 196), (18, 18, 18), (246, 238, 222)
    def bg(img):
        d = ImageDraw.Draw(img)
        d.pieslice([-80, -80, 160, 160], 0, 90, fill=Y); d.rectangle([560, 0, W, 120], fill=B)
        d.polygon([(0, 260), (90, 230), (60, 340)], fill=R); d.ellipse([580, 250, 660, 330], fill=R)
        for i in range(6):
            d.arc([470 + i * 16, 140, 500 + i * 16, 170], 180 if i % 2 else 0, 360 if i % 2 else 180, fill=K, width=4)
        for x, y in ((40, 200), (590, 190), (30, 380), (610, 380)):
            d.rectangle([x, y, x + 6, y + 6], fill=K)
    def card(img, d, x, y, w, h, im):
        d.rectangle([x - 8, y - 8, x + w + 8, y + h + 8], fill=K); img.paste(im, (x, y))
        d.ellipse([x + w - 14, y - 18, x + w + 18, y + 14], fill=Y)
    return dict(bg=CR, paint_bg=bg, neigh=lambda im: duo(im, B, CR), card=card,
                badges=badges_boxes(R, CR, FUTB(13)), title=title_std(FUTB, 42, K, FUTB(15), R, y=300),
                pills=pills_std(FUTB(13), B, CR, K, K, "rect", y=352),
                bottom=bottom_std(K, FUTB(28), Y, R, FUTB(14), CR, K, CR, "circle", R),
                top=top_std(FUTB(16), K))


@style("16", "Art deco arcade", "Elastic")
def s16():
    GOLD, K, CREAM = (212, 175, 90), (10, 12, 20), (240, 228, 200)
    def bg(img):
        d = ImageDraw.Draw(img)
        for i in range(0, 19):
            a = math.radians(180 + i * 10)
            d.line([(W // 2, 470), (W // 2 + 700 * math.cos(a), 470 + 700 * math.sin(a))], fill=(34, 32, 30), width=3)
        for r in (120, 200, 280):
            d.arc([W // 2 - r * 2, 470 - r * 2, W // 2 + r * 2, 470 + r * 2], 180, 360, fill=(48, 42, 30), width=2)
    def card(img, d, x, y, w, h, im):
        d.rectangle([x - 10, y - 10, x + w + 10, y + h + 10], outline=GOLD, width=2)
        d.rectangle([x - 5, y - 5, x + w + 5, y + h + 5], outline=GOLD, width=1)
        for cx, cy in ((x - 10, y - 10), (x + w + 10, y - 10), (x - 10, y + h + 10), (x + w + 10, y + h + 10)):
            d.polygon([(cx, cy - 7), (cx + 7, cy), (cx, cy + 7), (cx - 7, cy)], fill=GOLD)
        img.paste(im, (x, y))
    return dict(bg=K, paint_bg=bg, neigh=lambda im: duo(im, K, GOLD), card=card,
                badges=badges_boxes(K, GOLD, COPPER(12)), title=title_std(COPPER, 34, CREAM, COPPER(14), GOLD, y=302),
                pills=pills_std(COPPER(12), GOLD, K, GOLD, GOLD, "rect", y=354),
                bottom=bottom_std(None, COPPER(24), CREAM, GOLD, COPPER(12), GOLD, K, CREAM, "circle", None),
                top=top_std(COPPER(15), GOLD))


@style("17", "Brutalist type", "DIA")
def s17():
    K, WH, ACC = (0, 0, 0), (255, 255, 255), (0, 255, 120)
    def bg(img):
        d = ImageDraw.Draw(img)
        lay = Image.new("RGB", (W, 260), K); ld = ImageDraw.Draw(lay)
        ld.text((W // 2, 130), "FIGHT", font=HELVC(260), fill=(40, 40, 40), anchor="mm")
        img.paste(lay.resize((W, 300)), (0, 20))
    def card(img, d, x, y, w, h, im):
        img.paste(im, (x, y)); d.rectangle([x, y, x + w, y + h], outline=ACC, width=3)
    def title(img, d):
        f = fit(d, TITLE, HELVC, 74, 620)
        lay = Image.new("RGBA", (W, 90)); ImageDraw.Draw(lay).text((W // 2, 45), TITLE, font=f, fill=WH, anchor="mm")
        lay = lay.resize((W, 70)); img.paste(lay, (0, 262), lay)
        d.text((W // 2, 334), SUB, font=HELV(14), fill=ACC, anchor="mm")
    return dict(bg=K, paint_bg=bg, neigh=lambda im: ImageOps.grayscale(im).convert("RGB"), card=card,
                badges=badges_boxes(ACC, K, HELV(12)), title=title,
                pills=pills_std(HELVC(15), WH, K, WH, None, "rect", y=354),
                bottom=bottom_std(None, HELVC(46), WH, ACC, HELV(13), WH, K, WH, a_col=ACC),
                top=top_std(HELV(15), WH))


@style("18", "70s sunset stripes", "Sarofsky")
def s18():
    BR, OR, MU, CR, RD = (70, 40, 30), (236, 112, 40), (232, 176, 60), (246, 230, 200), (196, 60, 40)
    def bg(img):
        d = ImageDraw.Draw(img)
        for i, c in enumerate((RD, OR, MU, (240, 210, 130))):
            d.rectangle([0, 230 + i * 26, W, 256 + i * 26], fill=c)
        d.ellipse([W // 2 - 190, 40, W // 2 + 190, 420], fill=None, outline=None)
        for i, c in enumerate((RD, OR, MU)):
            d.arc([-160 - i * 30, 300 - i * 30, 220 + i * 30, 680 + i * 30], 270, 360, fill=c, width=24)
    def card(img, d, x, y, w, h, im):
        d.rounded_rectangle([x - 10, y - 10, x + w + 10, y + h + 10], 26, fill=BR)
        m = Image.new("L", (w, h), 0); ImageDraw.Draw(m).rounded_rectangle([0, 0, w - 1, h - 1], 18, fill=255)
        img.paste(im, (x, y), m)
    def title(img, d):
        f = fit(d, TITLE, GILL, 42, 600)
        d.text((W // 2 + 3, 300 + 3), TITLE, font=f, fill=BR, anchor="mm"); d.text((W // 2, 300), TITLE, font=f, fill=CR, anchor="mm")
        d.text((W // 2, 332), SUB, font=GILL(15), fill=BR, anchor="mm")
    return dict(bg=CR, paint_bg=bg, neigh=lambda im: duo(im, BR, MU), neigh_card=neigh_round(14, BR, 5), card=card,
                badges=badges_boxes(OR, CR, GILL(13), rad=11), title=title,
                pills=pills_std(GILL(13), BR, CR, BR, None, "round", y=352),
                bottom=bottom_std(BR, GILL(28), CR, MU, GILL(14), CR, BR, CR, "circle", OR),
                top=top_std(GILL(17), BR))


@style("19", "Y2K chrome", "Hornet")
def s19():
    def bg(img):
        vgrad(img, [(0, (20, 30, 90)), (0.5, (120, 60, 200)), (1, (20, 180, 220))])
        d = ImageDraw.Draw(img)
        for i in range(-10, 20):
            d.line([(i * 50, H), (W // 2, 200)], fill=(140, 210, 255), width=1)
        for y in range(260, H, 22):
            d.line([(0, y), (W, y)], fill=(140, 210, 255), width=1)
    def chrome(d, s, f, cx, cy):
        lay = Image.new("RGBA", (W, 100)); ld = ImageDraw.Draw(lay)
        ld.text((W // 2, 50), s, font=f, fill=(255, 255, 255), anchor="mm")
        grad = Image.new("RGB", (W, 100)); vgrad_local = ImageDraw.Draw(grad)
        for y in range(100):
            t = y / 99
            vgrad_local.line([(0, y), (W, y)], fill=lerp((255, 255, 255), (90, 110, 160), t * 2) if t < .5 else lerp((40, 50, 90), (230, 240, 255), (t - .5) * 2))
        return lay, grad
    def title(img, d):
        f = fit(d, TITLE, AVB, 46, 600)
        lay, grad = chrome(d, TITLE, f, W // 2, 300)
        sh = Image.new("RGBA", (W, 100)); ImageDraw.Draw(sh).text((W // 2 + 2, 52), TITLE, font=f, fill=(20, 10, 60), anchor="mm", stroke_width=3, stroke_fill=(20, 10, 60))
        img.paste(sh, (0, 250), sh); img.paste(grad, (0, 250), lay)
        ImageDraw.Draw(img).text((W // 2, 334), SUB, font=AVB(14), fill=(200, 240, 255), anchor="mm")
    def card(img, d, x, y, w, h, im):
        for k in range(10, 0, -1):
            d.rounded_rectangle([x - k, y - k, x + w + k, y + h + k], 14 + k, fill=lerp((90, 240, 255), (255, 120, 240), k / 10))
        m = Image.new("L", (w, h), 0); ImageDraw.Draw(m).rounded_rectangle([0, 0, w - 1, h - 1], 12, fill=255)
        img.paste(im, (x, y), m)
    return dict(paint_bg=bg, neigh=lambda im: im.point(lambda v: v * 2 // 3), neigh_card=neigh_round(12, (140, 210, 255), 3), card=card,
                badges=badges_boxes((255, 120, 240), (20, 10, 60), AVB(12), rad=11), title=title,
                pills=pills_std(AVB(13), (255, 255, 255), (60, 30, 140), (220, 240, 255), (220, 240, 255), "round", y=354),
                bottom=bottom_std(None, AVB(28), (255, 255, 255), (90, 240, 255), AVB(14), (255, 255, 255), (60, 30, 140), (220, 240, 255), "circle", (255, 120, 240)),
                top=top_std(AVB(16), (255, 255, 255)))


@style("20", "80s arcade flyer", "after Japanese arcade flyers / Tendril-style energy")
def s20():
    K, Y, R, CY, WH = (14, 10, 30), (255, 220, 0), (255, 40, 60), (0, 210, 255), (255, 255, 255)
    def bg(img):
        d = ImageDraw.Draw(img)
        cx, cy = W // 2, 168
        for i in range(36):
            a0, a1 = math.radians(i * 10), math.radians(i * 10 + 5)
            d.polygon([(cx, cy), (cx + 900 * math.cos(a0), cy + 900 * math.sin(a0)), (cx + 900 * math.cos(a1), cy + 900 * math.sin(a1))], fill=(40, 20, 70))
        star(d, 70, 90, 50, Y, 12, .55); star(d, 590, 260, 40, R, 10, .55)
    def card(img, d, x, y, w, h, im):
        star(d, x + w // 2, y + h // 2, w * .72, Y, 16, .82)
        d.rectangle([x - 6, y - 6, x + w + 6, y + h + 6], fill=K); img.paste(im, (x, y))
    def title(img, d):
        f = fit(d, TITLE, IMPACT, 60, 600)
        lay = Image.new("RGBA", (W, 100)); ld = ImageDraw.Draw(lay)
        ld.text((W // 2, 50), TITLE, font=f, fill=Y, anchor="mm", stroke_width=6, stroke_fill=R)
        lay = lay.transform((W, 100), Image.AFFINE, (1, 0.18, -9, 0, 1, 0), resample=Image.BICUBIC)
        img.paste(lay, (0, 250), lay)
        ImageDraw.Draw(img).text((W // 2, 334), SUB, font=IMPACT(16), fill=CY, anchor="mm")
    return dict(bg=K, paint_bg=bg, neigh=lambda im: im.point(lambda v: v // 2), card=card,
                badges=badges_boxes(R, WH, IMPACT(15)), title=title,
                pills=pills_std(IMPACT(15), Y, K, WH, CY, "tag", y=356),
                bottom=bottom_std(R, IMPACT(36), Y, WH, IMPACT(16), Y, K, WH, a_col=CY),
                top=top_std(IMPACT(20), Y))


# ---------------------------------------------------------------- render + sheets
def main():
    done = []
    for key, name, ref, fn in S:
        img = draw_menu(fn())
        fn_out = os.path.join(OUT, f"{key}-{name.lower().replace(' / ', '-').replace(' ', '-')}.jpg")
        done.append((key, name, ref, crt(img, fn_out)))
        print(key, name)

    LAB = HELV(22)
    for part in (0, 1):
        items = done[part * 10:(part + 1) * 10]
        tw_, th_ = 640, 480
        sheet = Image.new("RGB", (tw_ * 2, (th_ + 40) * 5), (255, 255, 255))
        d = ImageDraw.Draw(sheet)
        for i, (key, name, ref, im) in enumerate(items):
            x, y = (i % 2) * tw_, (i // 2) * (th_ + 40)
            d.text((x + 10, y + 8), f"{key}  {name}  —  {ref}", font=LAB, fill=(20, 20, 20))
            sheet.paste(im.resize((tw_, th_)), (x, y + 40))
        sheet.save(os.path.join(HERE, f"explore-sheet-{part + 1}.jpg"), quality=85)
    print("sheets ok")



if __name__ == "__main__":
    main()
