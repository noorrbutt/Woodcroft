"""Shared enumerations stored as native PostgreSQL enum types.

Rule of thumb used throughout Woodcroft: a native enum when the set is small,
stable and code branches on it (order status, role, province); a lookup table
when the set is data the admin edits (categories, tags, couriers' rate cards).
"""

from __future__ import annotations

from enum import StrEnum


class PakistanProvince(StrEnum):
    PUNJAB = "punjab"
    SINDH = "sindh"
    KHYBER_PAKHTUNKHWA = "khyber_pakhtunkhwa"
    BALOCHISTAN = "balochistan"
    GILGIT_BALTISTAN = "gilgit_baltistan"
    AZAD_JAMMU_KASHMIR = "azad_jammu_kashmir"
    ISLAMABAD = "islamabad"

    @property
    def label(self) -> str:
        return {
            "punjab": "Punjab",
            "sindh": "Sindh",
            "khyber_pakhtunkhwa": "Khyber Pakhtunkhwa",
            "balochistan": "Balochistan",
            "gilgit_baltistan": "Gilgit-Baltistan",
            "azad_jammu_kashmir": "Azad Jammu & Kashmir",
            "islamabad": "Islamabad Capital Territory",
        }[self.value]


class AddressType(StrEnum):
    SHIPPING = "shipping"
    BILLING = "billing"
    BOTH = "both"


class Courier(StrEnum):
    TCS = "tcs"
    LEOPARDS = "leopards"
    MP = "mp"
    TRAX = "trax"
    POSTEX = "postex"
    BLUEEX = "blueex"

    @property
    def label(self) -> str:
        return {
            "tcs": "TCS",
            "leopards": "Leopards Courier",
            "mp": "M&P",
            "trax": "TRAX",
            "postex": "PostEx",
            "blueex": "BlueEx",
        }[self.value]

    @property
    def tracking_url(self) -> str:
        return {
            "tcs": "https://www.tcsexpress.com/track/",
            "leopards": "https://leopardscourier.com/tracking",
            "mp": "https://mpexpress.com.pk/tracking",
            "trax": "https://trax.pk/tracking",
            "postex": "https://postex.pk/tracking",
            "blueex": "https://blue-ex.com/tracking",
        }[self.value]


class TaxMode(StrEnum):
    INCLUSIVE = "inclusive"
    EXCLUSIVE = "exclusive"


class ProductStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    ARCHIVED = "archived"


class StockPolicy(StrEnum):
    """What to do when a variant's available stock reaches zero."""

    DENY = "deny"          # refuse to sell
    CONTINUE = "continue"  # allow backorder
    PREORDER = "preorder"  # sell against a known future date


class WoodSpecies(StrEnum):
    """Species actually used by Pakistani furniture makers.

    Sheesham (Indian rosewood) and mango are the authentic local staples;
    deodar is the Himalayan cedar used for traditional joinery.
    """

    SHEESHAM = "sheesham"
    WALNUT = "walnut"
    TEAK = "teak"
    MANGO = "mango"
    ACACIA = "acacia"
    DEODAR = "deodar"
    OAK = "oak"
    PINE = "pine"

    @property
    def label(self) -> str:
        return {
            "sheesham": "Sheesham (Indian Rosewood)",
            "walnut": "Walnut",
            "teak": "Teak",
            "mango": "Mango Wood",
            "acacia": "Acacia",
            "deodar": "Deodar (Himalayan Cedar)",
            "oak": "Oak",
            "pine": "Pine",
        }[self.value]

    @property
    def grain_palette(self) -> tuple[str, str, str]:
        """(base, grain, highlight) hex used by the procedural plate generator."""
        return {
            "sheesham": ("#5A3A24", "#3E2415", "#7C5436"),
            "walnut": ("#5C4433", "#3B2A1E", "#806049"),
            "teak": ("#9A6B3F", "#6E4626", "#BE8B58"),
            "mango": ("#B9925E", "#8A6A3C", "#D8BC8A"),
            "acacia": ("#8A5A32", "#5E3A1E", "#B07F4E"),
            "deodar": ("#C0A176", "#93744C", "#DCC49B"),
            "oak": ("#B99A6B", "#8C7148", "#D6BC93"),
            "pine": ("#D9BE92", "#B2946A", "#EFDCBA"),
        }[self.value]


class PersonalizationInputType(StrEnum):
    TEXT = "text"                # engraving line
    MONOGRAM = "monogram"        # 2-3 initials
    SELECT = "select"            # font, placement
    DIMENSIONS = "dimensions"    # custom length/width/height


class ReservationStatus(StrEnum):
    ACTIVE = "active"
    CONSUMED = "consumed"   # became an order line
    RELEASED = "released"   # checkout abandoned
    EXPIRED = "expired"     # swept by the worker


class MovementReason(StrEnum):
    SALE = "sale"
    RESTOCK = "restock"
    RETURN = "return"
    CANCELLATION = "cancellation"
    DAMAGE = "damage"
    CORRECTION = "correction"
    INITIAL = "initial"


class OrderStatus(StrEnum):
    """Lifecycle of an order.

    Forward transitions are enforced by the order service; the terminal states
    are DELIVERED, CANCELLED and REFUNDED.
    """

    PENDING = "pending"                # placed, awaiting confirmation
    CONFIRMED = "confirmed"            # COD confirmed / payment captured
    PROCESSING = "processing"          # being made or picked
    SHIPPED = "shipped"
    OUT_FOR_DELIVERY = "out_for_delivery"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"
    REFUNDED = "refunded"

    @property
    def is_terminal(self) -> bool:
        return self in {OrderStatus.DELIVERED, OrderStatus.CANCELLED, OrderStatus.REFUNDED}

    @property
    def label(self) -> str:
        return self.value.replace("_", " ").title()


class PaymentStatus(StrEnum):
    PENDING = "pending"
    AUTHORIZED = "authorized"
    PAID = "paid"
    FAILED = "failed"
    REFUNDED = "refunded"
    PARTIALLY_REFUNDED = "partially_refunded"
    CANCELLED = "cancelled"


class PaymentMethodCode(StrEnum):
    COD = "cod"
    JAZZCASH = "jazzcash"
    EASYPAISA = "easypaisa"


class ShipmentStatus(StrEnum):
    PENDING = "pending"
    DISPATCHED = "dispatched"
    IN_TRANSIT = "in_transit"
    OUT_FOR_DELIVERY = "out_for_delivery"
    DELIVERED = "delivered"
    FAILED = "failed"
    RETURNED = "returned"


class ReturnStatus(StrEnum):
    REQUESTED = "requested"
    APPROVED = "approved"
    REJECTED = "rejected"
    IN_TRANSIT = "in_transit"
    RECEIVED = "received"
    REFUNDED = "refunded"
    CANCELLED = "cancelled"


class ReturnReason(StrEnum):
    DAMAGED = "damaged"
    DEFECTIVE = "defective"
    WRONG_ITEM = "wrong_item"
    NOT_AS_DESCRIBED = "not_as_described"
    CHANGED_MIND = "changed_mind"
    SIZE_ISSUE = "size_issue"
    OTHER = "other"
