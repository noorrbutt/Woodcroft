"""The pricing engine.

Every price a customer sees and every figure in the admin reports comes through
here, so these are the tests that matter most in the codebase. The cross mode
test in particular guards a setting an admin can flip in the UI: if inclusive
and exclusive ever disagree, flipping it silently changes what people pay.
"""

from __future__ import annotations

import uuid

import pytest

from app.models.enums import DiscountKind, TaxMode
from app.services.pricing import (
    CouponInput,
    LineInput,
    PersonalizationChoice,
    QuoteRequest,
    allocate_proportionally,
    quote,
)

GST = 1800
RS = 100  # paisa per rupee


def vid() -> uuid.UUID:
    return uuid.uuid4()


def line(price_rs: int, qty: int = 1, **kw) -> LineInput:
    return LineInput(
        variant_id=vid(), quantity=qty, unit_price_paisa=price_rs * RS, **kw
    )


class TestAllocation:
    def test_parts_sum_to_the_whole(self) -> None:
        parts = allocate_proportionally(1000, [3333, 3333, 3334])
        assert sum(parts) == 1000

    def test_awkward_split_still_balances(self) -> None:
        """Three equal lines sharing 100 paisa cannot divide evenly."""
        parts = allocate_proportionally(100, [1, 1, 1])
        assert sum(parts) == 100
        assert sorted(parts) == [33, 33, 34]

    def test_proportional_to_weights(self) -> None:
        parts = allocate_proportionally(300, [100, 200])
        assert parts == [100, 200]

    def test_zero_total(self) -> None:
        assert allocate_proportionally(0, [10, 20]) == [0, 0]

    def test_zero_weights(self) -> None:
        assert allocate_proportionally(500, [0, 0]) == [0, 0]

    @pytest.mark.parametrize("total", [1, 7, 99, 101, 9999, 123_457])
    def test_always_balances(self, total: int) -> None:
        parts = allocate_proportionally(total, [7, 11, 13, 17, 19])
        assert sum(parts) == total


class TestBasics:
    def test_single_line(self) -> None:
        q = quote(QuoteRequest(lines=(line(11_800),), tax_rate_bp=GST))
        assert q.subtotal_paisa == 11_800 * RS
        assert q.total_paisa == 11_800 * RS

    def test_quantity_multiplies(self) -> None:
        q = quote(QuoteRequest(lines=(line(1_000, qty=3),), tax_rate_bp=GST))
        assert q.subtotal_paisa == 3_000 * RS
        assert q.item_count == 3

    def test_empty_basket(self) -> None:
        q = quote(QuoteRequest(lines=()))
        assert q.total_paisa == 0
        assert q.item_count == 0


