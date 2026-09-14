"""number sequences and guest order access token

Adds the three reference-number sequences (order, ticket, return) that replace
the old COUNT(*)+1 minting, and the guest order access token.

Revision ID: b2f1a9c4d7e3
Revises: cb4be3241cfb
Create Date: 2026-09-14 12:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b2f1a9c4d7e3"
down_revision: str | None = "cb4be3241cfb"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE SEQUENCE IF NOT EXISTS order_number_seq")
    op.execute("CREATE SEQUENCE IF NOT EXISTS ticket_number_seq")
    op.execute("CREATE SEQUENCE IF NOT EXISTS return_number_seq")
    op.add_column(
        "order",
        sa.Column("access_token", sa.String(length=64), nullable=True),
    )
    op.create_index("ix_order_access_token", "order", ["access_token"])

    # Allow admin-uploaded product images alongside generated and curated ones.
    op.drop_constraint("ck_product_image_source_is_known", "product_image", type_="check")
    op.create_check_constraint(
        "ck_product_image_source_is_known",
        "product_image",
        "source IN ('generated', 'curated', 'uploaded')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_product_image_source_is_known", "product_image", type_="check")
    op.create_check_constraint(
        "ck_product_image_source_is_known",
        "product_image",
        "source IN ('generated', 'curated')",
    )
    op.drop_index("ix_order_access_token", table_name="order")
    op.drop_column("order", "access_token")
    op.execute("DROP SEQUENCE IF EXISTS return_number_seq")
    op.execute("DROP SEQUENCE IF EXISTS ticket_number_seq")
    op.execute("DROP SEQUENCE IF EXISTS order_number_seq")
