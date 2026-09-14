"""Composite the bedroom hero where "Made to be kept" rises from behind the bed.

A spacious room shot from afar (bed set back, nightstands beside it) is warmed
slightly, then the words are drawn on the back wall and the bed is painted back
over their lower edge so the wordmark reads as emerging from behind it, staying
pixel-aligned with the bed at every screen size.

Two crops are written: a 16:9 desktop cut (one line) and a 9:16 phone cut (two
lines). Media lives outside git, so this is the repeatable way to rebuild the
hero after a fresh checkout.

    PEXELS_API_KEY=... python -m scripts.build_bed_hero

Run from the backend/ directory. Needs numpy (see requirements-dev.txt).
"""

from __future__ import annotations

import io
import json
import ssl
import sys
import urllib.request
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFont

from app.core.config import settings
from app.services.media.pexels import api_key

_CTX = ssl.create_default_context()
_UA = "WoodcroftCatalog/1.0"
PHOTO_ID = 7045862  # spacious room, foot-first, big clean wall above the bed
FONT = Path("app/services/media/fonts/Lora.ttf")
INK = (52, 38, 28)


def _fetch() -> Image.Image | None:
    key = api_key()
    if not key:
        return None
    try:
        meta = json.loads(_req(f"https://api.pexels.com/v1/photos/{PHOTO_ID}", key))
        return Image.open(io.BytesIO(_req(meta["src"]["original"]))).convert("RGB")
    except Exception:
        return None


def _req(url: str, key: str | None = None) -> bytes:
    headers = {"User-Agent": _UA}
    if key:
        headers["Authorization"] = key
    return urllib.request.urlopen(
        urllib.request.Request(url, headers=headers), timeout=40, context=_CTX
    ).read()


def _warm(im: Image.Image) -> Image.Image:
    arr = np.asarray(im).astype(np.float32)
    arr[..., 0] *= 1.03
    arr[..., 2] *= 0.945
    out = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))
    return ImageEnhance.Contrast(out).enhance(1.03)


def _occlusion(size: tuple[int, int], cut: float) -> Image.Image:
    cw, ch = size
    cut_px, fe = int(cut * ch), int(0.013 * ch)
    m = np.zeros((ch, cw), np.float32)
    m[cut_px:] = 1.0
    m[cut_px - fe : cut_px + fe] = np.linspace(0, 1, 2 * fe)[:, None]
    return Image.fromarray((m * 255).astype(np.uint8), "L")


def _font_for(text: str, target_w: int) -> ImageFont.FreeTypeFont:
    base = ImageFont.truetype(str(FONT), 200)
    bb = base.getbbox(text)
    return ImageFont.truetype(str(FONT), int(200 * target_w / (bb[2] - bb[0])))


def _centre(draw: ImageDraw.ImageDraw, text: str, font, cx: int, top: int) -> None:
    bb = font.getbbox(text)
    draw.text((cx - (bb[2] - bb[0]) // 2 - bb[0], top - bb[1]), text, font=font, fill=INK)


def _save(img: Image.Image, base: Path, widths: tuple[int, ...]) -> None:
    base.parent.mkdir(parents=True, exist_ok=True)
    cw, ch = img.size
    for wpx in widths:
        img.resize((wpx, round(wpx * ch / cw)), Image.LANCZOS).save(
            f"{base}_{wpx}.webp", "WEBP", quality=86, method=4
        )


def main() -> int:
    if not FONT.exists():
        print(f"Font missing: {FONT}")
        return 1
    src = _fetch()
    if src is None:
        print("Could not fetch the hero photo (PEXELS_API_KEY set?).")
        return 1
    src = _warm(src)
    root = Path(settings.MEDIA_ROOT)
    W, H = src.size

    # Desktop 16:9, single line rising from behind the bed.
    ch = int(W / (16 / 9))
    top = int(0.135 * H)
    crop = src.crop((0, top, W, top + ch))
    cw, chh = crop.size
    cut = (0.545 * H - top) / chh
    f = _font_for("Made to be kept", int(cw * 0.62))
    bb = f.getbbox("Made to be kept")
    tp = int((cut - 0.66 * ((bb[3] - bb[1]) / chh)) * chh) - bb[1]
    comp = crop.copy()
    _centre(ImageDraw.Draw(comp), "Made to be kept", f, cw // 2, tp)
    comp.paste(crop, (0, 0), _occlusion(comp.size, cut))
    _save(comp, root / "hero" / "bed_hero", (800, 1600, 2400))
    print("desktop hero: ok")

    # Phone 9:16, two lines.
    mcw = int(H * 9 / 16)
    mc = src.crop(((W - mcw) // 2, 0, (W - mcw) // 2 + mcw, H))
    cw, chh = mc.size
    cut = 0.545
    f = _font_for("be kept", int(cw * 0.82))
    bb = f.getbbox("be kept")
    lh = int((bb[3] - bb[1]) * 1.04)
    l2 = int((cut - 0.62 * ((bb[3] - bb[1]) / chh)) * chh) - bb[1]
    comp = mc.copy()
    d = ImageDraw.Draw(comp)
    _centre(d, "Made to", f, cw // 2, l2 - lh)
    _centre(d, "be kept", f, cw // 2, l2)
    comp.paste(mc, (0, 0), _occlusion(comp.size, cut))
    _save(comp, root / "hero" / "bed_hero_m", (600, 900, 1200))
    print("phone hero: ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
