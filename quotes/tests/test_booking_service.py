"""Slice 3 step 4: book_quote and cancel_booking, with Graham's Case 1 and Case 4 inputs."""

from datetime import UTC, date, datetime
from decimal import Decimal
from unittest import mock

from django.test import TestCase

from quotes.booking_service import BookingConflict, book_quote, cancel_booking
from quotes.contacts import Contact
from quotes.models import Booking, BookingStatus, Quote
from quotes.services import create_quotes
from quotes.tariff_versions import create_tariff_version
from quotes.tests.quote_helpers import NOW, make_request, unit_fields

BOOKED_AT = datetime(2026, 11, 25, 15, 30, tzinfo=UTC)  # 09:30 in Chicago
INSTRUCTIONS = (
    "Carrier must provide a liftgate for delivery; the delivery address is a residence with "
    "no loading dock. Call receiver 30 minutes before delivery."
)
DANA = Contact("Dana Whitfield", phone="972-555-0142")
MARCUS = Contact("Marcus Bell", phone="404-555-0178")
LUIS = Contact("Luis Herrera", phone="602-555-0126")


# fmt: off
def case_1_request():
    """Example 1 with Graham's Case 1 addresses and commodity descriptions."""
    return make_request(
        units=[
            unit_fields(
                weight_lb=1200, freight_class="55",
                commodity_description="Ceramic floor tiles, boxed",
            ),
            unit_fields(
                unit_type="crate", weight_lb=400, freight_class="125",
                commodity_description="Rack-mount network switches",
            ),
        ],
        origin_street="2200 Commerce Park Way",
        destination_street="418 Magnolia Ridge Dr SE", destination_city="Atlanta",
        destination_state="GA", destination_postal_code="30301",
        destination_location_type="residential", liftgate_requested=True,
    )  # fmt: skip


# fmt: on
def example_4_request():
    return make_request(
        units=[unit_fields(weight_lb=1000, freight_class="100")],
        origin_street="2200 Commerce Park Way",
        destination_street="1200 Sonoran Business Pkwy", destination_city="Phoenix",
        destination_state="AZ", destination_postal_code="85001",
        pickup_date=date(2026, 12, 3),
    )  # fmt: skip


def mid_quote(request) -> Quote:
    return create_quotes(request, NOW)[1]


def book_case_1(quote, now=BOOKED_AT):
    return book_quote(quote, DANA, MARCUS, INSTRUCTIONS, now)


