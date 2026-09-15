"""Procedural product imagery.

There are no photographs of this furniture, and there never will be for a demo
catalogue. The options were a grey placeholder box, a remote stock photo that
needs an API key and an internet connection, or generating something ourselves.

We generate. Each plate is a staged studio composition: a warm paper ground, a
soft contact shadow, and a panel filled with wood grain tinted to the actual
species. It reads as a deliberate material study rather than a missing image.

Getting the grain right
-----------------------
Real flat-sawn timber is not concentric rings. The pith sits far off the edge of
the board, so what you see is a set of nearly parallel bands running along the
length, wandering slowly, occasionally opening into the arched "cathedral"
figure where the cut passes near a growth boundary. Modelling it as rings around
a nearby centre produces a topographic-map look that reads as marble or an oil
slick, never as wood. So the field here is built along one dominant axis with
slow lateral drift, and the arches come from letting ring spacing compress
rather than from curving the rings themselves.

Performance
-----------
Per-pixel Python on a 2000x2500 plate would take minutes, and there are
hundreds. The grain is computed small, where the maths is cheap, then
LANCZOS-upscaled; grain is low frequency, so nothing is lost. Textures are
cached at a fixed size per (species, variation) and resized at composition
time, which keeps the cache actually hitting.
"""

from __future__ import annotations

import hashlib
import math
import random
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter

from app.models.enums import WoodSpecies
from app.services.media.colour import hex_to_rgb, mix

#: Grain is generated at this size, then scaled to whatever the panel needs.
#: Fixed so the lru_cache below actually hits.
GRAIN_W, GRAIN_H = 210, 270

#: Cached texture size. Large enough to downscale to any panel cleanly.
TEXTURE_W, TEXTURE_H = 900, 1150

SIZES = (400, 800, 1600)

#: Warm paper grounds, alternated so a grid of plates is not uniform.
GROUNDS = ("#F2ECE1", "#EFE8DB", "#F5F0E7", "#ECE4D6")


@dataclass(frozen=True)
class Grain:
    """How a species reads: band spacing, wander, and figure strength."""

    frequency: float   # bands across the board
    wander: float      # how much they drift sideways
    contrast: float    # latewood darkness
    figure: float      # cathedral arch strength


GRAIN_BY_SPECIES: dict[WoodSpecies, Grain] = {
    # Dense tropical hardwoods: many tight lines, busy figure.
    WoodSpecies.SHEESHAM: Grain(26.0, 0.055, 0.34, 0.30),
    WoodSpecies.WALNUT: Grain(21.0, 0.065, 0.30, 0.34),
    WoodSpecies.ACACIA: Grain(23.0, 0.060, 0.32, 0.28),
    # Calmer, straighter grain.
    WoodSpecies.TEAK: Grain(17.0, 0.040, 0.22, 0.20),
    WoodSpecies.MANGO: Grain(15.0, 0.050, 0.24, 0.26),
    WoodSpecies.OAK: Grain(19.0, 0.045, 0.28, 0.38),
    # Softwoods: fewer, wider bands but a hard early/latewood step.
    WoodSpecies.DEODAR: Grain(13.0, 0.035, 0.30, 0.22),
    WoodSpecies.PINE: Grain(11.0, 0.030, 0.34, 0.20),
}


def _seed_for(key: str) -> int:
    return int(hashlib.sha256(key.encode()).hexdigest()[:8], 16)


# ── Noise ────────────────────────────────────────────────────────────────────
def _smooth(t: float) -> float:
    return t * t * (3 - 2 * t)


def _noise_1d(n: int, rng: random.Random, cells: int) -> list[float]:
    """Smooth 1-D noise, used for lateral drift along the board."""
    lattice = [rng.random() for _ in range(cells + 2)]
    out = []
    for i in range(n):
        g = i / n * cells
        i0 = int(g)
        f = _smooth(g - i0)
        out.append(lattice[i0] * (1 - f) + lattice[i0 + 1] * f)
    return out


def _noise_2d(w: int, h: int, rng: random.Random, cx: int, cy: int) -> list[list[float]]:
    lattice = [[rng.random() for _ in range(cx + 2)] for _ in range(cy + 2)]
    out = []
    for y in range(h):
        gy = y / h * cy
        y0 = int(gy)
        fy = _smooth(gy - y0)
        row = []
        for x in range(w):
            gx = x / w * cx
            x0 = int(gx)
            fx = _smooth(gx - x0)
            top = lattice[y0][x0] * (1 - fx) + lattice[y0][x0 + 1] * fx
            bot = lattice[y0 + 1][x0] * (1 - fx) + lattice[y0 + 1][x0 + 1] * fx
            row.append(top * (1 - fy) + bot * fy)
        out.append(row)
    return out


