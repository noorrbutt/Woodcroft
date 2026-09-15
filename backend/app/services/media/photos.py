"""Product imagery: honest placeholders and admin uploads.

Real product photography is uploaded by an admin through the image manager. Until
a piece has its own photo, the seed generates an on-brand placeholder card
(write_placeholder) labelled with the product name and wood, rather than a stock
room scene that would misrepresent the item. write_upload processes an admin's
real photo into the same webp size family with a blur-up placeholder.

Curated photography is a separate path: `media/pexels.py` searches for a photo
matching the product type and downloads it. A room-level stock scene keyed on
category is deliberately not offered - it cannot be guaranteed to show the piece
a customer is looking at.
"""

from __future__ import annotations

import hashlib
import io
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from app.models.enums import WoodSpecies
from app.services.media.colour import hex_to_rgb, mix
from app.services.media.plates import SIZES, blur_data_url

_FONT_PATH = Path(__file__).parent / "fonts" / "Lora.ttf"


def _font(size: int, weight: int = 500) -> ImageFont.FreeTypeFont:
    font = ImageFont.truetype(str(_FONT_PATH), size)
    try:
        font.set_variation_by_axes([weight])
    except Exception:
        pass
    return font


def _wrap(draw, text: str, font, max_width: int) -> list[str]:
    words, lines, line = text.split(), [], ""
    for word in words:
        trial = f"{line} {word}".strip()
        if draw.textlength(trial, font=font) <= max_width:
            line = trial
        else:
            if line:
                lines.append(line)
            line = word
    if line:
        lines.append(line)
    return lines[:4]


def render_placeholder(species: WoodSpecies, product_name: str) -> Image.Image:
    """An honest, on-brand placeholder card labelled with the product.

    Real product photography is uploaded by an admin. Until then, showing a
    stock room scene that does not match the piece (a sofa on a wardrobe) is
    worse than showing nothing, so this renders a tasteful editorial card: a
    warm ground tinted by the wood, the product name in a serif, the wood named
    beneath. It never pretends to be a photo of the item.
    """
    W, H = 1000, 1250
    bone = (244, 239, 231)
    tone = hex_to_rgb(species.grain_palette[0])
    ink = (42, 29, 18)
    muted = mix(ink, bone, 0.45)
    brass = (176, 141, 87)

    # Vertical gradient from bone to a soft wash of the wood tone.
    base = Image.new("RGB", (W, H), bone)
    px = base.load()
    for y in range(H):
        t = (y / H) * 0.22
        row = mix(bone, tone, t)
        for x in range(W):
            px[x, y] = row
    draw = ImageDraw.Draw(base)

    # Eyebrow, letter-spaced.
    eyebrow = " ".join("WOODCROFT")
    ef = _font(22, 500)
    ew = draw.textlength(eyebrow, font=ef)
    draw.text(((W - ew) / 2, 250), eyebrow, font=ef, fill=brass)

    # Product name, wrapped and centred.
    title_font = _font(58, 600)
    lines = _wrap(draw, product_name, title_font, W - 200)
    line_h = 74
    total_h = line_h * len(lines)
    y = (H - total_h) / 2 - 10
    for ln in lines:
        w = draw.textlength(ln, font=title_font)
        draw.text(((W - w) / 2, y), ln, font=title_font, fill=ink)
        y += line_h

    # Brass rule.
    draw.line([(W / 2 - 40, y + 24), (W / 2 + 40, y + 24)], fill=brass, width=2)

    # Wood species beneath.
    sf = _font(24, 500)
    label = species.label.upper()
    sw = draw.textlength(label, font=sf)
    draw.text(((W - sw) / 2, y + 48), label, font=sf, fill=muted)

    return base


def placeholder_meta(rel_path: str, base: Image.Image) -> dict:
    """The ProductImage metadata for a rendered placeholder (no file I/O)."""
    return {
        "base_path": rel_path,
        "sizes": list(SIZES),
        "width": base.width,
        "height": base.height,
        "aspect": round(base.width / base.height, 4),
        "blur_data_url": blur_data_url(base),
        "source": "generated",
        "checksum": hashlib.sha256(f"placeholder:{rel_path}".encode()).hexdigest(),
    }


def write_placeholder(
    root: Path, rel_path: str, species: WoodSpecies, product_name: str
) -> dict:
    """Render an on-brand placeholder card and save the webp size family to disk."""
    base = render_placeholder(species, product_name)
    target = root / rel_path
    target.parent.mkdir(parents=True, exist_ok=True)
    for size in SIZES:
        scaled = base.copy()
        scaled.thumbnail((size, size * 2), Image.LANCZOS)
        scaled.save(f"{target}_{size}.webp", "WEBP", quality=84, method=2)
    return placeholder_meta(rel_path, base)


def write_upload(root: Path, rel_path: str, data: bytes) -> dict:
    """Process an admin-uploaded image into the same webp size family.

    Raises ValueError if the bytes are not a decodable image. The result matches
    the ProductImage metadata shape, with source 'uploaded'.
    """
    try:
        master = Image.open(io.BytesIO(data)).convert("RGB")
        master.load()
    except Exception as exc:  # noqa: BLE001 - turned into a clean 4xx by caller
        raise ValueError("That file is not a readable image.") from exc

    target = root / rel_path
    target.parent.mkdir(parents=True, exist_ok=True)
    for size in SIZES:
        scaled = master.copy()
        scaled.thumbnail((size, size * 2), Image.LANCZOS)
        scaled.save(f"{target}_{size}.webp", "WEBP", quality=82, method=2)

    return {
        "base_path": rel_path,
        "sizes": list(SIZES),
        "width": master.width,
        "height": master.height,
        "aspect": round(master.width / master.height, 4),
        "blur_data_url": blur_data_url(master),
        "source": "uploaded",
        "checksum": hashlib.sha256(data).hexdigest(),
    }
