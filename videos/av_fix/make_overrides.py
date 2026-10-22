#!/usr/bin/env python3
"""Per-game RetroArch overrides for a sharp, correctly shaped picture on the cabs' 4:3 CRTs (240p).
Reads videos/geometry.json (native size, aspect, rotation per arcade game) and the current overrides in
sdkit/retroarch/config, writes the merged files to av_fix/proposed/retroarch/config/<core name>/<rom>.cfg.
Rules (see findings.md):
  horizontal, 224 or 240 lines: framebuffer = 2x (or 1x) the native width at the native height (exact integer
      scale, no stretching of lines); the VI widens it to video_viwidth (global 664 = 4:3 for a 224-line picture,
      704 here for 240-line games).
  horizontal, other heights: framebuffer at 240 lines, custom viewport, bilinear for the vertical squeeze.
  vertical (3:4): 640x240 framebuffer, custom viewport 384x240 (x 664/640 by the VI = 398 of 711 samples = 3:4
      at 240 lines), bilinear (256/288/320/384 lines -> 240 can't be integer)."""
import json, os, re
HERE = os.path.dirname(os.path.abspath(__file__)); WII = os.path.abspath(os.path.join(HERE, "../.."))
GEOM = json.load(open(os.path.join(WII, "videos/geometry.json")))
# games that moved core since geometry.json was made (arcade.tsv is the truth; geometry from the sim's RetroArch log)
GEOM["dkong3"] = {"core": "mame2000", "geom": ["224", "256", "0.7500", "0"]}
GEOM["atetris"] = {"core": "mame2000", "geom": ["336", "240", "1.3333", "0"]}
SRC = os.path.join(WII, "sdkit/retroarch/config"); OUT = os.environ.get("OUT", os.path.join(HERE, "proposed/retroarch/config"))
CORE_DIR = {"fbalpha2012": "FB Alpha 2012", "fbalpha2012_cps1": "FB Alpha 2012 CPS-1",
            "fbalpha2012_cps2": "FB Alpha 2012 CPS-2", "fbalpha2012_neogeo": "FB Alpha 2012 Neo Geo",
            "mame2000": "MAME 2000"}
RES = [(0, 0), (512, 192), (598, 200), (640, 200), (384, 224), (448, 224), (480, 224), (512, 224), (576, 224),
       (608, 224), (640, 224), (340, 232), (512, 232), (512, 236), (336, 240), (352, 240), (384, 240), (512, 240),
       (530, 240), (608, 240), (640, 240), (512, 384), (598, 400), (640, 400), (384, 448), (448, 448), (480, 448),
       (512, 448), (576, 448), (608, 448), (640, 448), (340, 464), (512, 464), (512, 472), (352, 480), (384, 480),
       (512, 480), (530, 480), (608, 480), (640, 480)]          # gx_gfx.c menu_gx_resolutions = current_resolution_id
VERT_H = 210
LINE_PER_SAMPLE = 213.6 * 4 / 3 / 634       # cab1: screen = 99 89 -> 634 samples x 213.6 lines visible, physically 4:3
KEYS = ("video_aspect_ratio_auto", "current_resolution_id", "aspect_ratio_index", "custom_viewport_width", "custom_viewport_height",
        "custom_viewport_x", "custom_viewport_y", "video_smooth", "video_viwidth")


def rid(w, h):
    return RES.index((w, h)) if (w, h) in RES else None


def vertical_settings(w, h):
    """3:4 picture inside cab1's calibrated visible area: VERT_H lines (bilinear from the game's h), the game's own
    width 1:1 in a 336x240 framebuffer (columns stay exact), and the VI widens it to the 3:4 width. The 4:3 visible
    area of cab1 is 634 samples x 213.6 lines, so one line = 1/0.4492 samples of width. gx_resize moves the
    viewport offset into the VI origin in samples (not fb pixels); custom_viewport_x is solved for that so the
    picture is centred on sample 360."""
    fbw = 336 if w <= 336 else 384
    target = 0.75 * VERT_H / LINE_PER_SAMPLE                  # 3:4 width in samples
    vi = int(round(fbw * target / w / 2)) * 2
    xo = (720 - vi) // 2; pos = 720 - vi - xo                 # VI origin, and how far gx may push it right
    start = 360 - target / 2
    need = start - xo
    x_total = need if need <= pos else pos + (need - pos) * fbw / vi
    cx = int(round(x_total - (fbw - w) / 2))
    assert cx >= 0, (w, h, cx)
    return {"current_resolution_id": str(rid(fbw, 240)), "aspect_ratio_index": "23",
            "custom_viewport_width": str(w), "custom_viewport_height": str(VERT_H), "custom_viewport_x": str(cx),
            "custom_viewport_y": "0", "video_smooth": "true", "video_viwidth": str(vi)}, \
        f"vertical 3:4: {w} columns 1:1 in {fbw}x240, {h}->{VERT_H} lines bilinear, VI {vi} = {target:.0f} samples"


