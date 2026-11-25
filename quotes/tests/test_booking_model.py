"""Slice 3 step 3: the Booking model, its one-quote rule and its guard."""

from datetime import timedelta
from unittest import mock

from django.contrib import admin
from django.db import IntegrityError, models, transaction
from django.test import RequestFactory, TestCase

from quotes.models import Booking, BookingStatus, ImmutableRecordError, Quote
from quotes.services import create_quotes
from quotes.tests.quote_helpers import NOW, example_1_request

SNAPSHOT = {"number": "BK-000001", "units": []}


def make_booking(quote: Quote, **overrides) -> Booking:
    fields = dict(
        quote=quote,
        booked_at=NOW + timedelta(minutes=80),
        shipper_name="Dana Whitfield",
        shipper_phone="972-555-0142",
        receiver_name="Marcus Bell",
        receiver_phone="404-555-0178",
        special_instructions="Call receiver 30 minutes before delivery.",
        bill_of_lading=SNAPSHOT,
    )
    fields.update(overrides)
    return Booking.objects.create(**fields)


class BookingModelTests(TestCase):
    def setUp(self):
        self.quote = create_quotes(example_1_request(), NOW)[1]

    def test_a_new_booking_is_booked_and_not_cancelled(self):
        booking = make_booking(self.quote)
        self.assertEqual(booking.status, BookingStatus.BOOKED)
        self.assertIsNone(booking.cancelled_at)
        self.assertEqual(booking.cancel_reason, "")

    def test_the_booking_number_is_bk_plus_the_id_padded_to_six_digits(self):
        booking = make_booking(self.quote)
        self.assertEqual(booking.booking_number, f"BK-{booking.pk:06d}")
        self.assertRegex(booking.booking_number, r"^BK-\d{6}$")

    def test_an_unsaved_booking_has_no_number_yet(self):
        self.assertEqual(Booking(quote=self.quote).booking_number, "")

    def test_the_quote_reaches_its_booking_and_the_booking_its_quote(self):
        booking = make_booking(self.quote)
        self.assertEqual(self.quote.booking, booking)
        self.assertEqual(booking.quote, self.quote)

    def test_a_quote_can_have_only_one_booking_even_at_the_database(self):
        make_booking(self.quote)
        with self.assertRaises(IntegrityError), transaction.atomic():
            make_booking(self.quote)
        self.assertEqual(Booking.objects.count(), 1)

    def test_other_quotes_of_the_same_request_are_not_blocked_by_the_model(self):
        # The "one active booking per request" rule is the service's job (step 4), not the table's.
        other = Quote.objects.filter(quote_request=self.quote.quote_request).exclude(
            pk=self.quote.pk
        )
        make_booking(self.quote)
        make_booking(other.first())
        self.assertEqual(Booking.objects.count(), 2)

    def test_the_snapshot_is_stored_as_json_and_read_back_unchanged(self):
        booking = make_booking(self.quote, bill_of_lading={"number": "BK-000007", "units": [1, 2]})
        booking.refresh_from_db()
        self.assertEqual(booking.bill_of_lading, {"number": "BK-000007", "units": [1, 2]})


class BookingGuardTests(TestCase):
    def setUp(self):
        self.quote = create_quotes(example_1_request(), NOW)[1]
        self.booking = make_booking(self.quote)

    def test_a_saved_booking_cannot_be_edited(self):
        self.booking.receiver_name = "Someone Else"
        with self.assertRaises(ImmutableRecordError):
            self.booking.save()
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.receiver_name, "Marcus Bell")

    def test_the_status_cannot_be_changed_by_a_plain_save(self):
        self.booking.status = BookingStatus.CANCELLED
        with self.assertRaises(ImmutableRecordError):
            self.booking.save()

    def test_the_snapshot_cannot_be_changed(self):
        self.booking.bill_of_lading = {"number": "BK-999999"}
        with self.assertRaises(ImmutableRecordError):
            self.booking.save()
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.bill_of_lading, SNAPSHOT)

    def test_a_booking_cannot_be_deleted(self):
        with self.assertRaises(ImmutableRecordError):
            self.booking.delete()
        self.assertEqual(Booking.objects.count(), 1)

    def test_the_admin_shows_bookings_read_only(self):
        model_admin = admin.site._registry[Booking]
        request = RequestFactory().get("/")
        self.assertFalse(model_admin.has_add_permission(request))
        self.assertFalse(model_admin.has_change_permission(request, self.booking))
        self.assertFalse(model_admin.has_delete_permission(request, self.booking))


class MarkCancelledTests(TestCase):
    def setUp(self):
        self.quote = create_quotes(example_1_request(), NOW)[1]
        self.booking = make_booking(self.quote)
        self.when = NOW + timedelta(hours=1)

    def test_mark_cancelled_records_the_status_time_and_reason(self):
        self.booking.mark_cancelled("Shipper cancelled", self.when)
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, BookingStatus.CANCELLED)
        self.assertEqual(self.booking.cancelled_at, self.when)
        self.assertEqual(self.booking.cancel_reason, "Shipper cancelled")

    def test_cancelling_changes_nothing_else(self):
        before = Booking.objects.values().get(pk=self.booking.pk)
        self.booking.mark_cancelled("Shipper cancelled", self.when)
        after = Booking.objects.values().get(pk=self.booking.pk)
        changed = {key for key in before if before[key] != after[key]}
        self.assertEqual(changed, {"status", "cancelled_at", "cancel_reason"})

    def test_cancelling_leaves_the_quote_unchanged(self):
        before = Quote.objects.values().get(pk=self.quote.pk)
        self.booking.mark_cancelled("Shipper cancelled", self.when)
        self.assertEqual(Quote.objects.values().get(pk=self.quote.pk), before)

    def test_the_guard_is_closed_again_after_cancelling(self):
        self.booking.mark_cancelled("Shipper cancelled", self.when)
        self.booking.receiver_name = "Someone Else"
        with self.assertRaises(ImmutableRecordError):
            self.booking.save()

    def test_the_guard_is_closed_even_if_the_cancel_save_fails(self):
        with mock.patch.object(models.Model, "save", side_effect=RuntimeError("disk full")):
            with self.assertRaises(RuntimeError):
                self.booking.mark_cancelled("Shipper cancelled", self.when)
        self.booking.receiver_name = "Someone Else"
        with self.assertRaises(ImmutableRecordError):
            self.booking.save()
