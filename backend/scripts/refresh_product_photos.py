"""Replace product images with real, type-matched photos from Pexels.

Runs in place against the current database (no destructive re-seed): for each
product it searches Pexels for the product's item type (dining chair, wardrobe,
dresser...), downloads a matching photo, crops to 4:5 and writes the webp family.
Any product whose photo cannot be fetched keeps a generated placeholder card, so
the catalogue never ends up with a broken image.

    PEXELS_API_KEY=... python -m scripts.refresh_product_photos

Run from the backend/ directory.
"""

from __future__ import annotations

import shutil
import sys

from sqlalchemy import delete, select

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.catalog import Category, Product, ProductImage
from app.models.enums import WoodSpecies
from app.services.media.pexels import api_key, write_search_photo
from app.services.media.photos import write_placeholder


def main() -> int:
    key = api_key()
    if not key:
        print("PEXELS_API_KEY is not set. Get a free key at "
              "https://www.pexels.com/api/ and export it, then re-run.")
        return 1

    db = SessionLocal()
    root = settings.media_path
    products = db.scalars(select(Product)).all()
    matched = placeholder = 0

    for i, product in enumerate(products, 1):
        category = db.get(Category, product.category_id)
        subcategory = category.slug if category else "bespoke"
        wood = product.wood_species or WoodSpecies.SHEESHAM

        db.execute(delete(ProductImage).where(ProductImage.product_id == product.id))
        pdir = root / "products" / product.slug
        if pdir.exists():
            shutil.rmtree(pdir, ignore_errors=True)

        rel = f"products/{product.slug}/0"
        meta = write_search_photo(root, rel, subcategory, product.slug, key)
        if meta is not None:
            matched += 1
        else:
            meta = write_placeholder(root, rel, wood, product.name)
            placeholder += 1

        db.add(ProductImage(
            product_id=product.id,
            alt_text=product.name,
            sort_order=0,
            is_primary=True,
            **meta,
        ))
        if i % 20 == 0:
            db.commit()
            print(f"  {i}/{len(products)} processed "
                  f"({matched} photos, {placeholder} placeholders)")

    db.commit()
    db.close()
    print(f"\nDone: {matched} real photos, {placeholder} placeholders "
          f"across {len(products)} products.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