class TestTaxModes:
    """The invariant that protects every price in the store."""

    def test_inclusive_extracts_tax(self) -> None:
        q = quote(
            QuoteRequest(
                lines=(line(11_800),), tax_mode=TaxMode.INCLUSIVE, tax_rate_bp=GST
            )
        )
        assert q.total_paisa == 11_800 * RS  # customer pays the shelf price
        assert q.tax_paisa == 1_800 * RS
        assert q.net_paisa == 10_000 * RS

    def test_exclusive_adds_tax(self) -> None:
        q = quote(
            QuoteRequest(
                lines=(line(10_000),), tax_mode=TaxMode.EXCLUSIVE, tax_rate_bp=GST
            )
        )
        assert q.net_paisa == 10_000 * RS
        assert q.tax_paisa == 1_800 * RS
        assert q.total_paisa == 11_800 * RS

    def test_both_modes_charge_the_same(self) -> None:
        inclusive = quote(
            QuoteRequest(
                lines=(line(11_800),), tax_mode=TaxMode.INCLUSIVE, tax_rate_bp=GST
            )
        )
        exclusive = quote(
            QuoteRequest(
                lines=(line(10_000),), tax_mode=TaxMode.EXCLUSIVE, tax_rate_bp=GST
            )
        )
        assert inclusive.total_paisa == exclusive.total_paisa
        assert inclusive.tax_paisa == exclusive.tax_paisa
        assert inclusive.net_paisa == exclusive.net_paisa

    def test_net_plus_tax_equals_subtotal_inclusive(self) -> None:
        q = quote(
            QuoteRequest(
                lines=(line(7_777), line(3_333, qty=2)),
                tax_mode=TaxMode.INCLUSIVE,
                tax_rate_bp=GST,
            )
        )
        for ln in q.lines:
            assert ln.net_paisa + ln.tax_paisa == ln.subtotal_paisa

    def test_zero_rated_category(self) -> None:
        q = quote(
            QuoteRequest(
                lines=(line(5_000, tax_rate_bp=0),),
                tax_mode=TaxMode.INCLUSIVE,
                tax_rate_bp=GST,
            )
        )
        assert q.tax_paisa == 0
        assert q.total_paisa == 5_000 * RS

    def test_mixed_rates_across_lines(self) -> None:
        q = quote(
            QuoteRequest(
                lines=(line(11_800), line(5_000, tax_rate_bp=0)),
                tax_mode=TaxMode.INCLUSIVE,
                tax_rate_bp=GST,
            )
        )
        assert q.lines[0].tax_paisa == 1_800 * RS
        assert q.lines[1].tax_paisa == 0


class TestPersonalization:
    def test_flat_surcharge(self) -> None:
        engraving = PersonalizationChoice(
            key="engraving", label="Engraving", value="Ayesha",
            surcharge_paisa=500 * RS,
        )
        q = quote(QuoteRequest(lines=(line(10_000, personalizations=(engraving,)),)))
        assert q.lines[0].personalization_surcharge_paisa == 500 * RS
        assert q.subtotal_paisa == 10_500 * RS

    def test_per_character_surcharge(self) -> None:
        engraving = PersonalizationChoice(
            key="engraving", label="Engraving", value="Ayesha",  # 6 characters
            surcharge_paisa=200 * RS, surcharge_per_char_paisa=50 * RS,
        )
        q = quote(QuoteRequest(lines=(line(10_000, personalizations=(engraving,)),)))
        assert q.lines[0].personalization_surcharge_paisa == (200 + 6 * 50) * RS

    def test_surcharge_applies_per_unit(self) -> None:
        """Engraving three boards means engraving three times."""
        engraving = PersonalizationChoice(
            key="engraving", label="Engraving", value="AB", surcharge_paisa=300 * RS
        )
        q = quote(
            QuoteRequest(lines=(line(1_000, qty=3, personalizations=(engraving,)),))
        )
        assert q.subtotal_paisa == (1_000 + 300) * 3 * RS

    def test_whitespace_does_not_inflate_charge(self) -> None:
        choice = PersonalizationChoice(
            key="engraving", label="Engraving", value="  AB  ",
            surcharge_per_char_paisa=100 * RS,
        )
        q = quote(QuoteRequest(lines=(line(1_000, personalizations=(choice,)),)))
        assert q.lines[0].personalization_surcharge_paisa == 2 * 100 * RS


