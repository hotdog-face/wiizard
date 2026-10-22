# Mitchell's own 2017 wizards (Desktop/wizards/wizards (1).psd), cut out of the composite by keying the grey canvas.
# Saves each finished design as a transparent PNG: wiz1 (blue starry), wiz2 (outlined), wiz3/4 (teal, dark coat).
import os
from PIL import Image, ImageFilter
HERE = os.path.dirname(os.path.abspath(__file__))
PSD = os.path.expanduser("~/Desktop/wizards/wizards (1).psd")
im = Image.open(PSD).convert("RGB").crop((2050, 300, 3150, 700))
BG = (122, 122, 122)
def key(c):
    return max(abs(a - b) for a, b in zip(c, BG)) <= 3
rgba = im.convert("RGBA")
px = rgba.load()
for y in range(im.height):
    for x in range(im.width):
        c = px[x, y]
        if key(c[:3]):
            px[x, y] = (0, 0, 0, 0)
        elif all(abs(c[i] - c[0]) < 6 for i in range(3)) and 70 < c[0] < 118 and y > 300:   # the floor shadow under the feet
            px[x, y] = (0, 0, 0, 0)
for name, (x0, x1) in (("wiz1", (30, 215)), ("wiz2", (420, 590)), ("wiz3", (600, 760))):
    part = rgba.crop((x0, 0, x1, 400))
    part = part.crop(part.getbbox())
    part.save(os.path.join(HERE, f"{name}.png"))
    print(name, part.size)
