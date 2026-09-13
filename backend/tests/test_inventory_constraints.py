"""Inventory invariants.

Overselling is the failure mode that costs a furniture retailer real money and
real reputation: two shoppers buy the last hand-made table, and one of them gets
an apologetic phone call. These tests assert the database itself refuses to let
that happen, independent of whatever the application layer does.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError


@pytest.fixture
def variant_id(raw):
    cat = raw.execute(
        text(
            "INSERT INTO category (name, slug, path, depth) "
            "VALUES ('Dining', 'dining', 'dining', 0) RETURNING id"
        )
    ).scalar_one()
    prod = raw.execute(
        text(
            "INSERT INTO product (category_id, name, slug, base_price_paisa, status) "
            "VALUES (:c, 'Sheesham Table', 'sheesham-table', 2499900, 'active') "
            "RETURNING id"
        ),
        {"c": cat},
    ).scalar_one()
    return raw.execute(
        text(
            "INSERT INTO product_variant (product_id, sku) "
            "VALUES (:p, 'WC-SHE-001') RETURNING id"
        ),
        {"p": prod},
    ).scalar_one()


def _stock(raw, variant_id, on_hand=10, reserved=0):
    return raw.execute(
        text(
            "INSERT INTO stock_level (variant_id, on_hand, reserved) "
            "VALUES (:v, :o, :r) RETURNING id"
        ),
        {"v": variant_id, "o": on_hand, "r": reserved},
    ).scalar_one()


class TestAvailableIsGenerated:
    def test_available_is_on_hand_minus_reserved(self, raw, variant_id) -> None:
        _stock(raw, variant_id, on_hand=10, reserved=3)
        available = raw.execute(
            text("SELECT available FROM stock_level WHERE variant_id = :v"),
            {"v": variant_id},
        ).scalar_one()
        assert available == 7

    def test_available_tracks_updates(self, raw, variant_id) -> None:
        """Being generated, it cannot drift from its inputs."""
        _stock(raw, variant_id, on_hand=10, reserved=0)
        raw.execute(
            text("UPDATE stock_level SET reserved = 4 WHERE variant_id = :v"),
            {"v": variant_id},
        )
        available = raw.execute(
            text("SELECT available FROM stock_level WHERE variant_id = :v"),
            {"v": variant_id},
        ).scalar_one()
        assert available == 6

    def test_available_cannot_be_written_directly(self, raw, variant_id) -> None:
        """One definition of sellable quantity, and no way to contradict it."""
        _stock(raw, variant_id)
        with pytest.raises(Exception):
            raw.execute(
                text("UPDATE stock_level SET available = 999 WHERE variant_id = :v"),
                {"v": variant_id},
            )


class TestOversellGuard:
    def test_cannot_reserve_more_than_on_hand(self, raw, variant_id) -> None:
        """The hard stop against overselling."""
        with pytest.raises(IntegrityError):
            _stock(raw, variant_id, on_hand=3, reserved=4)

    def test_reserving_exactly_all_stock_is_allowed(self, raw, variant_id) -> None:
        _stock(raw, variant_id, on_hand=3, reserved=3)

    def test_cannot_raise_reservation_above_stock(self, raw, variant_id) -> None:
        _stock(raw, variant_id, on_hand=5, reserved=2)
        with pytest.raises(IntegrityError):
            raw.execute(
                text("UPDATE stock_level SET reserved = 6 WHERE variant_id = :v"),
                {"v": variant_id},
            )

    def test_cannot_drop_stock_below_existing_reservations(self, raw, variant_id) -> None:
        """Shrinking on_hand must not strand reservations above it."""
        _stock(raw, variant_id, on_hand=5, reserved=4)
        with pytest.raises(IntegrityError):
            raw.execute(
                text("UPDATE stock_level SET on_hand = 2 WHERE variant_id = :v"),
                {"v": variant_id},
            )

    def test_negative_stock_rejected(self, raw, variant_id) -> None:
        with pytest.raises(IntegrityError):
            _stock(raw, variant_id, on_hand=-1)

    def test_one_stock_row_per_variant(self, raw, variant_id) -> None:
        _stock(raw, variant_id)
        with pytest.raises(IntegrityError):
            _stock(raw, variant_id)


class TestReservations:
    def test_quantity_must_be_positive(self, raw, variant_id) -> None:
        with pytest.raises(IntegrityError):
            raw.execute(
                text(
                    "INSERT INTO stock_reservation "
                    "(variant_id, quantity, expires_at) "
                    "VALUES (:v, 0, now() + interval '20 minutes')"
                ),
                {"v": variant_id},
            )

    def test_expired_active_reservations_are_findable(self, raw, variant_id) -> None:
        """This query is the background sweeper's hot path."""
        raw.execute(
            text(
                "INSERT INTO stock_reservation (variant_id, quantity, expires_at, status) "
                "VALUES (:v, 2, now() - interval '1 minute', 'active'), "
                "       (:v, 1, now() + interval '20 minutes', 'active'), "
                "       (:v, 1, now() - interval '1 hour', 'released')"
            ),
            {"v": variant_id},
        )
        due = raw.execute(
            text(
                "SELECT count(*) FROM stock_reservation "
                "WHERE status = 'active' AND expires_at < now()"
            )
        ).scalar_one()
        assert due == 1


class TestMovementLedger:
    def test_zero_delta_rejected(self, raw, variant_id) -> None:
        """A movement that moves nothing is a bug, not a record."""
        with pytest.raises(IntegrityError):
            raw.execute(
                text(
                    "INSERT INTO stock_movement "
                    "(variant_id, delta, balance_after, reason) "
                    "VALUES (:v, 0, 10, 'correction')"
                ),
                {"v": variant_id},
            )

    def test_negative_balance_rejected(self, raw, variant_id) -> None:
        with pytest.raises(IntegrityError):
            raw.execute(
                text(
                    "INSERT INTO stock_movement "
                    "(variant_id, delta, balance_after, reason) "
                    "VALUES (:v, -5, -2, 'sale')"
                ),
                {"v": variant_id},
            )

    def test_ledger_sums_to_current_balance(self, raw, variant_id) -> None:
        """The audit property: replaying deltas reproduces the balance."""
        raw.execute(
            text(
                "INSERT INTO stock_movement "
                "(variant_id, delta, balance_after, reason) VALUES "
                "(:v,  20, 20, 'initial'), "
                "(:v,  -3, 17, 'sale'), "
                "(:v,  -2, 15, 'sale'), "
                "(:v,   1, 16, 'return'), "
                "(:v,  -4, 12, 'damage')"
            ),
            {"v": variant_id},
        )
        total, final = raw.execute(
            text(
                "SELECT sum(delta), "
                "       (SELECT balance_after FROM stock_movement "
                "        WHERE variant_id = :v ORDER BY created_at DESC, id DESC LIMIT 1) "
                "FROM stock_movement WHERE variant_id = :v"
            ),
            {"v": variant_id},
        ).one()
        assert total == final == 12
