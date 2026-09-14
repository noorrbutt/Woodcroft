"""Composite the bedroom hero: "Made to be kept" behind the bed, on the wall.

The effect is the MODUS / HORIZON layering — background wall, then the wordmark,
then the bed as a foreground cutout painted back on top so it overlaps the base
of the centre letters while the outer letters stay full on the wall. The bed is
"cut out" with a simple silhouette mask (headboard + frame + nightstands), which
is reliable for a straight-on, symmetrical bedroom.

Source is a committed asset (scripts/assets/bedroom_hero.jpg). Two crops are
written into the gitignored media dir: a 16:9 desktop cut (one line) and a 4:5
phone cut (two lines). This is the repeatable way to rebuild the hero.

    python -m scripts.build_bed_hero

Run from the backend/ directory.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from app.core.config import settings

SOURCE = Path("scripts/assets/bedroom_hero.jpg")
FONT = Path("app/services/media/fonts/Lora.ttf")
INK = (50, 37, 27)


def _upscale(im: Image.Image, target_w: int) -> Image.Image:
    return im.resize((target_w, round(target_w * im.height / im.width)), Image.LANCZOS)


def _bed_mask(cw: int, chh: int, rects: list[tuple[float, float, float, float]]) -> Image.Image:
    """Opaque over the bed silhouette (fraction rects), transparent over the wall."""
    m = Image.new("L", (cw, chh), 0)
    d = ImageDraw.Draw(m)
    for x0, y0, x1, y1 in rects:
        d.rounded_rectangle((x0 * cw, y0 * chh, x1 * cw, y1 * chh), radius=int(0.02 * cw), fill=255)
    return m.filter(ImageFilter.GaussianBlur(int(0.006 * cw)))


def _font_for(text: str, target_w: int) -> ImageFont.FreeTypeFont:
    base = ImageFont.truetype(str(FONT), 200)
    bb = base.getbbox(text)
    return ImageFont.truetype(str(FONT), int(200 * target_w / (bb[2] - bb[0])))


def _centre(draw: ImageDraw.ImageDraw, text: str, font, cx: int, baseline: int) -> None:
    bb = font.getbbox(text)
    draw.text((cx - (bb[2] - bb[0]) // 2 - bb[0], baseline - (bb[3] - bb[1]) - bb[1]),
              text, font=font, fill=INK)


def _save(img: Image.Image, base: Path, widths: tuple[int, ...]) -> None:
    base.parent.mkdir(parents=True, exist_ok=True)
    cw, ch = img.size
    for w in widths:
        img.resize((w, round(w * ch / cw)), Image.LANCZOS).save(
            f"{base}_{w}.webp", "WEBP", quality=88, method=4
        )


def main() -> int:
    if not SOURCE.exists() or not FONT.exists():
        print(f"Missing source ({SOURCE}) or font ({FONT}).")
        return 1
    root = Path(settings.MEDIA_ROOT)
    base = Image.open(SOURCE).convert("RGB")

    # Desktop 16:9, one line spanning the wall.
    src = _upscale(base, 1920)
    W, H = src.size
    ch = int(W / (16 / 9))
    top = int((H - ch) * 0.30)
    crop = src.crop((0, top, W, top + ch))
    cw, chh = crop.size
    mask = _bed_mask(cw, chh, [
        (0.27, 0.55, 0.73, 1.0),   # headboard
        (0.19, 0.68, 0.81, 1.0),   # bed frame
        (0.10, 0.66, 0.26, 1.0),   # left nightstand
        (0.74, 0.66, 0.90, 1.0),   # right nightstand
    ])
    comp = crop.copy()
    _centre(ImageDraw.Draw(comp), "Made to be kept", _font_for("Made to be kept", int(cw * 0.82)),
            cw // 2, int(0.635 * chh))
    comp.paste(crop, (0, 0), mask)
    _save(comp, root / "hero" / "bed_hero", (800, 1600, 2400))
    print("desktop hero: ok")

    # Phone 4:5, two lines.
    src = _upscale(base, 1400)
    W, H = src.size
    cw2 = int(H * 4 / 5)
    mc = src.crop(((W - cw2) // 2, 0, (W - cw2) // 2 + cw2, H))
    cw, chh = mc.size
    mask = _bed_mask(cw, chh, [(0.14, 0.55, 0.86, 1.0), (0.04, 0.68, 0.96, 1.0)])
    f = _font_for("be kept", int(cw * 0.80))
    lh = int((f.getbbox("be kept")[3] - f.getbbox("be kept")[1]) * 1.06)
    comp = mc.copy()
    d = ImageDraw.Draw(comp)
    b2 = int(0.62 * chh)
    _centre(d, "Made to", f, cw // 2, b2 - lh)
    _centre(d, "be kept", f, cw // 2, b2)
    comp.paste(mc, (0, 0), mask)
    _save(comp, root / "hero" / "bed_hero_m", (600, 900, 1200))
    print("phone hero: ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
