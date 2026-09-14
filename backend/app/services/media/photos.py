"""Curated product photography.

The procedural wood plates read as flat swatches, not as furniture anyone wants
to buy. This module pulls real, styled furniture and interior photographs from
the Unsplash CDN (free under the Unsplash License), crops them to the catalogue's
4:5 aspect, and runs them through the same resize -> webp -> blur pipeline the
plates use, so they are served locally and load instantly with a blur-up
placeholder. Each unique photo is downloaded once and cached for the run.

If a download fails (offline, or a since-removed photo) the caller falls back to
a generated plate for that image, so a seed never breaks for want of a network.
"""

from __future__ import annotations

import hashlib
import io
import ssl
import urllib.request
from pathlib import Path

from PIL import Image

from app.services.media.plates import SIZES, blur_data_url

# Photo delivered pre-cropped to 4:5 by the Unsplash CDN, then optimised locally.
_CDN = "https://images.unsplash.com/photo-{pid}?w=1200&h=1500&fit=crop&crop=edges&q=80"
_UA = {"User-Agent": "Mozilla/5.0 (Woodcroft seeder)"}
_ctx = ssl.create_default_context()

#: Broad room categories, each a pool of verified furniture/interior photos.
CATEGORY_PHOTOS: dict[str, list[str]] = {
    "living": [
        "1555041469-a586c61ea9bc",
        "1567016432779-094069958ea5",
        "1550226891-ef816aed4a98",
        "1540574163026-643ea20ade25",
        "1524758631624-e2822e304c36",
    ],
    "dining": [
        "1617806118233-18e1de247200",
        "1533090161767-e6ffed986c88",
        "1449247709967-d4461a6a6103",
        "1595515106969-1ce29566ff1c",
        "1615874959474-d609969a20ed",
    ],
    "bedroom": [
        "1505693416388-ac5ce068fe85",
        "1522771739844-6a9f6d5f14af",
        "1560448204-e02f11c3d0e2",
        "1616594039964-ae9021a400a0",
        "1583847268964-b28dc8f51f92",
    ],
    "office": [
        "1518455027359-f3f8164ba6bd",
        "1593062096033-9a26b09da705",
        "1516382799247-87df95d790b7",
    ],
    "decor": [
        "1493809842364-78817add7ffb",
        "1567225557594-88d73e55f2cb",
    ],
    "outdoor": [
        "1600210492486-724fe5c67fb0",
        "1558211583-d26f610c1eb1",
        "1595429035839-c99c298ffdde",
    ],
    "kitchen": [
        "1556911220-bff31c812dba",
        "1600585154340-be6161a56a0c",
        "1584622650111-993a426fbf0a",
    ],
    "storage": [
        "1594026112284-02bb6f3352fe",
        "1503602642458-232111445657",
        "1558997519-83ea9252edf8",
    ],
}

#: Each catalogue subcategory slug maps to a broad room, so a product shows a
#: photo from the right space.
SUBCATEGORY_TO_BROAD: dict[str, str] = {
    "sofas-daybeds": "living", "coffee-tables": "living", "side-tables": "living",
    "tv-consoles": "living", "loungers": "living", "bookcases": "living",
    "dining-tables": "dining", "dining-chairs": "dining", "bar-stools": "dining",
    "sideboards": "dining", "serving-boards": "kitchen",
    "beds": "bedroom", "nightstands": "bedroom", "wardrobes": "bedroom",
    "dressers": "bedroom", "blanket-boxes": "bedroom", "chests-trunks": "storage",
    "desks": "office", "shelving": "office", "cabinets": "storage",
    "utensils": "kitchen", "spice-racks": "kitchen", "chopping-boards": "kitchen",
    "trays": "kitchen",
    "mirrors": "decor", "frames": "decor", "candle-holders": "decor",
    "planters": "outdoor", "garden-benches": "outdoor",
    "bespoke": "living",
}

_master_cache: dict[str, Image.Image | None] = {}


def _download_master(photo_id: str) -> Image.Image | None:
    """Fetch and cache one photo. Returns None if it cannot be fetched."""
    if photo_id in _master_cache:
        return _master_cache[photo_id]
    try:
        req = urllib.request.Request(_CDN.format(pid=photo_id), headers=_UA)
        data = urllib.request.urlopen(req, timeout=25, context=_ctx).read()
        image = Image.open(io.BytesIO(data)).convert("RGB")
        image.load()
    except Exception:
        image = None
    _master_cache[photo_id] = image
    return image


def photo_ids_for(subcategory: str, seed: str, count: int) -> list[str]:
    """Deterministically pick `count` distinct photos for a product.

    Seeded by the product slug so the same product always gets the same photos,
    and neighbouring products in a category get different ones.
    """
    pool = CATEGORY_PHOTOS.get(SUBCATEGORY_TO_BROAD.get(subcategory, "living"), [])
    if not pool:
        return []
    start = int(hashlib.sha256(seed.encode()).hexdigest(), 16) % len(pool)
    # Cycle the pool so a product always gets `count` ids even where the pool is
    # small; a repeated photo beats mixing a photo with a plate on one product.
    return [pool[(start + i) % len(pool)] for i in range(count)]


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


def write_photo(root: Path, rel_path: str, photo_id: str) -> dict | None:
    """Write one photo at every size. Returns metadata, or None on failure."""
    master = _download_master(photo_id)
    if master is None:
        return None

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
        "source": "curated",
        "checksum": hashlib.sha256(f"unsplash:{photo_id}".encode()).hexdigest(),
    }