def _grain_field(species: WoodSpecies, seed: int) -> Image.Image:
    """Greyscale grain: near-parallel bands along the board, slowly wandering."""
    rng = random.Random(seed)
    cfg = GRAIN_BY_SPECIES[species]

    # Lateral drift: one value per row, so bands stay coherent down the board
    # instead of dissolving into noise.
    drift = _noise_1d(GRAIN_H, rng, cells=5)
    # Slow spacing variation produces the cathedral arches.
    spacing = _noise_1d(GRAIN_H, rng, cells=3)
    # Fine mottling, well below band scale.
    mottle = _noise_2d(GRAIN_W, GRAIN_H, rng, cx=10, cy=22)
    # A slow lateral warp. Without it every line sits at a perfectly even
    # interval and the panel reads as machined reeding rather than timber.
    warp = _noise_2d(GRAIN_W, GRAIN_H, rng, cx=3, cy=4)

    frequency = cfg.frequency * rng.uniform(0.9, 1.1)
    phase = rng.uniform(0, math.pi * 2)

    pixels = bytearray(GRAIN_W * GRAIN_H)
    i = 0
    for y in range(GRAIN_H):
        # Bands shift sideways as we travel down the board.
        offset = (drift[y] - 0.5) * cfg.wander
        # And open out or compress, which is what makes an arch.
        local_freq = frequency * (1 + (spacing[y] - 0.5) * cfg.figure)

        # Latewood lines are not all equally dark; letting the strength vary
        # per row is most of what stops the result looking like a print.
        row_strength = 0.75 + drift[y] * 0.5

        for x in range(GRAIN_W):
            nx = x / GRAIN_W + offset + (warp[y][x] - 0.5) * 0.10

            # 0..1 wave, peaking where a growth boundary falls.
            wave = (math.sin((nx * local_freq + phase) * math.pi * 2) + 1) * 0.5
            # Raising it to a high power collapses the peak into a thin line,
            # leaving a wide pale earlywood field between. This ratio, not the
            # band spacing, is what actually makes it read as timber.
            line = wave ** 7

            value = 0.80 - line * cfg.contrast * row_strength
            value += (mottle[y][x] - 0.5) * 0.085
            value += (warp[y][x] - 0.5) * 0.11
            pixels[i] = max(0, min(255, int(value * 255)))
            i += 1

    field = Image.frombytes("L", (GRAIN_W, GRAIN_H), bytes(pixels))
    # Just enough to take the stair-stepping off, not enough to soften lines.
    return field.filter(ImageFilter.GaussianBlur(0.25))


