"""Génère assets/icon.png, icon.ico et icon.icns (icône originale : carré arrondi dégradé + flèches)."""
from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw

ASSETS = Path(__file__).resolve().parents[1] / "assets"
S = 1024


def gradient(size: int) -> Image.Image:
    a, b = (79, 70, 229), (14, 165, 233)  # indigo → bleu ciel
    img = Image.new("RGB", (size, size))
    px = img.load()
    for y in range(size):
        for x in range(size):
            t = (x + y) / (2 * size)
            px[x, y] = tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))
    return img


def arrow_arc(d: ImageDraw.ImageDraw, cx, cy, r, start, end, width, color):
    """Arc parcouru dans le sens horaire (repère écran) terminé par une pointe de flèche."""
    d.arc((cx - r, cy - r, cx + r, cy + r), start, end, fill=color, width=width)
    a = math.radians(end)
    rm = r - width / 2  # milieu du trait
    px, py = cx + rm * math.cos(a), cy + rm * math.sin(a)
    rad = (math.cos(a), math.sin(a))
    tan = (-math.sin(a), math.cos(a))
    hw, L = width * 1.1, width * 1.3
    d.polygon([(px + rad[0] * hw, py + rad[1] * hw), (px - rad[0] * hw, py - rad[1] * hw),
               (px + tan[0] * L, py + tan[1] * L)], fill=color)


def make() -> None:
    ASSETS.mkdir(exist_ok=True)
    big = S * 2
    mask = Image.new("L", (big, big), 0)
    ImageDraw.Draw(mask).rounded_rectangle((60, 60, big - 60, big - 60), radius=440, fill=255)
    base = gradient(big // 8).resize((big, big), Image.BICUBIC).convert("RGBA")
    base.putalpha(mask)
    d = ImageDraw.Draw(base)
    c = big // 2
    arrow_arc(d, c, c, 600, 195, 320, 130, (255, 255, 255, 255))
    arrow_arc(d, c, c, 600, 15, 140, 130, (255, 255, 255, 255))
    # petit document au centre
    w, h = 400, 510
    d.rounded_rectangle((c - w // 2, c - h // 2, c + w // 2, c + h // 2), radius=40, fill=(255, 255, 255, 255))
    for i in range(3):
        y = c - 120 + i * 105
        d.rounded_rectangle((c - 125, y, c + 125 - (i == 2) * 80, y + 36), radius=18, fill=(79, 70, 229, 255))
    icon = base.resize((S, S), Image.LANCZOS)
    icon.save(ASSETS / "icon.png")
    icon.save(ASSETS / "icon.ico", sizes=[(s, s) for s in (16, 20, 24, 32, 40, 48, 64, 128, 256)])
    try:
        icon.save(ASSETS / "icon.icns")
    except Exception as e:  # pragma: no cover
        print("ICNS non généré :", e)
    print("Icônes générées dans", ASSETS)


if __name__ == "__main__":
    make()
