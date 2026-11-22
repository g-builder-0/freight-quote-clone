"""Quote pricing rules (Slice 2).

Plain-input module: every function takes numbers, strings, dates and simple tariff data and
returns a result, with no database, no web request and no reading of the clock. Graham's hand
calculated worked examples (docs/slices/slice_02_quote_engine.md) are the test expectations.

All numbers in a tariff are illustrative and invented. Money is Decimal, never float, and each
line item is rounded half up to cents when it is created, so the lines always sum to the total.

Rules (see the spec, "Pricing rules"):
  1. The weight break comes from the total pounds of the whole shipment.
  2. Line-haul, for each class: (class weight / 100) x rate x class multiplier x zone factor.
  3. If the summed line-haul is below the carrier's minimum, it becomes the minimum.
  4. Fuel: ONE line, the fuel percentage x the line-haul from step 3 (fuel is added on top of the
     minimum). Fuel is not applied to accessorials.
  5. Accessorials: automatic location-type fees, then requested fees, each its own line.
  6. Total = line-haul + fuel + accessorials.
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from math import ceil

from .pickup import add_business_days

CENT = Decimal("0.01")

# Fee types in a tariff.
RESIDENTIAL = "residential"
LIMITED_ACCESS = "limited_access"
LIFTGATE = "liftgate"
APPOINTMENT = "appointment"
FEE_TYPES = (RESIDENTIAL, LIMITED_ACCESS, LIFTGATE, APPOINTMENT)

# Location types (same values as quotes.models.LocationType) that trigger an automatic fee.
# A construction site is charged as limited access; a business dock has no automatic fee.
AUTOMATIC_FEE_FOR_LOCATION = {
    "residential": RESIDENTIAL,
    "limited_access": LIMITED_ACCESS,
    "construction_site": LIMITED_ACCESS,
}

PICKUP = "pickup"
DELIVERY = "delivery"

# Line item kinds and sources.
LINE_HAUL = "line_haul"
FUEL = "fuel"
ACCESSORIAL = "accessorial"
SOURCE_AUTO = "auto"
SOURCE_REQUESTED = "requested"


@dataclass(frozen=True)
class WeightBreak:
    """One weight-break tier: `from_lb` up to and including `to_lb` (None means "and up")."""

    from_lb: int
    to_lb: int | None
    rate_per_cwt: Decimal  # dollars per hundredweight at class 100


@dataclass(frozen=True)
class CarrierTariffData:
    code: str
    name: str
    minimum_charge: Decimal
    fuel_percent: Decimal  # a fraction: Decimal("0.32") is 32%
    transit_adjustment_days: int
    weight_breaks: tuple[WeightBreak, ...]
    fees: Mapping[str, Decimal]  # keyed by fee type


@dataclass(frozen=True)
class ShipmentUnit:
    """One handling-unit line: weight is for ONE unit, `quantity` is how many identical units."""

    weight_lb: int
    quantity: int
    freight_class: str  # the class used for pricing, for example "55" or "92.5"


@dataclass(frozen=True)
class LineItem:
    kind: str
    description: str
    source: str  # "" for line-haul and fuel; "auto" or "requested" for accessorials
    reason: str  # for example "residential delivery address"; "" when there is no reason to give
    amount: Decimal


@dataclass(frozen=True)
class QuotePrice:
    carrier_cost: Decimal  # what the carrier charges: the sum of the rounded line items
    price: Decimal  # the customer price: apply_markup(carrier_cost)
    line_items: tuple[LineItem, ...]
    transit_days: int
    estimated_delivery_date: date


def to_cents(amount: Decimal) -> Decimal:
    """Round to whole cents, half up."""
    return amount.quantize(CENT, rounding=ROUND_HALF_UP)


def zone_gap(origin_postal_code: str, destination_postal_code: str) -> int:
    """Absolute difference between the first digits of the two ZIP codes (0 to 9)."""
    return abs(int(origin_postal_code[0]) - int(destination_postal_code[0]))


def zone_factor(gap: int) -> Decimal:
    """Price multiplier for the zone gap: 1.00 + 0.10 x gap."""
    return Decimal("1.00") + Decimal("0.10") * gap


def class_multiplier(freight_class: str) -> Decimal:
    """Class / 100: 0.500 for class 50 up to 5.000 for class 500; "92.5" gives 0.925."""
    return Decimal(freight_class) / Decimal(100)


def pricing_class(supplied_class: str, suggested_class: str) -> str:
    """The class that prices a handling unit: the shipper's class if given, else the suggestion."""
    return supplied_class or suggested_class


def total_weight_lb(units: Iterable[ShipmentUnit]) -> int:
    """Total pounds of the whole shipment: the sum of unit weight x quantity."""
    return sum(unit.weight_lb * unit.quantity for unit in units)


def weight_break_rate(tariff: CarrierTariffData, total_lb: int) -> Decimal:
    """Rate per cwt (class 100) for the tier the shipment's total weight falls in.

    Only the line-haul calculation below calls this: the weight-break lookup lives in one place so
    that the "bill at the next break" rule, which is not built, could be added here later.
    """
    for weight_break in tariff.weight_breaks:
        if total_lb >= weight_break.from_lb and (
            weight_break.to_lb is None or total_lb <= weight_break.to_lb
        ):
            return weight_break.rate_per_cwt
    raise ValueError(f"No weight break for {total_lb} lb in the {tariff.code} tariff.")


