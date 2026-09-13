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
