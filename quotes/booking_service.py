"""Booking a quote and cancelling a booking (Slice 3).

`book_quote` checks the state rules in a fixed order (already booked first, then
`Quote.check_bookable`), then saves the booking and its bill of lading in one transaction: either
both are saved or neither is. The caller passes the current time in, so nothing here reads the
real clock. Contacts arrive already cleaned (see contacts.py).
"""

from django.db import IntegrityError, transaction
from django.utils import timezone

from . import booking_status
from .bill_of_lading import Party, UnitLine, booking_number_for, build_bill_of_lading
from .contacts import Contact
from .models import Booking, BookingStatus, Quote, QuoteRequest

ALREADY_BOOKED = "This quote has already been booked."
REQUEST_ALREADY_BOOKED = "This quote request already has an active booking."
ALREADY_CANCELLED = "This booking is already cancelled."


class BookingConflict(Exception):
    """The stored state blocks the request. The message is the reason shown to the client (409)."""


def _party(contact: Contact, request: QuoteRequest, side: str) -> Party:
    return Party(
        contact=contact,
        street=getattr(request, f"{side}_street"),
        city=getattr(request, f"{side}_city"),
        state=getattr(request, f"{side}_state"),
        postal_code=getattr(request, f"{side}_postal_code"),
        location_type=getattr(request, f"{side}_location_type"),
    )


def _unit_lines(quote: Quote) -> list[UnitLine]:
    """The request's handling units, in order, each with the class that priced it on the quote."""
    classes = {qu.handling_unit_id: qu.freight_class for qu in quote.quoted_units.all()}
    return [
        UnitLine(
            unit_type=unit.unit_type,
            quantity=unit.quantity,
            weight_lb=unit.weight_lb,
            length_in=unit.length_in,
            width_in=unit.width_in,
            height_in=unit.height_in,
            freight_class=classes[unit.pk],
            commodity_description=unit.commodity_description,
            nmfc_code=unit.nmfc_code,
            stackable=unit.stackable,
        )
        for unit in quote.quote_request.handling_units.all()
    ]


@transaction.atomic
def book_quote(
    quote: Quote, shipper: Contact, receiver: Contact, special_instructions: str, now
) -> Booking:
    """Book `quote` and return the booking, with its bill of lading stored.

    Raises `BookingConflict` (saving nothing) if the quote already has a booking (even a
    cancelled one), if another quote of the same request has an active booking, or if
    `check_bookable(now)` fails.
    """
    # Lock the request row so two bookings of one request cannot both pass the checks below.
    # (SQLite ignores the lock; it serialises writers anyway. PostgreSQL honours it.)
    request = QuoteRequest.objects.select_for_update().get(pk=quote.quote_request_id)

    if Booking.objects.filter(quote=quote).exists():
        raise BookingConflict(ALREADY_BOOKED)
    if Booking.objects.filter(quote__quote_request=request, status=BookingStatus.BOOKED).exists():
        raise BookingConflict(REQUEST_ALREADY_BOOKED)
    check = quote.check_bookable(now)
    if not check.bookable:
        raise BookingConflict(check.reason)

    try:
        with transaction.atomic():
            booking = Booking.objects.create(
                quote=quote,
                booked_at=now,
                shipper_name=shipper.name,
                shipper_phone=shipper.phone,
                shipper_email=shipper.email,
                receiver_name=receiver.name,
                receiver_phone=receiver.phone,
                receiver_email=receiver.email,
                special_instructions=special_instructions,
            )
    except IntegrityError:
        # Another request booked this quote between our check and our insert.
        raise BookingConflict(ALREADY_BOOKED) from None

    booking.attach_bill_of_lading(
        build_bill_of_lading(
            booking_number=booking_number_for(booking.pk),
            booking_date=timezone.localtime(now).date(),
            pickup_date=request.pickup_date,
            carrier_code=quote.carrier_code,
            carrier_name=quote.carrier_name,
            shipper=_party(shipper, request, "origin"),
            consignee=_party(receiver, request, "destination"),
            units=_unit_lines(quote),
            liftgate_requested=request.liftgate_requested,
            appointment_requested=request.appointment_requested,
            special_instructions=special_instructions,
        )
    )
    return booking


@transaction.atomic
def cancel_booking(booking: Booking, reason: str, now) -> Booking:
    """Cancel `booking` if its status allows it; raise `BookingConflict` if not."""
    # Re-read under a lock so a concurrent cancel is seen.
    current = Booking.objects.select_for_update().get(pk=booking.pk)
    if not booking_status.can_transition(current.status, BookingStatus.CANCELLED):
        raise BookingConflict(ALREADY_CANCELLED)
    current.mark_cancelled(reason, now)
    return current
