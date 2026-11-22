"""Density and freight class rules.

Plain-input module: every function takes simple numbers and returns simple values, with no
database and no web request, so each rule can be tested on its own. This is a simplified,
density-only suggestion based on NMFTA's 13-tier density scale; it is NOT an official NMFC
implementation and contains no NMFC item data.

This is the one replaceable home for the class table. Change the table and CLASS_TABLE_VERSION
together (see docs/slices/slice_01_quote_request.md and docs/slices/slice_02_notes.md).
"""

from decimal import Decimal

# Identifies the table below (NMFTA Docket 2025-1, effective 2025-07-19). It must change whenever
# any boundary or class in the table changes. Slice 2 quotes will record it.
CLASS_TABLE_VERSION = "NMFTA-2025-1"

CUBIC_INCHES_PER_CUBIC_FOOT = 1728

# (lowest density in the tier, inclusive; class), listed from the densest tier down.
# A density exactly on a boundary belongs to the upper tier (35 exactly is class 55).
DENSITY_CLASS_TABLE = (
    (Decimal("50"), Decimal("50")),
    (Decimal("35"), Decimal("55")),
    (Decimal("30"), Decimal("60")),
    (Decimal("22.5"), Decimal("65")),
    (Decimal("15"), Decimal("70")),
    (Decimal("12"), Decimal("85")),
    (Decimal("10"), Decimal("92.5")),
    (Decimal("8"), Decimal("100")),
    (Decimal("6"), Decimal("125")),
    (Decimal("4"), Decimal("175")),
    (Decimal("2"), Decimal("250")),
    (Decimal("1"), Decimal("300")),
)

# Class for a density below the lowest tier boundary (less than 1 lb per cubic foot).
LOWEST_DENSITY_CLASS = Decimal("400")

# The 18 standard NMFC classes. Used ONLY to validate a class supplied by a shipper, never to
# suggest one (classes such as 77.5, 110, 150, 200 and 500 are not on the density scale above).
# Kept as strings because that is how a class is stored and returned.
STANDARD_NMFC_CLASSES = (
    "50",
    "55",
    "60",
    "65",
    "70",
    "77.5",
    "85",
    "92.5",
    "100",
    "110",
    "125",
    "150",
    "175",
    "200",
    "250",
    "300",
    "400",
    "500",
)


def calculate_density(weight_lb: int, length_in: int, width_in: int, height_in: int) -> Decimal:
    """Return density in pounds per cubic foot for ONE handling unit.

    density = (weight x 1728) / (length x width x height)

    One division only, on whole numbers: no separate cubic-foot volume is computed first and
    nothing is rounded. The result is not rounded here either; round it only for display.
    (Decimal division is exact when the true value terminates, as for 9.6 and 34.984375. For a
    repeating value such as 4500/91 it keeps 28 significant digits, far finer than the gap
    between any such value and a table boundary.)
    """
    volume_cubic_inches = length_in * width_in * height_in
    if weight_lb <= 0 or volume_cubic_inches <= 0:
        raise ValueError("Weight and dimensions must be greater than zero.")
    return Decimal(weight_lb * CUBIC_INCHES_PER_CUBIC_FOOT) / Decimal(volume_cubic_inches)


def suggest_class(density: Decimal) -> Decimal:
    """Return the suggested freight class for an (unrounded) density in lb per cubic foot."""
    for lowest_density, freight_class in DENSITY_CLASS_TABLE:
        if density >= lowest_density:
            return freight_class
    return LOWEST_DENSITY_CLASS


def format_class(freight_class: Decimal) -> str:
    """Return a class as plain text: Decimal('55') -> '55', Decimal('92.5') -> '92.5'."""
    return format(freight_class.normalize(), "f")
