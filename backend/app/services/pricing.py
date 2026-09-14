"""The pricing engine. The only place in Woodcroft that computes money.

Cart display, checkout, order creation and the seeder all call ``quote()``.
That is deliberate: if any of them did its own arithmetic, a shopper could be
shown one total and charged another, and the admin's revenue reports would
disagree with the invoices.

The pipeline, in order
---------------------
1. base variant price (falls back to the product price)
2. personalization surcharges (flat, plus per-character for engraving)
3. line discounts: flash sale, then automatic rules, best one wins
4. coupon, applied at order level then allocated back across lines
5. gift card, loyalty points and store credit, applied to the payable amount
6. shipping
7. COD surcharge
8. tax, either extracted from inclusive prices or added to exclusive ones

Rounding
--------
Every amount is an integer number of paisa. Rounding is half-up and happens
once per line, never on a running total. Order level discounts are split across
lines with the largest remainder method so the parts always add back to exactly
the whole, with no stray paisa.

Tax modes
---------
Inclusive: the catalogue price already contains GST. The tax shown on the
invoice is extracted from it, so the customer pays the advertised number.
Exclusive: the catalogue price is pre tax and GST is added at checkout.

Both modes charge the same customer the same money for the same basket. Only
the presentation of the breakdown differs. ``tests/test_pricing.py`` asserts
this directly, because a difference here would silently change prices for every
customer the moment an admin flips the setting.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal

from app.core.money import Paisa, apply_bp, clamp_non_negative, tax_from_inclusive
from app.models.enums import DiscountKind, TaxMode

#: Loyalty: how many points one rupee of spend earns, and what a point is worth
#: when redeemed. Both are overridable from store settings.
DEFAULT_POINTS_PER_RUPEE = Decimal("0.01")
DEFAULT_POINT_VALUE_PAISA = 100  # 1 point == Rs 1


# ── Inputs ───────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class PersonalizationChoice:
    """One configured customisation on a line."""

    key: str
    label: str
    value: str
    surcharge_paisa: Paisa = 0
    surcharge_per_char_paisa: Paisa = 0

    def total_surcharge(self) -> Paisa:
        chars = len(self.value.strip())
        return self.surcharge_paisa + self.surcharge_per_char_paisa * chars


@dataclass(frozen=True)
class LineInput:
    variant_id: uuid.UUID
    quantity: int
    unit_price_paisa: Paisa
    #: Per-category or per-product override. Falls back to the store rate.
    tax_rate_bp: int | None = None
    personalizations: tuple[PersonalizationChoice, ...] = ()
    #: Percentage off this line from a flash sale, in basis points.
    flash_sale_bp: int = 0
    #: Percentage off from the best matching automatic rule.
    auto_discount_bp: int = 0
    #: Flat amount off this line from an automatic rule.
    auto_discount_paisa: Paisa = 0
    product_id: uuid.UUID | None = None
    is_gift_card: bool = False


@dataclass(frozen=True)
class CouponInput:
    code: str
    kind: DiscountKind
    value_bp: int | None = None
    value_paisa: Paisa | None = None
    max_discount_paisa: Paisa | None = None
    min_order_paisa: Paisa = 0


@dataclass(frozen=True)
class QuoteRequest:
    lines: tuple[LineInput, ...]
    tax_mode: TaxMode = TaxMode.INCLUSIVE
    tax_rate_bp: int = 1800
    coupon: CouponInput | None = None
    shipping_paisa: Paisa = 0
    #: Set when a rate or coupon makes delivery free.
    free_shipping: bool = False
    cod_surcharge_paisa: Paisa = 0
    gift_wrap_paisa: Paisa = 0
    gift_card_balance_paisa: Paisa = 0
    loyalty_points_available: int = 0
    loyalty_points_to_redeem: int = 0
    point_value_paisa: int = DEFAULT_POINT_VALUE_PAISA
    store_credit_paisa: Paisa = 0
    #: Shipping is normally taxed at the same rate as goods.
    tax_shipping: bool = True
    now: datetime | None = None


# ── Outputs ──────────────────────────────────────────────────────────────────
@dataclass
class LineQuote:
    variant_id: uuid.UUID
    quantity: int
    #: Catalogue price for one unit, before anything is applied.
    unit_price_paisa: Paisa
    personalization_surcharge_paisa: Paisa
    #: (unit + surcharge) * quantity, before discounts.
    gross_paisa: Paisa
    #: Line level discounts (flash sale, automatic rules).
    line_discount_paisa: Paisa
    #: This line's share of the order level coupon.
    allocated_discount_paisa: Paisa
    #: What this line contributes to the order total.
    subtotal_paisa: Paisa
    tax_paisa: Paisa
    tax_rate_bp: int
    #: Pre tax portion of subtotal. Equals subtotal in exclusive mode.
    net_paisa: Paisa

    @property
    def total_discount_paisa(self) -> Paisa:
        return self.line_discount_paisa + self.allocated_discount_paisa


@dataclass
class Quote:
    lines: list[LineQuote] = field(default_factory=list)
    subtotal_paisa: Paisa = 0
    discount_paisa: Paisa = 0
    shipping_paisa: Paisa = 0
    cod_surcharge_paisa: Paisa = 0
    gift_wrap_paisa: Paisa = 0
    tax_paisa: Paisa = 0
    gift_card_applied_paisa: Paisa = 0
    loyalty_applied_paisa: Paisa = 0
    store_credit_applied_paisa: Paisa = 0
    total_paisa: Paisa = 0
    loyalty_points_redeemed: int = 0
    loyalty_points_earned: int = 0
    tax_mode: TaxMode = TaxMode.INCLUSIVE
    tax_rate_bp: int = 1800
    coupon_code: str | None = None
    #: Populated when a coupon was supplied but could not be applied.
    coupon_error: str | None = None

    @property
    def item_count(self) -> int:
        return sum(line.quantity for line in self.lines)

    @property
    def net_paisa(self) -> Paisa:
        """Goods total excluding tax."""
        return sum(line.net_paisa for line in self.lines)


# ── Allocation ───────────────────────────────────────────────────────────────
def allocate_proportionally(total: Paisa, weights: list[Paisa]) -> list[Paisa]:
    """Split ``total`` across ``weights`` so the parts sum to exactly ``total``.

    Uses the largest remainder method. Naive per line rounding would leave the
    parts adding up to a paisa more or less than the whole, which then shows up
    as an invoice that does not balance.
    """
    weight_sum = sum(weights)
    if total <= 0 or weight_sum <= 0:
        return [0] * len(weights)

    exact = [Decimal(total) * Decimal(w) / Decimal(weight_sum) for w in weights]
    floors = [int(e) for e in exact]
    remainder = total - sum(floors)

    # Hand the leftover paisa to the lines with the largest fractional parts.
    order = sorted(
        range(len(weights)),
        key=lambda i: (exact[i] - floors[i], weights[i]),
        reverse=True,
    )
    for i in order[:remainder]:
        floors[i] += 1
    return floors


# ── Engine ───────────────────────────────────────────────────────────────────
def _coupon_discount(coupon: CouponInput, base: Paisa) -> Paisa:
    """Order level discount from a coupon, before allocation."""
    if base < coupon.min_order_paisa:
        return 0

    if coupon.kind is DiscountKind.PERCENTAGE and coupon.value_bp:
        amount = apply_bp(base, coupon.value_bp)
        if coupon.max_discount_paisa is not None:
            amount = min(amount, coupon.max_discount_paisa)
    elif coupon.kind is DiscountKind.FIXED_AMOUNT and coupon.value_paisa:
        amount = coupon.value_paisa
    else:
        # Free shipping coupons are handled by the caller setting free_shipping.
        amount = 0

    # A coupon can never make the basket negative.
    return min(amount, base)


def quote(request: QuoteRequest) -> Quote:
    """Price a basket. Pure function: same input always gives same output."""
    result = Quote(tax_mode=request.tax_mode, tax_rate_bp=request.tax_rate_bp)

    # ── 1 and 2: base price plus personalization, then 3: line discounts ─────
    priced: list[LineQuote] = []
    for line in request.lines:
        surcharge = sum(p.total_surcharge() for p in line.personalizations)
        unit_with_extras = line.unit_price_paisa + surcharge
        gross = unit_with_extras * line.quantity

        # Flash sale and automatic rules do not stack. The customer gets
        # whichever is worth more, which is both fairer and simpler to explain.
        flash = apply_bp(gross, line.flash_sale_bp) if line.flash_sale_bp else 0
        auto = apply_bp(gross, line.auto_discount_bp) if line.auto_discount_bp else 0
        auto += line.auto_discount_paisa
        line_discount = min(max(flash, auto), gross)

        priced.append(
            LineQuote(
                variant_id=line.variant_id,
                quantity=line.quantity,
                unit_price_paisa=line.unit_price_paisa,
                personalization_surcharge_paisa=surcharge,
                gross_paisa=gross,
                line_discount_paisa=line_discount,
                allocated_discount_paisa=0,
                subtotal_paisa=gross - line_discount,
                tax_paisa=0,
                tax_rate_bp=line.tax_rate_bp
                if line.tax_rate_bp is not None
                else request.tax_rate_bp,
                net_paisa=0,
            )
        )

    goods_after_line_discounts = sum(line.subtotal_paisa for line in priced)

    # ── 4: coupon, applied to the order then pushed back down to lines ───────
    coupon_discount = 0
    if request.coupon is not None:
        coupon_discount = _coupon_discount(request.coupon, goods_after_line_discounts)
        result.coupon_code = request.coupon.code
        if coupon_discount == 0 and goods_after_line_discounts < request.coupon.min_order_paisa:
            result.coupon_error = "minimum_order_not_met"

    if coupon_discount:
        shares = allocate_proportionally(
            coupon_discount, [line.subtotal_paisa for line in priced]
        )
        for line, share in zip(priced, shares, strict=True):
            line.allocated_discount_paisa = share
            line.subtotal_paisa -= share

    # ── 8: tax, per line so mixed rates work ─────────────────────────────────
    for line in priced:
        if request.tax_mode is TaxMode.INCLUSIVE:
            # The price already contains tax. Pull it out by subtraction so
            # net + tax lands exactly back on subtotal.
            line.tax_paisa = tax_from_inclusive(line.subtotal_paisa, line.tax_rate_bp)
            line.net_paisa = line.subtotal_paisa - line.tax_paisa
        else:
            line.net_paisa = line.subtotal_paisa
            line.tax_paisa = apply_bp(line.subtotal_paisa, line.tax_rate_bp)

    result.lines = priced
    # net_goods is the goods total after every discount; it drives the payable.
    # subtotal_paisa is the goods total BEFORE any discount, so an invoice reads
    # Subtotal - Discount + Delivery = Total and actually adds up. line.subtotal
    # has already had both the line discount and the coupon share subtracted, so
    # add them back to recover the pre-discount figure.
    net_goods = sum(line.subtotal_paisa for line in priced)
    line_discount_total = sum(line.line_discount_paisa for line in priced)
    result.discount_paisa = line_discount_total + coupon_discount
    result.subtotal_paisa = net_goods + result.discount_paisa

    # ── 6 and 7: shipping, gift wrap, COD ────────────────────────────────────
    shipping = 0 if request.free_shipping else request.shipping_paisa
    result.shipping_paisa = shipping
    result.gift_wrap_paisa = request.gift_wrap_paisa
    result.cod_surcharge_paisa = request.cod_surcharge_paisa

    extras = shipping + request.gift_wrap_paisa + request.cod_surcharge_paisa
    extras_tax = 0
    if request.tax_shipping and extras:
        if request.tax_mode is TaxMode.INCLUSIVE:
            extras_tax = tax_from_inclusive(extras, request.tax_rate_bp)
        else:
            extras_tax = apply_bp(extras, request.tax_rate_bp)

    result.tax_paisa = sum(line.tax_paisa for line in priced) + extras_tax

    # Payable before any stored value is applied. Uses net_goods, not the
    # pre-discount subtotal, so the total stays exactly what the customer owes.
    if request.tax_mode is TaxMode.INCLUSIVE:
        payable = net_goods + extras
    else:
        payable = net_goods + extras + result.tax_paisa

    # ── 5: stored value, in the order that helps the customer most ───────────
    # Gift card first, then loyalty, then store credit. Loyalty points are the
    # only one the customer can accidentally waste, so they are spent after the
    # gift card has already reduced the bill.
    gift_card = min(request.gift_card_balance_paisa, payable)
    payable -= gift_card

    points = min(request.loyalty_points_to_redeem, request.loyalty_points_available)
    loyalty_value = points * request.point_value_paisa
    if loyalty_value > payable:
        # Only redeem the points actually needed, rounding down so the customer
        # never spends a point that buys nothing.
        points = payable // request.point_value_paisa if request.point_value_paisa else 0
        loyalty_value = points * request.point_value_paisa
    payable -= loyalty_value

    store_credit = min(request.store_credit_paisa, payable)
    payable -= store_credit

    result.gift_card_applied_paisa = gift_card
    result.loyalty_applied_paisa = loyalty_value
    result.loyalty_points_redeemed = points
    result.store_credit_applied_paisa = store_credit
    result.total_paisa = clamp_non_negative(payable)

    # Points are earned on the goods actually paid for, excluding tax, shipping
    # and anything settled with stored value.
    earn_base = clamp_non_negative(result.net_paisa - gift_card - loyalty_value)
    result.loyalty_points_earned = int(
        (Decimal(earn_base) / 100 * DEFAULT_POINTS_PER_RUPEE).quantize(
            Decimal("1"), rounding=ROUND_HALF_UP
        )
    )

    return result