@lru_cache(maxsize=64)
def wood_texture(species: WoodSpecies, variation: int) -> Image.Image:
    """A tinted wood texture at a fixed size, cached per species + variation."""
    palette = species.grain_palette
    base, grain, highlight = hex_to_rgb(palette[0]), hex_to_rgb(palette[1]), hex_to_rgb(palette[2])

    field = _grain_field(species, _seed_for(f"{species.value}:{variation}"))
    field = field.resize((TEXTURE_W, TEXTURE_H), Image.LANCZOS)

    # Fine fibre, stretched along the grain so it reads as pore structure
    # rather than as photographic noise. Generated in C.
    fibre = Image.effect_noise((TEXTURE_W, TEXTURE_H), 9)
    fibre = fibre.resize((TEXTURE_W, max(1, TEXTURE_H // 6)), Image.BILINEAR)
    fibre = fibre.resize((TEXTURE_W, TEXTURE_H), Image.BILINEAR)
    field = ImageChops.overlay(field, fibre.point(lambda v: 128 + (v - 128) // 3))

    # Map greyscale through the species ramp with a LUT, so colouring is in C.
    channels = []
    for index in range(3):
        lut = []
        for v in range(256):
            t = v / 255
            colour = mix(grain, base, t * 1.9) if t < 0.52 else mix(base, highlight, (t - 0.52) * 2.1)
            lut.append(colour[index])
        channels.append(field.point(lut))

    return Image.merge("RGB", tuple(channels))


# ── Composition ──────────────────────────────────────────────────────────────
def _rounded_mask(size: tuple[int, int], radius: int) -> Image.Image:
    mask = Image.new("L", size, 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        (0, 0, size[0] - 1, size[1] - 1), radius=radius, fill=255
    )
    return mask


def _soft_light(size: tuple[int, int], rng: random.Random) -> Image.Image:
    """A gentle directional wash, brighter towards one upper corner.

    Built by scaling a tiny gradient, so there is no rotation and therefore no
    hard seam where rotated corners would otherwise land.
    """
    w, h = size
    small = Image.new("L", (8, 10))
    draw = ImageDraw.Draw(small)
    from_left = rng.random() < 0.5
    for y in range(10):
        for x in range(8):
            fx = (x / 7) if from_left else (1 - x / 7)
            fy = 1 - y / 9
            # Centre on mid-grey so overlay neither lifts nor crushes overall.
            draw.point((x, y), fill=int(112 + 44 * (fx * 0.45 + fy * 0.55)))
    return small.resize((w, h), Image.BICUBIC)


def _vignette(size: tuple[int, int], strength: float) -> Image.Image:
    w, h = size
    small = Image.new("L", (48, 60), 255)
    draw = ImageDraw.Draw(small)
    steps = 18
    for i in range(steps):
        t = i / steps
        inset = t * 10
        draw.rectangle(
            (inset, inset * 1.25, 47 - inset, 59 - inset * 1.25),
            outline=int(255 - 255 * strength * (1 - t)),
        )
    return small.resize((w, h), Image.BICUBIC).filter(
        ImageFilter.GaussianBlur(w / 28)
    )


def make_plate(
    species: WoodSpecies,
    *,
    key: str,
    angle: int = 0,
    width: int = 1000,
    height: int = 1250,
) -> Image.Image:
    """One staged product plate."""
    rng = random.Random(_seed_for(f"{key}:{angle}"))
    ground = hex_to_rgb(GROUNDS[rng.randrange(len(GROUNDS))])
    canvas = Image.new("RGB", (width, height), ground)

    # Panel geometry varies by angle so a product's images differ from each
    # other without needing different grain.
    insets = [
        (0.13, 0.15, 0.87, 0.85),
        (0.20, 0.11, 0.80, 0.75),
        (0.09, 0.20, 0.91, 0.81),
        (0.22, 0.22, 0.78, 0.70),
    ][angle % 4]
    x0, y0 = int(insets[0] * width), int(insets[1] * height)
    x1, y1 = int(insets[2] * width), int(insets[3] * height)
    pw, ph = x1 - x0, y1 - y0
    radius = max(4, int(min(pw, ph) * (0.02 if angle % 2 == 0 else 0.09)))

    texture = wood_texture(species, rng.randrange(4)).resize((pw, ph), Image.LANCZOS)
    light = _soft_light((pw, ph), rng)
    texture = ImageChops.overlay(texture, Image.merge("RGB", (light, light, light)))
    texture = ImageEnhance.Contrast(texture).enhance(1.04)

    mask = _rounded_mask((pw, ph), radius)

    # Warm contact shadow. Never pure black: black on a cream ground reads
    # cheap, and the whole palette is warm.
    shadow_mask = Image.new("L", (width, height), 0)
    shadow_mask.paste(mask, (x0 + int(pw * 0.015), y0 + int(ph * 0.03)))
    shadow_mask = shadow_mask.filter(
        ImageFilter.GaussianBlur(radius=max(10, pw // 26))
    ).point(lambda v: int(v * 0.30))
    canvas.paste(Image.new("RGB", (width, height), (72, 54, 38)), (0, 0), shadow_mask)

    canvas.paste(texture, (x0, y0), mask)

    # Hairline highlight along the top edge lifts the panel off the ground.
    ImageDraw.Draw(canvas, "RGBA").rounded_rectangle(
        (x0, y0, x1 - 1, y1 - 1), radius=radius, outline=(255, 246, 232, 48), width=1
    )

    canvas = Image.composite(
        canvas,
        ImageEnhance.Brightness(canvas).enhance(0.93),
        _vignette((width, height), 0.30),
    )
    return canvas


def blur_data_url(image: Image.Image) -> str:
    """A tiny base64 JPEG for the low quality image placeholder."""
    import base64
    import io

    thumb = image.copy()
    thumb.thumbnail((20, 25), Image.LANCZOS)
    buffer = io.BytesIO()
    thumb.save(buffer, format="JPEG", quality=40)
    return f"data:image/jpeg;base64,{base64.b64encode(buffer.getvalue()).decode()}"


def write_plate(
    root: Path, rel_path: str, species: WoodSpecies, *, key: str, angle: int = 0
) -> dict:
    """Render one plate at every size. Returns metadata for product_image."""
    master = make_plate(species, key=key, angle=angle)
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
        "source": "generated",
        "checksum": hashlib.sha256(f"{key}:{angle}:v2".encode()).hexdigest(),
    }


def write_swatch(root: Path, species: WoodSpecies, size: int = 320) -> str:
    """A tile of pure grain for the PDP species selector."""
    texture = wood_texture(species, 0).resize((size, size), Image.LANCZOS)
    rel = f"swatches/{species.value}"
    target = root / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    texture.save(f"{target}.webp", "WEBP", quality=88)
    return rel
