"""Colour helpers shared by the plate generator and the placeholder renderer.

Both build their palettes the same way - parse a hex string, then interpolate
between two colours - so the arithmetic lives here once rather than drifting
between two copies.
"""

from __future__ import annotations

RGB = tuple[int, int, int]


def hex_to_rgb(value: str) -> RGB:
    """``"#8B5E3C"`` or ``"8B5E3C"`` to an (r, g, b) triple."""
    value = value.lstrip("#")
    return (int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16))


def mix(a: RGB, b: RGB, t: float) -> RGB:
    """Linear blend from ``a`` to ``b``. ``t`` is clamped to 0..1."""
    t = max(0.0, min(1.0, t))
    return (
        round(a[0] + (b[0] - a[0]) * t),
        round(a[1] + (b[1] - a[1]) * t),
        round(a[2] + (b[2] - a[2]) * t),
    )
