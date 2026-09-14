"""Postgres sequences for human-facing reference numbers.

Order, ticket and return numbers were previously minted with ``COUNT(*) + 1``,
which is racy (two concurrent inserts compute the same number and the second
hits the UNIQUE constraint), goes backwards if any row is deleted, and needs a
full table scan. A sequence is atomic, monotonic and gap-tolerant.

The sequences are bound to ``Base.metadata`` so ``create_all`` emits them in
dev and test; the initial Alembic migration creates them for production.
"""

from __future__ import annotations

from sqlalchemy import Sequence

from app.db.base import Base

order_number_seq = Sequence("order_number_seq", metadata=Base.metadata)
ticket_number_seq = Sequence("ticket_number_seq", metadata=Base.metadata)
return_number_seq = Sequence("return_number_seq", metadata=Base.metadata)