class TestDiscounts:
    def test_flash_sale_percentage(self) -> None:
        q = quote(QuoteRequest(lines=(line(10_000, flash_sale_bp=2000),)))
        assert q.lines[0].line_discount_paisa == 2_000 * RS
        assert q.subtotal_paisa == 8_000 * RS

    def test_best_line_discount_wins_and_they_do_not_stack(self) -> None:
        q = quote(
            QuoteRequest(lines=(line(10_000, flash_sale_bp=1000, auto_discount_bp=2500),))
        )
        # 25 percent beats 10 percent, and only one is applied.
        assert q.lines[0].line_discount_paisa == 2_500 * RS

    def test_coupon_percentage(self) -> None:
        q = quote(
            QuoteRequest(
                lines=(line(10_000),),
                coupon=CouponInput("SAVE10", DiscountKind.PERCENTAGE, value_bp=1000),
            )
        )
        assert q.discount_paisa == 1_000 * RS
        assert q.subtotal_paisa == 9_000 * RS

    def test_coupon_cap(self) -> None:
        q = quote(
            QuoteRequest(
                lines=(line(100_000),),
                coupon=CouponInput(
                    "BIG", DiscountKind.PERCENTAGE, value_bp=2000,
                    max_discount_paisa=5_000 * RS,
                ),
            )
        )
        assert q.discount_paisa == 5_000 * RS

    def test_coupon_below_minimum_is_rejected(self) -> None:
        q = quote(
            QuoteRequest(
                lines=(line(1_000),),
                coupon=CouponInput(
                    "SAVE10", DiscountKind.PERCENTAGE, value_bp=1000,
                    min_order_paisa=5_000 * RS,
                ),
            )
        )
        assert q.discount_paisa == 0
        assert q.coupon_error == "minimum_order_not_met"

    def test_coupon_allocation_sums_to_the_discount(self) -> None:
        """Allocated shares must reconstruct the order level discount exactly."""
        q = quote(
            QuoteRequest(
                lines=(line(3_333), line(3_333), line(3_334)),
                coupon=CouponInput("SAVE10", DiscountKind.PERCENTAGE, value_bp=1000),
            )
        )
        allocated = sum(ln.allocated_discount_paisa for ln in q.lines)
        assert allocated == q.discount_paisa

    def test_fixed_coupon_cannot_exceed_basket(self) -> None:
        q = quote(
            QuoteRequest(
                lines=(line(500),),
                coupon=CouponInput(
                    "HUGE", DiscountKind.FIXED_AMOUNT, value_paisa=10_000 * RS
                ),
            )
        )
        assert q.total_paisa == 0
        assert q.subtotal_paisa == 0

    def test_free_shipping_coupon(self) -> None:
        q = quote(
            QuoteRequest(
                lines=(line(5_000),), shipping_paisa=500 * RS, free_shipping=True
            )
        )
        assert q.shipping_paisa == 0


class TestExtras:
    def test_shipping_and_cod_added(self) -> None:
        q = quote(
            QuoteRequest(
                lines=(line(10_000),),
                shipping_paisa=500 * RS,
                cod_surcharge_paisa=200 * RS,
                tax_mode=TaxMode.INCLUSIVE,
            )
        )
        assert q.total_paisa == (10_000 + 500 + 200) * RS

    def test_gift_wrap(self) -> None:
        q = quote(QuoteRequest(lines=(line(5_000),), gift_wrap_paisa=350 * RS))
        assert q.total_paisa == 5_350 * RS


class TestStoredValue:
    def test_gift_card_reduces_total(self) -> None:
        q = quote(
            QuoteRequest(lines=(line(10_000),), gift_card_balance_paisa=3_000 * RS)
        )
        assert q.gift_card_applied_paisa == 3_000 * RS
        assert q.total_paisa == 7_000 * RS

    def test_gift_card_never_exceeds_the_bill(self) -> None:
        q = quote(
            QuoteRequest(lines=(line(1_000),), gift_card_balance_paisa=50_000 * RS)
        )
        assert q.gift_card_applied_paisa == 1_000 * RS
        assert q.total_paisa == 0

    def test_loyalty_points_redeemed(self) -> None:
        q = quote(
            QuoteRequest(
                lines=(line(10_000),),
                loyalty_points_available=500,
                loyalty_points_to_redeem=500,
            )
        )
        assert q.loyalty_points_redeemed == 500
        assert q.loyalty_applied_paisa == 500 * RS
        assert q.total_paisa == 9_500 * RS

    def test_cannot_redeem_more_points_than_held(self) -> None:
        q = quote(
            QuoteRequest(
                lines=(line(10_000),),
                loyalty_points_available=100,
                loyalty_points_to_redeem=900,
            )
        )
        assert q.loyalty_points_redeemed == 100

    def test_surplus_points_are_not_wasted(self) -> None:
        """Only the points actually needed are spent."""
        q = quote(
            QuoteRequest(
                lines=(line(50),),  # Rs 50 bill
                loyalty_points_available=500,
                loyalty_points_to_redeem=500,
            )
        )
        assert q.loyalty_points_redeemed == 50
        assert q.total_paisa == 0

    def test_stored_value_order_gift_card_first(self) -> None:
        q = quote(
            QuoteRequest(
                lines=(line(10_000),),
                gift_card_balance_paisa=6_000 * RS,
                loyalty_points_available=10_000,
                loyalty_points_to_redeem=10_000,
                store_credit_paisa=10_000 * RS,
            )
        )
        assert q.gift_card_applied_paisa == 6_000 * RS
        assert q.loyalty_applied_paisa == 4_000 * RS
        assert q.store_credit_applied_paisa == 0
        assert q.total_paisa == 0

    def test_total_never_negative(self) -> None:
        q = quote(
            QuoteRequest(
                lines=(line(100),),
                gift_card_balance_paisa=99_999 * RS,
                store_credit_paisa=99_999 * RS,
            )
        )
        assert q.total_paisa == 0