def weight_by_class(units: Iterable[ShipmentUnit]) -> dict[str, int]:
    """Pounds per class (unit weight x quantity), lowest class first. Same-class units combine."""
    totals: dict[str, int] = {}
    for unit in units:
        totals[unit.freight_class] = totals.get(unit.freight_class, 0) + (
            unit.weight_lb * unit.quantity
        )
    return dict(sorted(totals.items(), key=lambda item: Decimal(item[0])))


def line_hauls(
    tariff: CarrierTariffData, units: Iterable[ShipmentUnit], factor: Decimal
) -> list[tuple[str, Decimal]]:
    """Line-haul for each class: [(class, amount)], each amount rounded to cents."""
    units = list(units)
    rate = weight_break_rate(tariff, total_weight_lb(units))
    return [
        (
            freight_class,
            to_cents(
                (Decimal(weight) / Decimal(100)) * rate * class_multiplier(freight_class) * factor
            ),
        )
        for freight_class, weight in weight_by_class(units).items()
    ]


def apply_minimum(summed_line_haul: Decimal, minimum_charge: Decimal) -> Decimal:
    """The line-haul after the minimum: the minimum if the sum is below it, else the sum."""
    return max(summed_line_haul, minimum_charge)


def fuel_amount(line_haul_after_minimum: Decimal, fuel_percent: Decimal) -> Decimal:
    """Fuel: the carrier's percentage x the whole line-haul after the minimum, rounded to cents."""
    return to_cents(line_haul_after_minimum * fuel_percent)


def accessorial_fee(tariff: CarrierTariffData, fee_type: str, end: str) -> Decimal:
    """The carrier's amount for a fee type. In Slice 2 the amount is the same at both ends.

    `end` is PICKUP or DELIVERY and is ignored for now; it is here so per-end pricing can be added
    later by changing this function and the tariff data only.
    """
    return tariff.fees[fee_type]


def apply_markup(carrier_cost: Decimal) -> Decimal:
    """Broker markup seam: the customer price from the carrier cost. A 0% markup in Slice 2."""
    return carrier_cost


def transit_days(gap: int, adjustment_days: int) -> int:
    """Business days: 1 + ceil(zone gap / 2) + the carrier's adjustment, never less than 1."""
    return max(1, 1 + ceil(gap / 2) + adjustment_days)


def _auto_fee_lines(tariff: CarrierTariffData, location_type: str, end: str) -> list[LineItem]:
    fee_type = AUTOMATIC_FEE_FOR_LOCATION.get(location_type)
    if fee_type is None:
        return []
    label = "Residential" if fee_type == RESIDENTIAL else "Limited-access"
    if location_type == "construction_site":
        reason = f"construction site {end} address (charged as limited access)"
    else:
        reason = f"{location_type.replace('_', ' ')} {end} address"
    return [
        LineItem(
            ACCESSORIAL,
            f"{label} {end}",
            SOURCE_AUTO,
            reason,
            to_cents(accessorial_fee(tariff, fee_type, end)),
        )
    ]


def price_quote(
    tariff: CarrierTariffData,
    *,
    origin_postal_code: str,
    destination_postal_code: str,
    origin_location_type: str,
    destination_location_type: str,
    pickup_date: date,
    units: Iterable[ShipmentUnit],
    liftgate_requested: bool = False,
    appointment_requested: bool = False,
) -> QuotePrice:
    """Price one shipment with one carrier's tariff, following the order of calculation above."""
    units = list(units)
    gap = zone_gap(origin_postal_code, destination_postal_code)
    factor = zone_factor(gap)

    per_class = line_hauls(tariff, units, factor)
    summed = sum((amount for _, amount in per_class), Decimal("0"))
    line_haul_after_minimum = apply_minimum(summed, tariff.minimum_charge)

    items: list[LineItem] = []
    if line_haul_after_minimum > summed:
        # The minimum applies: the shipper is charged the minimum, shown as one line.
        items.append(
            LineItem(
                LINE_HAUL,
                "Line-haul (minimum applied)",
                "",
                "",
                to_cents(line_haul_after_minimum),
            )
        )
    else:
        items.extend(
            LineItem(LINE_HAUL, f"Line-haul, class {freight_class}", "", "", amount)
            for freight_class, amount in per_class
        )

    fuel_percent_text = format(tariff.fuel_percent * 100, "f").rstrip("0").rstrip(".")
    items.append(
        LineItem(
            FUEL,
            f"Fuel ({fuel_percent_text}%)",
            "",
            "",
            fuel_amount(line_haul_after_minimum, tariff.fuel_percent),
        )
    )

    items.extend(_auto_fee_lines(tariff, origin_location_type, PICKUP))
    items.extend(_auto_fee_lines(tariff, destination_location_type, DELIVERY))
    if liftgate_requested:
        items.append(
            LineItem(
                ACCESSORIAL,
                "Liftgate",
                SOURCE_REQUESTED,
                "requested by shipper",
                to_cents(accessorial_fee(tariff, LIFTGATE, DELIVERY)),
            )
        )
    if appointment_requested:
        items.append(
            LineItem(
                ACCESSORIAL,
                "Appointment",
                SOURCE_REQUESTED,
                "requested by shipper",
                to_cents(accessorial_fee(tariff, APPOINTMENT, DELIVERY)),
            )
        )

    carrier_cost = sum((item.amount for item in items), Decimal("0"))
    days = transit_days(gap, tariff.transit_adjustment_days)
    return QuotePrice(
        carrier_cost=carrier_cost,
        price=apply_markup(carrier_cost),
        line_items=tuple(items),
        transit_days=days,
        estimated_delivery_date=add_business_days(pickup_date, days),
    )
