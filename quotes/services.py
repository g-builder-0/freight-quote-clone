"""Creating quotes for a saved quote request (Slice 2).

One call prices the request with every carrier in the current tariff version and saves one
immutable Quote per carrier, with its line items and the class used for each handling unit, in a
single transaction: either every quote is saved or none is. The caller passes the current time in,
so tests supply the clock and nothing here reads the real one.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date

from django.db import transaction
from django.utils import timezone

from . import pickup
from .freight_class import CLASS_TABLE_VERSION
from .models import (
    QUOTE_VALIDITY,
    Quote,
    QuotedUnit,
    QuoteLineItem,
    QuoteRequest,
    TariffVersion,
)
from .pricing import CarrierTariffData, QuotePrice, ShipmentUnit, price_quote, pricing_class


class NoTariffError(Exception):
    """There is no current tariff version, so nothing can be priced."""


def current_tariff_version() -> TariffVersion:
    """The tariff version prices come from; raises `NoTariffError` when there is none."""
    version = TariffVersion.current()
    if version is None:
        raise NoTariffError("There is no current tariff version.")
    return version


def unit_classes(units: Iterable) -> list[str]:
    """The class that prices each unit: the shipper's class if given, else the suggested class.

    `units` are saved or unsaved `HandlingUnit` objects.
    """
    return [pricing_class(unit.freight_class, unit.suggested_class) for unit in units]


@dataclass(frozen=True)
class CarrierPrice:
    tariff: CarrierTariffData
    price: QuotePrice


def price_with_every_carrier(
    version: TariffVersion,
    units: list,
    classes: list[str],
    *,
    origin_postal_code: str,
    destination_postal_code: str,
    origin_location_type: str,
    destination_location_type: str,
    liftgate_requested: bool = False,
    appointment_requested: bool = False,
    pickup_date: date | None = None,
) -> list[CarrierPrice]:
    """Price one shipment with every carrier of `version`, in carrier order.

    The one place a shipment is priced, used both to create quotes and to preview prices (Slice 5),
    so a preview cannot disagree with a real quote. Without a pickup date no delivery date is given.
    """
    shipment = [
        ShipmentUnit(unit.weight_lb, unit.quantity, freight_class)
        for unit, freight_class in zip(units, classes, strict=True)
    ]
    return [
        CarrierPrice(
            tariff,
            price_quote(
                tariff,
                origin_postal_code=origin_postal_code,
                destination_postal_code=destination_postal_code,
                origin_location_type=origin_location_type,
                destination_location_type=destination_location_type,
                pickup_date=pickup_date,
                units=shipment,
                liftgate_requested=liftgate_requested,
                appointment_requested=appointment_requested,
            ),
        )
        for tariff in (carrier.to_data() for carrier in version.carriers.order_by("id"))
    ]


@transaction.atomic
def create_quotes(quote_request: QuoteRequest, now) -> list[Quote]:
    """Create one quote per carrier for `quote_request`; return them in carrier order.

    Raises `pickup.PickupDateError`, saving nothing, if the pickup date is no longer a business
    day after today (America/Chicago): the pickup date is checked again here because a request can
    be quoted long after it was saved.
    """
    today = timezone.localtime(now).date()
    pickup.validate_pickup_date(quote_request.pickup_date, today)

    version = current_tariff_version()

    units = list(quote_request.handling_units.all())
    classes = unit_classes(units)
    priced = price_with_every_carrier(
        version,
        units,
        classes,
        origin_postal_code=quote_request.origin_postal_code,
        destination_postal_code=quote_request.destination_postal_code,
        origin_location_type=quote_request.origin_location_type,
        destination_location_type=quote_request.destination_location_type,
        liftgate_requested=quote_request.liftgate_requested,
        appointment_requested=quote_request.appointment_requested,
        pickup_date=quote_request.pickup_date,
    )

    quotes = []
    for carrier_price in priced:
        tariff, price = carrier_price.tariff, carrier_price.price
        quote = Quote.objects.create(
            quote_request=quote_request,
            carrier_code=tariff.code,
            carrier_name=tariff.name,
            tariff_version=version,
            rate_table_version=version.label,
            class_table_version=CLASS_TABLE_VERSION,
            total=price.price,
            transit_days=price.transit_days,
            estimated_delivery_date=price.estimated_delivery_date,
            created_at=now,
            expires_at=now + QUOTE_VALIDITY,
        )
        QuoteLineItem.objects.bulk_create(
            QuoteLineItem(
                quote=quote,
                position=position,
                kind=item.kind,
                description=item.description,
                source=item.source,
                reason=item.reason,
                amount=item.amount,
            )
            for position, item in enumerate(price.line_items)
        )
        QuotedUnit.objects.bulk_create(
            QuotedUnit(quote=quote, handling_unit=unit, freight_class=freight_class)
            for unit, freight_class in zip(units, classes, strict=True)
        )
        quotes.append(quote)
    return quotes