class TestLoyaltyEarning:
    def test_points_earned_on_net_spend(self) -> None:
        q = quote(
            QuoteRequest(
                lines=(line(11_800),), tax_mode=TaxMode.INCLUSIVE, tax_rate_bp=GST
            )
        )
        # Net is Rs 10,000, earning 1 point per Rs 100.
        assert q.loyalty_points_earned == 100

    def test_no_points_earned_on_gift_card_spend(self) -> None:
        q = quote(
            QuoteRequest(
                lines=(line(11_800),),
                tax_rate_bp=GST,
                gift_card_balance_paisa=11_800 * RS,
            )
        )
        assert q.loyalty_points_earned == 0


class TestDeterminism:
    def test_same_input_gives_same_output(self) -> None:
        req = QuoteRequest(
            lines=(line(7_999, qty=2), line(1_499)),
            coupon=CouponInput("SAVE15", DiscountKind.PERCENTAGE, value_bp=1500),
            shipping_paisa=450 * RS,
            cod_surcharge_paisa=200 * RS,
            tax_rate_bp=GST,
        )
        a, b = quote(req), quote(req)
        assert a.total_paisa == b.total_paisa
        assert a.tax_paisa == b.tax_paisa
        assert [ln.subtotal_paisa for ln in a.lines] == [
            ln.subtotal_paisa for ln in b.lines
        ]

    def test_realistic_basket_balances(self) -> None:
        """A full basket: personalization, sale, coupon, shipping, COD, tax."""
        engraving = PersonalizationChoice(
            key="engraving", label="Engraving", value="For Ayesha",
            surcharge_paisa=500 * RS, surcharge_per_char_paisa=25 * RS,
        )
        q = quote(
            QuoteRequest(
                lines=(
                    line(24_999, personalizations=(engraving,)),
                    line(8_499, qty=4, flash_sale_bp=1500),
                    line(3_299, qty=2),
                ),
                coupon=CouponInput("WOOD10", DiscountKind.PERCENTAGE, value_bp=1000),
                shipping_paisa=450 * RS,
                cod_surcharge_paisa=200 * RS,
                tax_mode=TaxMode.INCLUSIVE,
                tax_rate_bp=GST,
            )
        )
        # Lines reconstruct the subtotal.
        assert sum(ln.subtotal_paisa for ln in q.lines) == q.subtotal_paisa
        # Coupon shares reconstruct the coupon.
        line_discounts = sum(ln.line_discount_paisa for ln in q.lines)
        allocated = sum(ln.allocated_discount_paisa for ln in q.lines)
        assert line_discounts + allocated == q.discount_paisa
        # Total is subtotal plus the untaxed extras, in inclusive mode.
        assert q.total_paisa == q.subtotal_paisa + 450 * RS + 200 * RS
        assert q.total_paisa > 0
