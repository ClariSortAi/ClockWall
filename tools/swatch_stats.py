"""Reports tone statistics per swatch, so 'too bright' is a number.

    python tools/swatch_stats.py

Eyeballing a metal render on a screen is unreliable in exactly the direction
that matters here: a clipped highlight and a merely bright one look identical,
and a part that is 40% pure white has lost all its surface detail whatever it
looks like at a glance. Clip percentage is the one number that catches it.
"""
import os
from PIL import Image
import numpy as np

SRC = "captures/swatch"
for name in sorted(os.listdir(SRC)):
    if not name.endswith(".png"):
        continue
    im = np.array(Image.open(os.path.join(SRC, name)).convert("RGBA")).astype(np.float32)
    a = im[..., 3] > 8
    if not a.any():
        print("%-12s EMPTY" % name[:-4]); continue
    lum = (0.2126 * im[..., 0] + 0.7152 * im[..., 1] + 0.0722 * im[..., 2])[a]
    print("%-12s median %5.1f  p95 %5.1f  clipped>250 %5.1f%%  black<8 %5.1f%%"
          % (name[:-4], np.median(lum), np.percentile(lum, 95),
             100.0 * (lum > 250).mean(), 100.0 * (lum < 8).mean()))
