#!/usr/bin/env python3
"""What a 4:3 NTSC CRT shows for a Wii XFB frame: the VI places fbWidth XFB pixels over viWidth samples of the
13.5 MHz line (its filtered horizontal scaler when fbWidth < viWidth), the 4:3 picture is 710.85 samples wide
(BT.601: 52.656 us), and a 240p line is 1/240 of the height. Output: a 960x720 (4:3) image of the full raster.
    crtview.py <xfb.png> <out.png> --vi 640 [--lines 240] [--yorigin 0] [--x0 <VI start sample, default centred>]"""
import argparse
from PIL import Image

ACTIVE = 710.85          # 4:3 active width in 13.5 MHz samples


def crt(img, vi, lines=240, yorigin=0, x0=None, W=960, H=720):
    fbw, fbh = img.size
    if x0 is None:
        x0 = (720 - vi) / 2
    out = Image.new("RGB", (W, H))
    px_per_sample = W / ACTIVE
    left = (x0 - (720 - ACTIVE) / 2) * px_per_sample            # picture start on the 960-wide raster
    width = vi * px_per_sample
    line_h = H / 240.0
    # the VI's own scaler is a filtered one (polyphase FCT taps); bicubic stands in for it here
    scaled = img.resize((round(width), round(fbh * line_h)), Image.BICUBIC if vi != fbw else Image.NEAREST)
    # keep scanline-ish rows sharp vertically: redo the vertical with nearest from the horizontally scaled image
    hs = img.resize((round(width), fbh), Image.BICUBIC if vi != fbw else Image.NEAREST)
    scaled = hs.resize((round(width), round(fbh * line_h)), Image.NEAREST)
    out.paste(scaled, (round(left), round(yorigin * line_h)))
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("src"); ap.add_argument("out")
    ap.add_argument("--vi", type=float, default=640); ap.add_argument("--yorigin", type=float, default=0)
    ap.add_argument("--x0", type=float, default=None)
    a = ap.parse_args()
    crt(Image.open(a.src).convert("RGB"), a.vi, yorigin=a.yorigin, x0=a.x0).save(a.out)
