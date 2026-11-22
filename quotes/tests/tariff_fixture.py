"""The approved Slice 2 tariff (RATES-2026-1) as plain data, for tests.

Copied from the approved table in docs/slices/slice_02_quote_engine.md ("Carriers and tariffs").
All numbers are illustrative and invented. Rates are dollars per cwt at class 100.
"""

from decimal import Decimal

from quotes.pricing import (
    APPOINTMENT,
    LIFTGATE,
    LIMITED_ACCESS,
    RESIDENTIAL,
    CarrierTariffData,
    WeightBreak,
)

# Weight breaks: under 500, 500-999, 1,000-1,999, 2,000-4,999, 5,000 and up.
BREAKS = ((0, 499), (500, 999), (1000, 1999), (2000, 4999), (5000, None))


def _tariff(code, name, rates, minimum, fuel, residential, limited, liftgate, appointment, adj):
    return CarrierTariffData(
        code=code,
        name=name,
        minimum_charge=Decimal(minimum),
        fuel_percent=Decimal(fuel),
        transit_adjustment_days=adj,
        weight_breaks=tuple(
            WeightBreak(from_lb, to_lb, Decimal(rate))
            for (from_lb, to_lb), rate in zip(BREAKS, rates, strict=True)
        ),
        fees={
            RESIDENTIAL: Decimal(residential),
            LIMITED_ACCESS: Decimal(limited),
            LIFTGATE: Decimal(liftgate),
            APPOINTMENT: Decimal(appointment),
        },
    )


CHEAP = _tariff(
    "cheap", "Cheap and slow", ("42", "35", "30", "25", "20"), "75", "0.28",
    "85", "95", "65", "40", 1,
)  # fmt: skip
MID = _tariff(
    "mid", "Mid", ("48", "40", "34", "28", "23"), "90", "0.32", "100", "120", "85", "50", 0
)
FAST = _tariff(
    "fast", "Fast and pricey", ("56", "46", "39", "32", "26"), "110", "0.35",
    "120", "150", "110", "60", -1,
)  # fmt: skip

TARIFFS = {"cheap": CHEAP, "mid": MID, "fast": FAST}
