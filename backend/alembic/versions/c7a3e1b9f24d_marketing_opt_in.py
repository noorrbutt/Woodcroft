"""Marketing email is opt-in: default email_marketing to false.

Also clears the flag for existing rows, which were auto-enrolled under the old
default and never gave consent (PECA / anti-spam).

Revision ID: c7a3e1b9f24d
Revises: b2f1a9c4d7e3
Create Date: 2026-09-15
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "c7a3e1b9f24d"
down_revision = "b2f1a9c4d7e3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "notification_preference",
        "email_marketing",
        server_default=sa.text("false"),
    )
    # Existing accounts were enrolled without consent; turn marketing off for them.
    op.execute("UPDATE notification_preference SET email_marketing = false")


def downgrade() -> None:
    op.alter_column(
        "notification_preference",
        "email_marketing",
        server_default=sa.text("true"),
    )
