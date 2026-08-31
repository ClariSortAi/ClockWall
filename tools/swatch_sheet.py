"""Tiles captures/swatch/*.png onto one sheet, on a mid grey, for looking at.

    python tools/swatch_sheet.py

Mid grey rather than black: half these crops are polished metal on alpha, and
judging metal against black makes everything look brighter and more contrasty
than it is - which is exactly the mistake that let a too-dark bezel through.
"""
import os
from PIL import Image, ImageDraw

SRC = "captures/swatch"
ORDER = ["index", "bezel", "escapement", "balance", "hour", "second"]
CELL, PAD = 300, 10


def main():
    tiles = [(n, Image.open(os.path.join(SRC, n + ".png")).convert("RGBA"))
             for n in ORDER if os.path.exists(os.path.join(SRC, n + ".png"))]
    cols = len(tiles)
    sheet = Image.new("RGB", (cols * (CELL + PAD) + PAD, CELL + PAD * 2 + 18), (104, 104, 110))
    d = ImageDraw.Draw(sheet)
    for i, (name, im) in enumerate(tiles):
        im.thumbnail((CELL, CELL), Image.LANCZOS)
        cell = Image.new("RGBA", (CELL, CELL), (104, 104, 110, 255))
        cell.alpha_composite(im, ((CELL - im.width) // 2, (CELL - im.height) // 2))
        x = PAD + i * (CELL + PAD)
        sheet.paste(cell.convert("RGB"), (x, PAD))
        d.text((x + 4, CELL + PAD + 3), name, fill=(20, 20, 24))
    sheet.save("captures/swatch-sheet.png")
    print("wrote captures/swatch-sheet.png", sheet.size)


if __name__ == "__main__":
    main()
