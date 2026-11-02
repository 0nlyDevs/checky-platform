"""Halftone the landing's case-file pieces (apps/web/public/site/dossier).

Each Wikimedia Commons photograph (see apps/web/public/site/credits.json) is printed as a 45-degree dot
screen in the case file's ink on manila; share-alike sources keep their licence on the result.

    uv run --project apps/api --with pillow python -I scripts/site_pictures.py <originals dir>

with, in <originals dir>: analakely.jpg, panorama.jpg, rova-night.jpg, anosy.jpg (the files named in credits.json).
"""

import math
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageOps

OUT = Path(__file__).resolve().parents[1] / "apps/web/public/site/dossier"
INK, MANILA = (20, 18, 16), (220, 201, 163)  # --site-ink, --site-manila


def halftone(src: Path, out: Path, w: int = 900, h: int = 600, cell: int = 7) -> None:
    im = ImageOps.autocontrast(ImageOps.fit(Image.open(src).convert("L"), (w, h)), cutoff=2)
    s, c = 2, cell * 2
    rot = im.resize((w * s, h * s)).rotate(45, expand=True, fillcolor=255)
    dots = Image.new("L", rot.size, 255)
    draw, px = ImageDraw.Draw(dots), rot.load()
    for y in range(0, rot.size[1], c):
        for x in range(0, rot.size[0], c):
            cx, cy = min(x + c // 2, rot.size[0] - 1), min(y + c // 2, rot.size[1] - 1)
            dark = (1 - px[cx, cy] / 255) ** 1.3
            if dark > 0.04:
                r = c * 0.5 * math.sqrt(dark) * 1.05
                draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=0)
    dots = dots.rotate(-45)
    x0, y0 = (dots.size[0] - w * s) // 2, (dots.size[1] - h * s) // 2
    dots = dots.crop((x0, y0, x0 + w * s, y0 + h * s)).resize((w, h))
    Image.merge("RGB", [dots.point(lambda v, a=a, b=b: int(b + (a - b) * v / 255)) for a, b in zip(MANILA, INK)]).save(out, quality=88)


if __name__ == "__main__":
    src = Path(sys.argv[1])
    OUT.mkdir(parents=True, exist_ok=True)
    for i, name in enumerate(["analakely.jpg", "panorama.jpg", "rova-night.jpg", "anosy.jpg"], 1):
        halftone(src / name, OUT / f"piece-{i}.jpg")
