"""Cloudinary upload for admin-provided product photos.

Serving media is just a base-URL swap: ``MEDIA_URL`` points at the Cloudinary
delivery prefix and ``media_url()`` builds ``<prefix>/<base_path>_<size>.webp``.
This module handles the write side so an admin upload lands in Cloudinary rather
than the ephemeral serverless filesystem. Each size is uploaded with public id
``<base_path>_<size>`` so the delivered URL matches what ``media_url()`` builds,
and the ProductImage metadata is identical to the local ``write_upload`` path.
"""

from __future__ import annotations

import hashlib
import io

import cloudinary
import cloudinary.uploader
from PIL import Image

from app.core.config import settings
from app.services.media.plates import SIZES, blur_data_url


def _configure() -> None:
    cloudinary.config(
        cloud_name=settings.CLOUDINARY_CLOUD_NAME,
        api_key=settings.CLOUDINARY_API_KEY,
        api_secret=settings.CLOUDINARY_API_SECRET,
        secure=True,
    )


def cloud_write_upload(rel_path: str, data: bytes) -> dict:
    """Process bytes into the webp size family and upload each to Cloudinary.

    Mirrors ``app.services.media.photos.write_upload`` but writes to Cloudinary.
    Raises ValueError if the bytes are not a decodable image.
    """
    try:
        master = Image.open(io.BytesIO(data)).convert("RGB")
        master.load()
    except Exception as exc:  # noqa: BLE001 - turned into a clean 4xx by the caller
        raise ValueError("That file is not a readable image.") from exc

    _configure()
    for size in SIZES:
        scaled = master.copy()
        scaled.thumbnail((size, size * 2), Image.LANCZOS)
        buf = io.BytesIO()
        scaled.save(buf, "WEBP", quality=82, method=2)
        buf.seek(0)
        cloudinary.uploader.upload(
            buf,
            public_id=f"{rel_path}_{size}",
            resource_type="image",
            format="webp",
            overwrite=True,
            invalidate=True,
        )

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