class BookQuoteTests(TestCase):
    def test_case_1_a_normal_booking(self):
        quote = mid_quote(case_1_request())
        before = Quote.objects.values().get(pk=quote.pk)
        booking = book_case_1(quote)

        self.assertEqual(booking.booking_number, "BK-000001")
        self.assertEqual(booking.status, BookingStatus.BOOKED)
        self.assertEqual(booking.booked_at, BOOKED_AT)
        self.assertEqual(booking.quote.total, Decimal("913.85"))
        self.assertEqual(Booking.objects.count(), 1)
        self.assertEqual(Quote.objects.values().get(pk=quote.pk), before)

        bol = Booking.objects.get(pk=booking.pk).bill_of_lading
        self.assertEqual(bol["number"], "BK-000001")
        self.assertEqual(bol["booking_date"], "2026-11-25")
        self.assertEqual(bol["pickup_date"], "2026-11-30")
        self.assertEqual(bol["carrier"], {"code": "mid", "name": quote.carrier_name})
        self.assertEqual(bol["total_weight_lb"], 1600)
        self.assertEqual(bol["accessorials"], ["liftgate"])
        self.assertEqual(bol["special_instructions"], INSTRUCTIONS)
        self.assertEqual(bol["shipper"]["name"], "Dana Whitfield")
        self.assertEqual(bol["shipper"]["street"], "2200 Commerce Park Way")
        self.assertEqual(bol["shipper"]["location_type"], "business_dock")
        self.assertEqual(bol["consignee"]["name"], "Marcus Bell")
        self.assertEqual(bol["consignee"]["street"], "418 Magnolia Ridge Dr SE")
        self.assertEqual(bol["consignee"]["postal_code"], "30301")
        self.assertEqual(bol["consignee"]["location_type"], "residential")
        self.assertEqual(
            [(u["unit_type"], u["weight_lb"], u["freight_class"], u["commodity_description"])
             for u in bol["units"]],
            [("pallet", 1200, "55", "Ceramic floor tiles, boxed"),
             ("crate", 400, "125", "Rack-mount network switches")],
        )  # fmt: skip
        self.assertNotIn("total", bol)
        self.assertNotIn("price", bol)

    def test_the_booking_stores_both_contacts_and_the_instructions(self):
        booking = book_quote(
            mid_quote(case_1_request()),
            DANA,
            Contact("Marcus Bell", phone="404-555-0178", email="marcus@example.com"),
            INSTRUCTIONS,
            BOOKED_AT,
        )
        booking.refresh_from_db()
        self.assertEqual(
            (booking.shipper_name, booking.shipper_phone, booking.shipper_email),
            ("Dana Whitfield", "972-555-0142", ""),
        )
        self.assertEqual(
            (booking.receiver_name, booking.receiver_phone, booking.receiver_email),
            ("Marcus Bell", "404-555-0178", "marcus@example.com"),
        )
        self.assertEqual(booking.special_instructions, INSTRUCTIONS)

    def test_the_bill_of_lading_uses_the_class_that_priced_the_unit(self):
        request = make_request(units=[unit_fields(weight_lb=500, freight_class="")])
        quote = mid_quote(request)
        priced_as = quote.quoted_units.get().freight_class
        bol = book_case_1(quote).bill_of_lading
        self.assertEqual(bol["units"][0]["freight_class"], priced_as)

    def test_4a_booking_one_minute_before_expiry_succeeds(self):
        quote = mid_quote(example_4_request())
        booking = book_quote(quote, DANA, LUIS, "", datetime(2026, 12, 2, 14, 9, tzinfo=UTC))
        self.assertEqual(booking.status, BookingStatus.BOOKED)
        self.assertEqual(booking.bill_of_lading["booking_date"], "2026-12-02")

    def test_4b_booking_at_the_moment_of_expiry_is_refused(self):
        quote = mid_quote(example_4_request())
        with self.assertRaises(BookingConflict) as raised:
            book_quote(quote, DANA, LUIS, "", datetime(2026, 12, 2, 14, 10, tzinfo=UTC))
        self.assertEqual(str(raised.exception), "The quote has expired.")
        self.assertEqual(Booking.objects.count(), 0)

    def test_4c_pickup_date_passed(self):
        quote = mid_quote(case_1_request())
        before = Quote.objects.values().get(pk=quote.pk)
        with self.assertRaises(BookingConflict) as raised:
            book_case_1(quote, datetime(2026, 11, 30, 16, 0, tzinfo=UTC))  # 10:00 Chicago
        self.assertEqual(str(raised.exception), "The pickup date is no longer available.")
        self.assertEqual(Booking.objects.count(), 0)
        self.assertEqual(Quote.objects.values().get(pk=quote.pk), before)

    def test_4d_new_tariff_version(self):
        quote = mid_quote(case_1_request())
        create_tariff_version("RATES-2026-2", {}, created_at=datetime(2099, 1, 1, tzinfo=UTC))
        with self.assertRaises(BookingConflict) as raised:
            book_case_1(quote)
        self.assertEqual(str(raised.exception), "The rates have changed since this quote.")
        self.assertEqual(Booking.objects.count(), 0)

    def test_4e_class_table_version_changed(self):
        quote = mid_quote(case_1_request())
        with mock.patch("quotes.models.CLASS_TABLE_VERSION", "NMFTA-2099-1"):
            with self.assertRaises(BookingConflict) as raised:
                book_case_1(quote)
        self.assertEqual(
            str(raised.exception), "The freight class table has changed since this quote."
        )
        self.assertEqual(Booking.objects.count(), 0)

    def test_4f_double_booking(self):
        quote = mid_quote(case_1_request())
        first = book_case_1(quote)
        snapshot = Booking.objects.values().get(pk=first.pk)
        with self.assertRaises(BookingConflict) as raised:
            book_case_1(quote, datetime(2026, 11, 25, 15, 31, tzinfo=UTC))
        self.assertEqual(str(raised.exception), "This quote has already been booked.")
        self.assertEqual(Booking.objects.count(), 1)
        self.assertEqual(Booking.objects.values().get(pk=first.pk), snapshot)

    def test_already_booked_is_reported_before_the_check_bookable_reasons(self):
        quote = mid_quote(case_1_request())
        book_case_1(quote)
        # Now the pickup date has passed too; the booked state is still the reason given.
        with self.assertRaises(BookingConflict) as raised:
            book_case_1(quote, datetime(2026, 11, 30, 16, 0, tzinfo=UTC))
        self.assertEqual(str(raised.exception), "This quote has already been booked.")

    def test_another_quote_of_a_request_with_an_active_booking_is_refused(self):
        quotes = create_quotes(case_1_request(), NOW)
        book_case_1(quotes[1])
        with self.assertRaises(BookingConflict) as raised:
            book_case_1(quotes[0])
        self.assertEqual(str(raised.exception), "This quote request already has an active booking.")
        self.assertEqual(Booking.objects.count(), 1)

    def test_after_cancelling_another_quote_of_the_request_can_be_booked(self):
        quotes = create_quotes(case_1_request(), NOW)
        first = book_case_1(quotes[1])
        cancel_booking(first, "Shipper cancelled", BOOKED_AT)
        second = book_case_1(quotes[0])
        self.assertEqual(second.booking_number, "BK-000002")
        self.assertEqual(Booking.objects.count(), 2)

    def test_a_failure_while_saving_the_bill_of_lading_leaves_no_booking(self):
        quote = mid_quote(case_1_request())
        with mock.patch(
            "quotes.booking_service.build_bill_of_lading", side_effect=RuntimeError("boom")
        ):
            with self.assertRaises(RuntimeError):
                book_case_1(quote)
        self.assertEqual(Booking.objects.count(), 0)


