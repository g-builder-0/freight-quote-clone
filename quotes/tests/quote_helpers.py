"""Shared builders for Slice 2 tests that need saved requests."""

from datetime import UTC, date, datetime

from quotes.models import HandlingUnit, QuoteRequest

# Wednesday 2026-11-25 at 14:10 UTC (08:10 in Chicago) is "now" in these tests.
NOW = datetime(2026, 11, 25, 14, 10, tzinfo=UTC)


def make_request(units=None, **overrides) -> QuoteRequest:
    """A saved request. Default: Allen dock to Dallas dock, pickup Monday 30 Nov 2026."""
    fields = dict(
        origin_street="1 A St", origin_city="Allen", origin_state="TX",
        origin_postal_code="75002", origin_location_type="business_dock",
        destination_street="2 B St", destination_city="Dallas", destination_state="TX",
        destination_postal_code="75201", destination_location_type="business_dock",
        pickup_date=date(2026, 11, 30),
    )  # fmt: skip
    fields.update(overrides)
    request = QuoteRequest.objects.create(**fields)
    for unit in units if units is not None else [unit_fields()]:
        HandlingUnit.objects.create(quote_request=request, **unit)
    return request


def unit_fields(**overrides) -> dict:
    fields = dict(
        unit_type="pallet", quantity=1, length_in=48, width_in=40, height_in=40,
        weight_lb=1000, commodity_description="Widgets", freight_class="100",
    )  # fmt: skip
    fields.update(overrides)
    return fields


def example_1_request() -> QuoteRequest:
    """Graham's worked example 1: Allen to Atlanta (residential), a 1,200 lb class 55 pallet and
    a 400 lb class 125 crate, liftgate requested, pickup Monday 2026-11-30."""
    return make_request(
        units=[
            unit_fields(weight_lb=1200, freight_class="55"),
            unit_fields(unit_type="crate", weight_lb=400, freight_class="125"),
        ],
        destination_city="Atlanta", destination_state="GA",
        destination_postal_code="30301", destination_location_type="residential",
        liftgate_requested=True,
    )  # fmt: skip
