"""Add order idempotency keys.

Revision ID: a4c97e1d2b6f
Revises: c7a3e1b9f24d
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "a4c97e1d2b6f"
down_revision = "c7a3e1b9f24d"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("order", sa.Column("idempotency_key", sa.String(length=128)))
    op.create_index(
        "uq_order_idempotency_key",
        "order",
        ["idempotency_key"],
        unique=True,
        postgresql_where=sa.text("idempotency_key IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_order_idempotency_key", table_name="order")
    op.drop_column("order", "idempotency_key")
