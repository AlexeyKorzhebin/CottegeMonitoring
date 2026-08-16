#!/usr/bin/env python3
"""Render cottage light on/off tiles as SVG + PNG (64/128/256)."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

OUT = Path(__file__).resolve().parent
ON_BG = (245, 196, 0, 255)  # #F5C400
ON_GLYPH = (28, 25, 23, 255)  # #1C1917
OFF_BG = (58, 58, 58, 255)  # #3A3A3A
OFF_GLYPH = (163, 163, 163, 255)  # #A3A3A3
CANVAS = (24, 27, 31, 255)  # #181B1F
RX = 14  # corner radius in 64px space

# Closed bulb body (collar included) in 64×64 tile space, 15% padding.
# Cubic segments: (start, c1, c2, end) — start of each is end of previous.
BODY_CUBICS = [
    ((24.0, 44.0), (15.0, 40.0), (12.0, 33.0), (12.0, 26.0)),
    ((12.0, 26.0), (12.0, 16.0), (20.5, 9.0), (32.0, 9.0)),
    ((32.0, 9.0), (43.5, 9.0), (52.0, 16.0), (52.0, 26.0)),
    ((52.0, 26.0), (52.0, 33.0), (49.0, 40.0), (40.0, 44.0)),
]
BODY_LINE_TO = [(40.0, 46.5), (24.0, 46.5)]
BASE = (25.5, 48.0, 38.5, 54.0)  # x0,y0,x1,y1


def bezier(p0, p1, p2, p3, n: int = 48) -> list[tuple[float, float]]:
    pts: list[tuple[float, float]] = []
    for i in range(n + 1):
        t = i / n
        u = 1.0 - t
        x = u**3 * p0[0] + 3 * u**2 * t * p1[0] + 3 * u * t**2 * p2[0] + t**3 * p3[0]
        y = u**3 * p0[1] + 3 * u**2 * t * p1[1] + 3 * u * t**2 * p2[1] + t**3 * p3[1]
        pts.append((x, y))
    return pts


def body_points() -> list[tuple[float, float]]:
    pts: list[tuple[float, float]] = []
    for i, seg in enumerate(BODY_CUBICS):
        curve = bezier(*seg)
        pts.extend(curve if i == 0 else curve[1:])
    pts.extend(BODY_LINE_TO)
    return pts


def scaled(pts: list[tuple[float, float]], scale: int) -> list[tuple[int, int]]:
    return [(round(x * scale), round(y * scale)) for x, y in pts]


def bulb_mask(px: int) -> Image.Image:
    scale = px / 64
    s = px
    mask = Image.new("L", (s, s), 0)
    d = ImageDraw.Draw(mask)
    d.polygon(scaled(body_points(), scale), fill=255)
    x0, y0, x1, y1 = (round(v * scale) for v in BASE)
    d.rounded_rectangle([x0, y0, x1, y1], radius=max(1, round(1.2 * scale)), fill=255)
    return mask


def tile(px: int, bg: tuple[int, int, int, int], glyph: tuple[int, int, int, int], filled: bool) -> Image.Image:
    scale = px / 64
    img = Image.new("RGBA", (px, px), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, px - 1, px - 1], radius=round(RX * scale), fill=bg)
    mask = bulb_mask(px)
    if filled:
        layer = Image.new("RGBA", (px, px), glyph)
        img.paste(layer, (0, 0), mask)
        return img
    stroke = max(3, round(2.4 * scale))
    k = stroke if stroke % 2 == 1 else stroke + 1
    eroded = mask.filter(ImageFilter.MinFilter(k))
    outline = ImageChops.subtract(mask, eroded)
    layer = Image.new("RGBA", (px, px), glyph)
    img.paste(layer, (0, 0), outline)
    return img


def svg_path() -> str:
    parts = [f"M {BODY_CUBICS[0][0][0]:.1f} {BODY_CUBICS[0][0][1]:.1f}"]
    for _start, c1, c2, end in BODY_CUBICS:
        parts.append(f"C {c1[0]:.1f} {c1[1]:.1f} {c2[0]:.1f} {c2[1]:.1f} {end[0]:.1f} {end[1]:.1f}")
    for x, y in BODY_LINE_TO:
        parts.append(f"L {x:.1f} {y:.1f}")
    parts.append("Z")
    x0, y0, x1, y1 = BASE
    rw, rh = x1 - x0, y1 - y0
    base = f'<rect x="{x0}" y="{y0}" width="{rw}" height="{rh}" rx="1.2"/>'
    return " ".join(parts), base


def write_svg(path: Path, *, on: bool) -> None:
    d, base = svg_path()
    bg = "#F5C400" if on else "#3A3A3A"
    if on:
        glyph = f'<path fill="#1C1917" d="{d}"/>\n  {base.replace("/>", " fill=\"#1C1917\"/>")}'
    else:
        glyph = (
            f'<g fill="none" stroke="#A3A3A3" stroke-width="2.4" '
            f'stroke-linejoin="round" stroke-linecap="round">\n'
            f'    <path d="{d}"/>\n'
            f"    {base}\n"
            f"  </g>"
        )
    path.write_text(
        f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" width="64" height="64">
  <rect width="64" height="64" rx="14" fill="{bg}"/>
  {glyph}
</svg>
''',
        encoding="utf-8",
    )


def pair_preview() -> Image.Image:
    tile_px = 256
    gap = 48
    pad = 64
    label_h = 56
    w = pad * 2 + tile_px * 2 + gap
    h = pad * 2 + tile_px + label_h
    img = Image.new("RGBA", (w, h), CANVAS)
    on = tile(tile_px, ON_BG, ON_GLYPH, True)
    off = tile(tile_px, OFF_BG, OFF_GLYPH, False)
    img.paste(on, (pad, pad), on)
    img.paste(off, (pad + tile_px + gap, pad), off)
    d = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 28)
    except OSError:
        font = ImageFont.load_default()
    y = pad + tile_px + 16
    for text, x0 in (("ON", pad), ("OFF", pad + tile_px + gap)):
        bbox = d.textbbox((0, 0), text, font=font)
        tw = bbox[2] - bbox[0]
        d.text((x0 + (tile_px - tw) / 2, y), text, fill=(180, 180, 180, 255), font=font)
    return img


def main() -> None:
    write_svg(OUT / "light-on.svg", on=True)
    write_svg(OUT / "light-off.svg", on=False)
    for px in (64, 128, 256):
        tile(px, ON_BG, ON_GLYPH, True).save(OUT / f"light-on-{px}.png", "PNG")
        tile(px, OFF_BG, OFF_GLYPH, False).save(OUT / f"light-off-{px}.png", "PNG")
    pair_preview().save(OUT / "lights-pair-preview.png", "PNG")
    print(f"wrote icons in {OUT}")


if __name__ == "__main__":
    main()