# 2026-10-21: horizontal games use a custom viewport covering the whole framebuffer (aspect_ratio_index 23), not
# "4:3" (index 0). RetroArch's GX driver letterboxes index 0 against the Wii's own aspect setting; cab1's SYSCONF says
# 16:9 (IPL.AR=1), so every 4:3 game came out at 75% width and shifted right (gx_resize moves the offset into the VI
# origin). A custom viewport ignores that setting. Width on the tube follows the real board's dot clock, as a MiSTer
# outputs it (VI samples at 13.5 MHz: samples = pixels * 13.5 / dot clock MHz): CPS-1/CPS-2 384 px at 8 MHz = 648,
# Neo Geo at 6 MHz: 304 px = 684, 320 px = 720, SNES/NES/Mega Drive = 644 (47.7 us). Other boards keep the 4:3
# estimate (664 at 224 lines, 704 at 240). One resample only: the VI's own horizontal scaler (video_smooth off).
DOT_MHZ = {"FB Alpha 2012 CPS-1": 8.0, "FB Alpha 2012 CPS-2": 8.0, "FB Alpha 2012 Neo Geo": 6.0}
CUR_CORE = [None]


def settings(w, h, aspect, rot):
    vertical = aspect < 1
    if vertical:
        return vertical_settings(w, h)
    if h in (224, 240):
        clk = DOT_MHZ.get(CUR_CORE[0])
        vi = min(720, int(round(w * 13.5 / clk / 2)) * 2) if clk else (704 if h == 240 else 664)
        for k in (2, 1):
            i = rid(k * w, h)
            if i is not None and k * w <= min(640, vi):
                d = {"current_resolution_id": str(i), "aspect_ratio_index": "23", "video_aspect_ratio_auto": "false",
                     "custom_viewport_width": str(k * w), "custom_viewport_height": str(h), "custom_viewport_x": "0",
                     "custom_viewport_y": "0", "video_smooth": "false", "video_viwidth": str(vi)}
                return d, f"{k}x1 into {k*w}x{h}, VI {vi} samples, custom viewport (ignores the Wii's 16:9 setting)"
    if h == 480 and rid(w, 480) is not None:
        return {"current_resolution_id": str(rid(w, 480)), "aspect_ratio_index": "23", "video_aspect_ratio_auto": "false",
                "custom_viewport_width": str(w), "custom_viewport_height": "480", "custom_viewport_x": "0",
                "custom_viewport_y": "0", "video_smooth": "false",
                "video_viwidth": "704"}, f"1x1 into {w}x480 (480i)"
    k = 2 if 2 * w <= 640 else 1
    i = rid(k * w, 240)
    return {"current_resolution_id": str(i), "aspect_ratio_index": "23", "custom_viewport_width": str(k * w),
            "custom_viewport_height": "240", "custom_viewport_x": "0", "custom_viewport_y": "0",
            "video_smooth": "true", "video_viwidth": "704"}, f"{k}x into {k*w}x240, {h}->240 lines bilinear"


def main():
    rows = []
    for rom, v in sorted(GEOM.items()):
        w, h, aspect, rot = int(v["geom"][0]), int(v["geom"][1]), float(v["geom"][2]), int(v["geom"][3])
        cd = CORE_DIR[v["core"]]
        CUR_CORE[0] = cd
        d, why = settings(w, h, aspect, rot)
        src = os.path.join(SRC, cd, rom + ".cfg")
        lines = [l for l in open(src).read().splitlines()] if os.path.exists(src) else []
        keep = [l for l in lines if not (l.startswith("#") or any(re.match(rf"\s*{k}\s*=", l) for k in KEYS))]
        out = [f"# picture for a 4:3 CRT at 240p ({w}x{h} native, {why}); av_fix 2026-10-17"] + keep + \
              [f'{k} = "{val}"' for k, val in d.items()]
        os.makedirs(os.path.join(OUT, cd), exist_ok=True)
        open(os.path.join(OUT, cd, rom + ".cfg"), "w").write("\n".join(out) + "\n")
        rows.append(f"{rom}\t{cd}\t{w}x{h}\t{why}")
    for cd, rid_, why in (("Snes9x 2010", "7", "SNES 256x224 -> 512x224"), ("FCEUmm", "7", "NES 256x224 -> 512x224"),
                          ("Genesis Plus GX", "10", "Mega Drive H40 320x224 -> 640x224 (H32 256 games: 2.5x)")):
        src = os.path.join(SRC, cd, cd + ".cfg")
        keep = [l for l in open(src).read().splitlines() if not (l.startswith("#") or any(re.match(rf"\s*{k}\s*=", l) for k in KEYS))] if os.path.exists(src) else []
        fbw = 640 if rid_ == "10" else 512
        d = {"current_resolution_id": rid_, "aspect_ratio_index": "23", "video_aspect_ratio_auto": "false",
             "custom_viewport_width": str(fbw), "custom_viewport_height": "224", "custom_viewport_x": "0",
             "custom_viewport_y": "0", "video_smooth": "false", "video_viwidth": "644"}
        out = [f"# consoles at native lines, 2x width, the VI widens it to 644 samples = the real console's active line ({why}); av_fix 2026-10-17"] + keep + [f'{k} = "{v}"' for k, v in d.items()]
        os.makedirs(os.path.join(OUT, cd), exist_ok=True)
        open(os.path.join(OUT, cd, cd + ".cfg"), "w").write("\n".join(out) + "\n")
        rows.append(f"{cd}\t(core)\t{why}")
    open(os.path.join(HERE, "proposed/overrides.tsv"), "w").write("\n".join(rows) + "\n")
    print(len(rows), "overrides ->", OUT)


if __name__ == "__main__":
    main()
