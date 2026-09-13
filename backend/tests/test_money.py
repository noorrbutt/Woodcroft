"""Money arithmetic.

These are the highest-value tests in the codebase: every price the customer
sees, every invoice line and every analytics figure flows through this module,
so a rounding error here is a silent, compounding, money-losing bug.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.core.money import (
    apply_bp,
    clamp_non_negative,
    format_pkr,
    net_from_inclusive,
    paisa_to_rupees,
    percentage_of,
    rupees_to_paisa,
    tax_from_inclusive,
)

GST_BP = 1800  # 18.00%


class TestConversion:
    def test_rupees_to_paisa(self) -> None:
        assert rupees_to_paisa(1) == 100
        assert rupees_to_paisa(24_999) == 2_499_900
        assert rupees_to_paisa("11800.50") == 1_180_050

    def test_rupees_to_paisa_rounds_half_up(self) -> None:
        # 0.005 rupees == 0.5 paisa. Banker's rounding would give 0 here.
        assert rupees_to_paisa("0.005") == 1
        assert rupees_to_paisa("0.015") == 2

    def test_round_trip(self) -> None:
        assert paisa_to_rupees(2_499_900) == Decimal("24999.00")


class TestTax:
    def test_apply_bp(self) -> None:
        assert apply_bp(1_000_000, GST_BP) == 180_000

    def test_inclusive_split_is_exact(self) -> None:
        """net + tax must equal gross with zero residue.

        Deriving tax by subtraction rather than computing it directly is what
        guarantees this; computing both independently would leave a paisa adrift.
        """
        gross = 1_180_000  # Rs 11,800
        tax = tax_from_inclusive(gross, GST_BP)
        net = net_from_inclusive(gross, GST_BP)
        assert tax == 180_000
        assert net == 1_000_000
        assert net + tax == gross

    @pytest.mark.parametrize(
        "gross",
        [1, 99, 100, 12_345, 999_999, 1_180_000, 7_777_777, 123_456_789],
    )
    def test_inclusive_split_exact_for_awkward_amounts(self, gross: int) -> None:
        tax = tax_from_inclusive(gross, GST_BP)
        net = net_from_inclusive(gross, GST_BP)
        assert net + tax == gross, f"residue at gross={gross}"
        assert tax >= 0
        assert net >= 0

    def test_both_tax_modes_charge_the_customer_the_same(self) -> None:
        """The core cross-mode invariant.

        Inclusive Rs 11,800 and exclusive Rs 10,000 + 18% must produce an
        identical customer-facing total. If this ever fails, flipping the store
        setting silently changes what people are charged.
        """
        inclusive_total = 1_180_000
        inclusive_net = net_from_inclusive(inclusive_total, GST_BP)

        exclusive_net = 1_000_000
        exclusive_total = exclusive_net + apply_bp(exclusive_net, GST_BP)

        assert inclusive_net == exclusive_net
        assert inclusive_total == exclusive_total

    def test_zero_rated(self) -> None:
        assert apply_bp(1_000_000, 0) == 0
        assert tax_from_inclusive(1_000_000, 0) == 0
        assert net_from_inclusive(1_000_000, 0) == 1_000_000


class TestDiscounts:
    def test_percentage_of(self) -> None:
        assert percentage_of(1_000_000, 10) == 100_000
        assert percentage_of(1_000_000, Decimal("12.5")) == 125_000

    def test_percentage_rounds_half_up(self) -> None:
        # 5% of 25 paisa = 1.25 -> 1; of 30 paisa = 1.5 -> 2 (not 2 then 2).
        assert percentage_of(25, 5) == 1
        assert percentage_of(30, 5) == 2

    def test_clamp_non_negative(self) -> None:
        """A discount larger than the line must not produce negative money."""
        assert clamp_non_negative(-500) == 0
        assert clamp_non_negative(0) == 0
        assert clamp_non_negative(500) == 500


class TestFormatting:
    def test_grouping_and_prefix(self) -> None:
        assert format_pkr(2_499_900) == "Rs 24,999"
        assert format_pkr(100) == "Rs 1"
        assert format_pkr(0) == "Rs 0"

    def test_with_decimals(self) -> None:
        assert format_pkr(2_499_950, with_decimals=True) == "Rs 24,999.50"
        assert format_pkr(100, with_decimals=True) == "Rs 1.00"

    def test_negative(self) -> None:
        assert format_pkr(-2_499_900) == "-Rs 24,999"

    def test_rounds_to_nearest_rupee_without_decimals(self) -> None:
        assert format_pkr(2_499_949) == "Rs 24,999"
        assert format_pkr(2_499_950) == "Rs 25,000"

    def test_large_amount_grouping(self) -> None:
        # Western grouping, deliberately not the lakh/crore system: Pakistani
        # e-commerce sites overwhelmingly display thousands separators.
        assert format_pkr(150_000_000) == "Rs 1,500,000"
