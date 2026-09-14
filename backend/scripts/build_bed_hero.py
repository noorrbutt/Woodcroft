"""Composite the bedroom hero where "Made to be kept" rises from behind the bed.

The effect is baked into the image (rather than layered in CSS) so the wordmark
stays pixel-aligned with the headboard at every screen size: the photo's wall is
cleaned of its two picture frames, the words are drawn on the wall, then the bed
is painted back over their lower half so they read as emerging from behind it.

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
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from app.core.config import settings
from app.services.media.pexels import api_key

_CTX = ssl.create_default_context()
_UA = "WoodcroftCatalog/1.0"
PHOTO_ID = 7546281  # frontal bed, tall tufted headboard, clean wall above
FONT = Path("app/services/media/fonts/Lora.ttf")
INK = (46, 33, 24)
# Picture frames + sconce to erase, as (x0, y0, x1, y1) fractions of the photo.
FRAMES = [(0.29, 0.185, 0.455, 0.405), (0.465, 0.20, 0.545, 0.365), (0.545, 0.185, 0.71, 0.405)]


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


def _clean_wall(im: Image.Image) -> Image.Image:
    """Erase the framed pictures by interpolating the clean wall above and below."""
    w, h = im.size
    arr = np.asarray(im).astype(np.float32).copy()
    for x0f, y0f, x1f, y1f in FRAMES:
        x0, y0, x1, y1 = int(x0f * w), int(y0f * h), int(x1f * w), int(y1f * h)
        strip = max(6, int(0.010 * h))
        top = arr[y0 - strip : y0, x0:x1].mean(axis=0)
        bot = arr[y1 : y1 + strip, x0:x1].mean(axis=0)
        t = np.linspace(0, 1, y1 - y0).reshape(-1, 1, 1)
        grad = top[None] * (1 - t) + bot[None] * t
        mw, mh = x1 - x0, y1 - y0
        m = Image.new("L", (mw, mh), 0)
        fe = int(min(mw, mh) * 0.08)
        ImageDraw.Draw(m).rectangle([fe, fe, mw - fe, mh - fe], fill=255)
        m = np.asarray(m.filter(ImageFilter.GaussianBlur(max(6, fe // 2)))).astype(np.float32) / 255
        arr[y0:y1, x0:x1] = arr[y0:y1, x0:x1] * (1 - m[..., None]) + grad * m[..., None]
    # Soften any residual edges across the pure-wall band.
    out = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))
    y0, y1 = int(0.14 * h), int(0.405 * h)
    band = np.asarray(out.crop((0, y0, w, y1)).filter(ImageFilter.GaussianBlur(10))).astype(np.float32)
    a2 = np.asarray(out).astype(np.float32)
    fade = int((y1 - y0) * 0.12)
    fy = np.ones((y1 - y0, 1, 1), np.float32)
    fy[:fade, 0, 0] = np.linspace(0, 1, fade)
    fy[-fade:, 0, 0] = np.linspace(1, 0, fade)
    a2[y0:y1] = a2[y0:y1] * (1 - fy) + band * fy
    return Image.fromarray(np.clip(a2, 0, 255).astype(np.uint8))


def _occlusion(size: tuple[int, int], cut: float) -> Image.Image:
    cw, ch = size
    cut_px, fe = int(cut * ch), int(0.015 * ch)
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
    src = _clean_wall(src)
    root = Path(settings.MEDIA_ROOT)
    W, H = src.size

    # Desktop 16:9, single line rising from behind the headboard.
    ch = int(W / (16 / 9))
    crop = src.crop((0, min(int(0.03 * H), H - ch), W, min(int(0.03 * H), H - ch) + ch))
    cw, chh = crop.size
    f = _font_for("Made to be kept", int(cw * 0.70))
    bb = f.getbbox("Made to be kept")
    cut = 0.475
    top = int((cut - 0.56 * ((bb[3] - bb[1]) / chh)) * chh) - bb[1]
    comp = crop.copy()
    _centre(ImageDraw.Draw(comp), "Made to be kept", f, cw // 2, top)
    comp.paste(crop, (0, 0), _occlusion(comp.size, cut))
    _save(comp, root / "hero" / "bed_hero", (800, 1600, 2400))
    print("desktop hero: ok")

    # Phone 9:16, two lines.
    mcw = int(H * 9 / 16)
    mc = src.crop(((W - mcw) // 2, 0, (W - mcw) // 2 + mcw, H))
    cw, chh = mc.size
    f = _font_for("be kept", int(cw * 0.80))
    bb = f.getbbox("be kept")
    lh = int((bb[3] - bb[1]) * 1.04)
    cut = 0.44
    l2 = int((cut - 0.5 * ((bb[3] - bb[1]) / chh)) * chh) - bb[1]
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
