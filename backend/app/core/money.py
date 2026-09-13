"""Money handling. Every amount in Woodcroft is an integer number of paisa.

1 PKR = 100 paisa. Amounts are stored in BIGINT columns and passed around as
plain ``int``. Floats are never used for money anywhere in this codebase - the
only conversion to a decimal representation happens at display time.

Rounding rule: half-up on the smallest unit (paisa), applied once per line and
then summed. Python's built-in ``round`` is banker's rounding, which would make
tax totals drift, so it is deliberately not used here.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

Paisa = int

PAISA_PER_RUPEE = 100
#: Basis points denominator. 10_000 bp == 100%.
BP_DENOMINATOR = 10_000


def rupees_to_paisa(rupees: float | int | str | Decimal) -> Paisa:
    """Convert a rupee amount to paisa, rounding half-up."""
    value = Decimal(str(rupees)) * PAISA_PER_RUPEE
    return int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def paisa_to_rupees(paisa: Paisa) -> Decimal:
    """Exact decimal rupee value. For display and PDF rendering only."""
    return (Decimal(paisa) / PAISA_PER_RUPEE).quantize(Decimal("0.01"))


def apply_bp(amount: Paisa, basis_points: int) -> Paisa:
    """Apply a basis-point rate to an amount, rounding half-up.

    >>> apply_bp(1_000_000, 1800)   # 18% of Rs 10,000
    180000
    """
    value = Decimal(amount) * Decimal(basis_points) / Decimal(BP_DENOMINATOR)
    return int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def tax_from_inclusive(gross: Paisa, basis_points: int) -> Paisa:
    """Extract the tax component from a tax-inclusive amount.

    net = gross / (1 + rate);  tax = gross - net

    Deriving tax by subtraction rather than computing it directly guarantees
    ``net + tax == gross`` exactly, with no rounding residue.

    >>> tax_from_inclusive(1_180_000, 1800)   # Rs 11,800 incl. 18%
    180000
    """
    divisor = Decimal(BP_DENOMINATOR + basis_points) / Decimal(BP_DENOMINATOR)
    net = (Decimal(gross) / divisor).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return gross - int(net)


def net_from_inclusive(gross: Paisa, basis_points: int) -> Paisa:
    """The pre-tax portion of a tax-inclusive amount."""
    return gross - tax_from_inclusive(gross, basis_points)


def percentage_of(amount: Paisa, percent: Decimal | float | int) -> Paisa:
    """Percentage discount helper, rounding half-up."""
    value = Decimal(amount) * Decimal(str(percent)) / Decimal(100)
    return int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def format_pkr(paisa: Paisa, *, with_decimals: bool = False) -> str:
    """Render paisa as a display string.

    Deliberately does NOT use ``Intl``-style currency formatting or locale
    currency symbols: the PKR symbol renders inconsistently as 'PKR', 'Rs' or
    '₨' depending on the ICU version and platform. The prefix is hardcoded so
    backend PDFs and the frontend always agree.

    >>> format_pkr(2_499_900)
    'Rs 24,999'
    >>> format_pkr(2_499_950, with_decimals=True)
    'Rs 24,999.50'
    """
    negative = paisa < 0
    amount = abs(paisa)

    if with_decimals:
        whole, frac = divmod(amount, PAISA_PER_RUPEE)
        body = f"{whole:,}.{frac:02d}"
    else:
        # Round to the nearest rupee for the common display case.
        whole = (amount + PAISA_PER_RUPEE // 2) // PAISA_PER_RUPEE
        body = f"{whole:,}"

    return f"{'-' if negative else ''}Rs {body}"


def clamp_non_negative(paisa: Paisa) -> Paisa:
    """Discounts must never push a line or total below zero."""
    return paisa if paisa > 0 else 0
