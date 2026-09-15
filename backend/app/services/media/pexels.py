"""Real product photos via the Pexels search API.

Keyless image search is blocked or unreliable from most environments (Unsplash
and DuckDuckGo refuse it; Openverse/Wikimedia are flaky), so matching a photo to
a product type needs a search API. Pexels is free, its key is instant, its
licence allows commercial use with no attribution, and its image CDN downloads
reliably. Each catalogue subcategory maps to a plain search term ("wooden dining
chair"), so a dining chair shows a dining chair. Results are downloaded once,
cropped to the catalogue's 4:5 aspect and run through the same webp+blur pipeline
as everything else, so they are served locally and load instantly.

Set PEXELS_API_KEY in the environment or backend/.env. Without it, callers fall
back to the generated placeholder card.
"""

from __future__ import annotations

import hashlib
import io
import json
import ssl
import urllib.parse
import urllib.request
from pathlib import Path

from PIL import Image

from app.core.config import settings
from app.services.media.plates import SIZES, blur_data_url

_ctx = ssl.create_default_context()
_UA = "WoodcroftCatalog/1.0"

#: Each catalogue subcategory -> a plain-English search term for the exact item.
SUBCATEGORY_QUERY: dict[str, str] = {
    "sofas-daybeds": "wooden sofa living room",
    "coffee-tables": "wooden center table living room",
    "side-tables": "wooden side table",
    "tv-consoles": "wooden tv console media unit",
    "loungers": "wooden lounge chair",
    "bookcases": "wooden bookcase bookshelf",
    "dining-tables": "wooden dining table",
    "dining-chairs": "wooden dining chair",
    "bar-stools": "wooden bar stool",
    "sideboards": "wooden sideboard buffet",
    "serving-boards": "wooden serving board",
    "beds": "wooden bed frame",
    "nightstands": "wooden nightstand bedside table",
    "wardrobes": "wooden wardrobe closet",
    "dressers": "wooden dresser chest of drawers",
    "blanket-boxes": "wooden blanket box ottoman",
    "chests-trunks": "wooden storage chest trunk",
    "desks": "wooden desk",
    "shelving": "wooden wall shelf",
    "cabinets": "wooden cabinet",
    "utensils": "wooden kitchen utensils",
    "spice-racks": "wooden spice rack",
    "chopping-boards": "wooden chopping board",
    "trays": "wooden serving tray",
    "mirrors": "wooden framed mirror",
    "frames": "wooden picture frame",
    "candle-holders": "wooden candle holder",
    "planters": "wooden planter pot",
    "garden-benches": "wooden garden bench",
    "bespoke": "handmade wooden furniture",
}

# Cache search results and downloaded masters within a run.
_search_cache: dict[str, list[str]] = {}
_master_cache: dict[str, Image.Image | None] = {}


def api_key() -> str | None:
    return settings.PEXELS_API_KEY or None


def _search(query: str, key: str) -> list[str]:
    """Return candidate image URLs for a query, portrait-first, cached."""
    if query in _search_cache:
        return _search_cache[query]
    params = urllib.parse.urlencode(
        {"query": query, "orientation": "portrait", "per_page": 12}
    )
    req = urllib.request.Request(
        f"https://api.pexels.com/v1/search?{params}",
        headers={"Authorization": key, "User-Agent": _UA},
    )
    urls: list[str] = []
    try:
        data = json.loads(urllib.request.urlopen(req, timeout=25, context=_ctx).read())
        for photo in data.get("photos", []):
            src = photo.get("src", {})
            # portrait is already ~4:5-ish; fall back to the original.
            urls.append(src.get("portrait") or src.get("large") or src.get("original"))
    except Exception:
        urls = []
    urls = [u for u in urls if u]
    _search_cache[query] = urls
    return urls


def _download(url: str) -> Image.Image | None:
    if url in _master_cache:
        return _master_cache[url]
    try:
        req = urllib.request.Request(url, headers={"User-Agent": _UA})
        data = urllib.request.urlopen(req, timeout=25, context=_ctx).read()
        image = Image.open(io.BytesIO(data)).convert("RGB")
        image.load()
    except Exception:
        image = None
    _master_cache[url] = image
    return image


def _crop_4x5(image: Image.Image) -> Image.Image:
    """Centre-crop to a 4:5 portrait."""
    target = 4 / 5
    w, h = image.size
    if w / h > target:
        new_w = int(h * target)
        left = (w - new_w) // 2
        image = image.crop((left, 0, left + new_w, h))
    else:
        new_h = int(w / target)
        top = (h - new_h) // 2
        image = image.crop((0, top, w, top + new_h))
    return image


def fetch_for(subcategory: str, seed: str, key: str) -> Image.Image | None:
    """Pick a matching photo for a product, deterministically by seed."""
    query = SUBCATEGORY_QUERY.get(subcategory, "handmade wooden furniture")
    urls = _search(query, key)
    if not urls:
        return None
    idx = int(hashlib.sha256(seed.encode()).hexdigest(), 16) % len(urls)
    # Try the chosen result, then walk forward until one downloads.
    for offset in range(len(urls)):
        image = _download(urls[(idx + offset) % len(urls)])
        if image is not None:
            return image
    return None


def write_search_photo(
    root: Path, rel_path: str, subcategory: str, seed: str, key: str
) -> dict | None:
    """Write a matched Pexels photo at every size. None if none could be fetched."""
    master = fetch_for(subcategory, seed, key)
    if master is None:
        return None
    master = _crop_4x5(master)

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
        "checksum": hashlib.sha256(f"pexels:{rel_path}".encode()).hexdigest(),
    }
