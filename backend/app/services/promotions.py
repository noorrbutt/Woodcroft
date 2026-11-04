"""Promotion lookups shared by storefront and checkout."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.promotion import FlashSale, FlashSaleItem


def active_flash_sale_discounts(
    db: Session,
    product_ids: list[uuid.UUID] | None = None,
    *,
    now: datetime | None = None,
) -> dict[uuid.UUID, int]:
    """Return each product's best eligible flash-sale rate at ``now``.

    ``FlashSale.is_active`` is synchronized by a background job and is not an
    authority for pricing. The sale window and unit cap are checked here so a
    delayed worker cannot change the price a shopper sees or pays.
    """
    if product_ids == []:
        return {}

    current_time = now or datetime.now(UTC)
    discount_bp = func.max(
        func.coalesce(FlashSaleItem.discount_bp, FlashSale.discount_bp)
    )
    conditions = [
        FlashSale.starts_at <= current_time,
        FlashSale.ends_at > current_time,
        (FlashSale.max_units.is_(None) | (FlashSale.units_sold < FlashSale.max_units)),
    ]
    if product_ids is not None:
        conditions.append(FlashSaleItem.product_id.in_(product_ids))

    rows = db.execute(
        select(FlashSaleItem.product_id, discount_bp)
        .join(FlashSale, FlashSale.id == FlashSaleItem.flash_sale_id)
        .where(*conditions)
        .group_by(FlashSaleItem.product_id)
    ).all()
    return {product_id: rate for product_id, rate in rows}
