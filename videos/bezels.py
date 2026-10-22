#!/usr/bin/env python3
"""Bezel art for the vertical arcade games (Pac-Man, Galaga, Donkey Kong...), so the black side bars show the
game's flyer and marquee instead. RetroArch overlays, one per game, switched on by a per-game override:
  sdkit/retroarch/overlays/bezels/<stem>.png + .cfg   -> sd:/retroarch/overlays/bezels/
  sdkit/retroarch/config/<core name>/<stem>.cfg      -> sd:/retroarch/config/ (rgui_config_directory)
The picture of a 3:4 game on a 4:3 CRT is 56.25% of the width, centred: x 140..500 of 640. The overlay is drawn on
top of the game, so the middle stays fully transparent (with 2 px to spare each side).
    bezels.py   (vertical games from geometry.json, made by probing each game in its core)"""
import json
import os
from PIL import Image, ImageDraw, ImageFilter, ImageEnhance

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "sdkit", "retroarch")
CORE_NAMES = {"fbalpha2012": "FB Alpha 2012", "fbalpha2012_cps1": "FB Alpha 2012 CPS-1",
              "fbalpha2012_cps2": "FB Alpha 2012 CPS-2", "fbalpha2012_neogeo": "FB Alpha 2012 Neo Geo",
              "mame2000": "MAME 2000"}
W, H = 640, 480
HOLE = (138, 502)                            # transparent columns


def media(kind, stem):
    for plat in ("arcade", "neogeo"):
        p = os.path.join(HERE, "scraped", plat, "media", kind, stem + ".png")
        if os.path.exists(p):
            return Image.open(p).convert("RGBA")
    return None


def fit(im, w, h):
    im = im.copy()
    im.thumbnail((w, h), Image.LANCZOS)
    return im


def bezel(stem):
    flyer, marquee = media("covers", stem), media("marquees", stem)
    shot = media("screenshots", stem)
    base = flyer or shot
    canvas = Image.new("RGBA", (W, H), (12, 14, 20, 255))
    if base:                                 # blurred, dark full-bleed backdrop
        bg = base.convert("RGB").resize((W, int(W * base.height / base.width)), Image.LANCZOS)
        bg = bg.crop((0, (bg.height - H) // 2, W, (bg.height - H) // 2 + H)) if bg.height >= H else bg.resize((W, H))
        bg = ImageEnhance.Brightness(bg.filter(ImageFilter.GaussianBlur(14))).enhance(0.35)
        canvas.paste(bg.convert("RGBA"), (0, 0))
    side_w = HOLE[0] - 16
    if flyer:                                # left: the flyer
        f = fit(flyer, side_w, H - 60)
        canvas.alpha_composite(f, ((HOLE[0] - f.width) // 2, (H - f.height) // 2))
    right = marquee.rotate(90, expand=True) if marquee else (flyer.transpose(Image.FLIP_LEFT_RIGHT) if flyer else None)
    if right:                                # right: the marquee, turned to run down the side
        r = fit(right, side_w, H - 40)
        canvas.alpha_composite(r, (HOLE[1] + (W - HOLE[1] - r.width) // 2, (H - r.height) // 2))
    d = ImageDraw.Draw(canvas)
    for i, a in enumerate((140, 90, 50)):    # soft edge toward the game
        d.line([(HOLE[0] - 1 - i, 0), (HOLE[0] - 1 - i, H)], fill=(0, 0, 0, a))
        d.line([(HOLE[1] + i, 0), (HOLE[1] + i, H)], fill=(0, 0, 0, a))
    d.rectangle([HOLE[0], 0, HOLE[1] - 1, H], fill=(0, 0, 0, 0))
    return canvas, bool(flyer or marquee)


def main():
    geo = json.load(open(os.path.join(HERE, "geometry.json")))
    vertical = {k: v for k, v in geo.items() if float(v["geom"][2]) < 1}
    odir = os.path.join(OUT, "overlays", "bezels")
    os.makedirs(odir, exist_ok=True)
    made, plain = 0, []
    for stem, v in sorted(vertical.items()):
        im, has_art = bezel(stem)
        im.save(os.path.join(odir, stem + ".png"), optimize=True)   # plain RGBA: what RetroArch's PNG reader surely takes
        open(os.path.join(odir, stem + ".cfg"), "w").write(
            f'overlays = 1\noverlay0_overlay = "{stem}.png"\noverlay0_full_screen = true\noverlay0_normalized = true\n'
            f'overlay0_descs = 0\n')
        cdir = os.path.join(OUT, "config", CORE_NAMES[v["core"]])
        os.makedirs(cdir, exist_ok=True)
        open(os.path.join(cdir, stem + ".cfg"), "w").write(
            f'input_overlay_enable = "true"\ninput_overlay = "sd:/retroarch/overlays/bezels/{stem}.cfg"\n'
            f'input_overlay_opacity = "1.000000"\ninput_overlay_scale = "1.000000"\ninput_overlay_auto_scale = "false"\n'
            f'input_overlay_hide_in_menu = "false"\ninput_overlay_show_inputs = "0"\n')
        made += 1
        if not has_art:
            plain.append(stem)
    print(made, "bezels;", "no art (plain dark sides):", plain)


if __name__ == "__main__":
    main()
