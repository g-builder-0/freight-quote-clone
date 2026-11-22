"""Creating quotes for a saved quote request (Slice 2).

One call prices the request with every carrier in the current tariff version and saves one
immutable Quote per carrier, with its line items and the class used for each handling unit, in a
single transaction: either every quote is saved or none is. The caller passes the current time in,
so tests supply the clock and nothing here reads the real one.
"""

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
from .pricing import ShipmentUnit, price_quote, pricing_class


class NoTariffError(Exception):
    """There is no current tariff version, so nothing can be priced."""


@transaction.atomic
def create_quotes(quote_request: QuoteRequest, now) -> list[Quote]:
    """Create one quote per carrier for `quote_request`; return them in carrier order.

    Raises `pickup.PickupDateError`, saving nothing, if the pickup date is no longer a business
    day after today (America/Chicago): the pickup date is checked again here because a request can
    be quoted long after it was saved.
    """
    today = timezone.localtime(now).date()
    pickup.validate_pickup_date(quote_request.pickup_date, today)

    version = TariffVersion.current()
    if version is None:
        raise NoTariffError("There is no current tariff version.")

    units = list(quote_request.handling_units.all())
    # The class that prices each unit: the shipper's class if given, else the suggested class.
    classes = [pricing_class(unit.freight_class, unit.suggested_class) for unit in units]
    shipment = [
        ShipmentUnit(unit.weight_lb, unit.quantity, freight_class)
        for unit, freight_class in zip(units, classes, strict=True)
    ]

    quotes = []
    for carrier in version.carriers.order_by("id"):
        tariff = carrier.to_data()
        price = price_quote(
            tariff,
            origin_postal_code=quote_request.origin_postal_code,
            destination_postal_code=quote_request.destination_postal_code,
            origin_location_type=quote_request.origin_location_type,
            destination_location_type=quote_request.destination_location_type,
            pickup_date=quote_request.pickup_date,
            units=shipment,
            liftgate_requested=quote_request.liftgate_requested,
            appointment_requested=quote_request.appointment_requested,
        )
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
