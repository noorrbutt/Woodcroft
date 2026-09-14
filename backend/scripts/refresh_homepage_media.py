"""Install real, art-directed homepage imagery from Pexels.

Runs in place against the current database (no destructive re-seed):

  * the hero  -> a dark, hand-tool workshop photo (replaces the generated
    wood-field texture, which reads as a flat brown blur under the scrim),
  * the story band image -> a warm board-planing shot,
  * every top-level category -> a matching room/material photo, and each
    category's ``image_path`` is pointed at it so the homepage bento wall shows
    real timber instead of blank plaques.

The photo ids below are the ones hand-picked when this was first built; if an id
ever fails to download the code falls back to a fresh keyword search so the run
still completes. Media lives outside git (generated), so this is the documented,
repeatable way to restore homepage imagery after a fresh seed.

    PEXELS_API_KEY=... python -m scripts.refresh_homepage_media

Run from the backend/ directory.
"""

from __future__ import annotations

import io
import json
import ssl
import sys
import urllib.parse
import urllib.request
from pathlib import Path

from PIL import Image
from sqlalchemy import text

from app.core.config import settings
from app.db.session import SessionLocal
from app.services.media.pexels import api_key

_CTX = ssl.create_default_context()
_UA = "WoodcroftCatalog/1.0"

# Hand-picked, vetted Pexels photo ids with a keyword fallback each.
HERO = (5711877, "carpenter woodworking hand tools chisel")
STORY = (313776, "carpenter planing wood workshop")
CATEGORIES: dict[str, tuple[int, str]] = {
    "living": (39134599, "wooden sofa living room interior"),
    "dining": (8113029, "wooden dining table chairs"),
    "bedroom": (9389329, "wooden bed frame bedroom"),
    "office": (5393443, "wooden writing desk home office"),
    "kitchen-dining": (7129385, "wooden cutting board kitchen"),
    "decor": (8218186, "round wooden wall mirror"),
    "storage": (34558080, "wooden cabinet sideboard drawers"),
    "outdoor": (15676408, "wooden garden bench patio"),
    "bespoke": (5974241, "carpenter woodworking hands craft"),
}


def _get(url: str, key: str | None = None) -> bytes:
    headers = {"User-Agent": _UA}
    if key:
        headers["Authorization"] = key
    req = urllib.request.Request(url, headers=headers)
    return urllib.request.urlopen(req, timeout=30, context=_CTX).read()


def _by_id(pid: int, key: str) -> Image.Image | None:
    try:
        meta = json.loads(_get(f"https://api.pexels.com/v1/photos/{pid}", key))
        return Image.open(io.BytesIO(_get(meta["src"]["original"]))).convert("RGB")
    except Exception:
        return None


def _by_query(query: str, key: str, orientation: str) -> Image.Image | None:
    params = urllib.parse.urlencode(
        {"query": query, "orientation": orientation, "per_page": 5}
    )
    try:
        data = json.loads(_get(f"https://api.pexels.com/v1/search?{params}", key))
        for photo in data.get("photos", []):
            url = photo["src"].get("original")
            if not url:
                continue
            try:
                return Image.open(io.BytesIO(_get(url))).convert("RGB")
            except Exception:
                continue
    except Exception:
        return None
    return None


def _fetch(pid: int, query: str, key: str, orientation: str) -> Image.Image | None:
    return _by_id(pid, key) or _by_query(query, key, orientation)


def _crop(image: Image.Image, ratio: float) -> Image.Image:
    """Centre-crop to width/height ``ratio``."""
    w, h = image.size
    if w / h > ratio:
        nw = int(h * ratio)
        left = (w - nw) // 2
        return image.crop((left, 0, left + nw, h))
    nh = int(w / ratio)
    top = (h - nh) // 2
    return image.crop((0, top, w, top + nh))


def _write(master: Image.Image, base: Path, widths: tuple[int, ...]) -> None:
    base.parent.mkdir(parents=True, exist_ok=True)
    for width in widths:
        img = master.copy()
        if img.width > width:
            img = img.resize((width, round(img.height * width / img.width)), Image.LANCZOS)
        img.save(f"{base}_{width}.webp", "WEBP", quality=84, method=4)


def main() -> int:
    key = api_key()
    if not key:
        print("PEXELS_API_KEY is not set. Nothing to do.")
        return 1

    root = Path(settings.MEDIA_ROOT if hasattr(settings, "MEDIA_ROOT") else "media")
    if not root.exists():
        root = Path("media")

    # Hero (dark hand-tool workshop), 16:9.
    hero = _fetch(*HERO, key, "landscape")
    if hero is not None:
        _write(_crop(hero, 16 / 9), root / "hero" / "workshop", (800, 1600, 2400))
        print("hero: ok")
    else:
        print("hero: FAILED (kept existing)")

    # Story band image (warm planing shot), 5:4.
    story = _fetch(*STORY, key, "landscape")
    if story is not None:
        _write(_crop(story, 5 / 4), root / "hero" / "story", (800, 1600))
        print("story: ok")
    else:
        print("story: FAILED (kept existing)")

    # Category tiles, 4:5, plus the DB pointer.
    done: list[str] = []
    with SessionLocal() as session:
        for slug, (pid, query) in CATEGORIES.items():
            image = _fetch(pid, query, key, "portrait")
            if image is None:
                print(f"category {slug}: FAILED (skipped)")
                continue
            _write(_crop(image, 4 / 5), root / "categories" / slug, (400, 800, 1600))
            session.execute(
                text("UPDATE category SET image_path = :p WHERE slug = :s"),
                {"p": f"categories/{slug}", "s": slug},
            )
            done.append(slug)
        session.commit()
    print(f"categories: {len(done)} updated -> {', '.join(done)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