class CancelBookingTests(TestCase):
    def setUp(self):
        self.quote = mid_quote(case_1_request())
        self.booking = book_case_1(self.quote)
        self.cancel_time = datetime(2026, 11, 25, 16, 0, tzinfo=UTC)  # 10:00 in Chicago

    def test_4g_cancelling_a_booked_booking(self):
        cancelled = cancel_booking(self.booking, "Shipper cancelled", self.cancel_time)
        stored = Booking.objects.get(pk=self.booking.pk)
        for booking in (cancelled, stored):
            self.assertEqual(booking.status, BookingStatus.CANCELLED)
            self.assertEqual(booking.cancelled_at, self.cancel_time)
            self.assertEqual(booking.cancel_reason, "Shipper cancelled")
        self.assertEqual(stored.bill_of_lading, self.booking.bill_of_lading)

    def test_4h_cancelling_twice(self):
        cancel_booking(self.booking, "Shipper cancelled", self.cancel_time)
        with self.assertRaises(BookingConflict) as raised:
            cancel_booking(self.booking, "Again", self.cancel_time)
        self.assertEqual(str(raised.exception), "This booking is already cancelled.")
        self.assertEqual(Booking.objects.get().cancel_reason, "Shipper cancelled")

    def test_4i_the_cancelled_bookings_quote_cannot_be_booked_again(self):
        cancel_booking(self.booking, "Shipper cancelled", self.cancel_time)
        with self.assertRaises(BookingConflict) as raised:
            book_case_1(self.quote, self.cancel_time)
        self.assertEqual(str(raised.exception), "This quote has already been booked.")
        self.assertEqual(Booking.objects.count(), 1)

    def test_cancelling_leaves_the_quote_unchanged(self):
        before = Quote.objects.values().get(pk=self.quote.pk)
        cancel_booking(self.booking, "Shipper cancelled", self.cancel_time)
        self.assertEqual(Quote.objects.values().get(pk=self.quote.pk), before)
