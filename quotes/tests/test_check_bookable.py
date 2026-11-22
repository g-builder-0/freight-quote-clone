"""Slice 2 step 6: Quote.check_bookable(now), the four conditions that must all hold."""

from datetime import UTC, date, datetime, timedelta

from django.test import TestCase

from quotes.models import Quote, TariffVersion
from quotes.services import create_quotes
from quotes.tariff_versions import create_tariff_version
from quotes.tests.quote_helpers import NOW, example_1_request, make_request


class CheckBookableTests(TestCase):
    def setUp(self):
        self.quote = create_quotes(example_1_request(), NOW)[1]  # mid; expires 2 Dec 14:10 UTC

    def test_a_fresh_quote_can_be_booked(self):
        result = self.quote.check_bookable(NOW)
        self.assertTrue(result.bookable)
        self.assertEqual(result.reason, "")

    def test_a_quote_can_be_booked_one_second_before_it_expires(self):
        # A later pickup date, so that only the expiry decides (Example 1's pickup, Monday 30 Nov,
        # passes before its quote expires on 2 Dec: that case is tested separately below).
        quote = create_quotes(make_request(pickup_date=date(2026, 12, 14)), NOW)[1]
        self.assertTrue(quote.check_bookable(quote.expires_at - timedelta(seconds=1)).bookable)

    def test_a_quote_cannot_be_booked_at_the_moment_it_expires(self):
        quote = create_quotes(make_request(pickup_date=date(2026, 12, 14)), NOW)[1]
        result = quote.check_bookable(quote.expires_at)
        self.assertFalse(result.bookable)
        self.assertIn("expired", result.reason)

    def test_an_expired_quote_cannot_be_booked(self):
        result = self.quote.check_bookable(NOW + timedelta(days=8))
        self.assertFalse(result.bookable)
        self.assertIn("expired", result.reason)

    def test_a_quote_with_a_different_class_table_version_cannot_be_booked(self):
        quote = create_quotes(make_request(), NOW)[0]
        # Quotes are immutable, so make the stale one the way an old quote would exist.
        stale = Quote.objects.create(
            quote_request=quote.quote_request, carrier_code="mid", carrier_name="Mid",
            tariff_version=TariffVersion.current(), rate_table_version="RATES-2026-1",
            class_table_version="NMFTA-2020-0", total=quote.total, transit_days=2,
            estimated_delivery_date=quote.estimated_delivery_date, created_at=NOW,
            expires_at=NOW + timedelta(days=7),
        )  # fmt: skip
        result = stale.check_bookable(NOW)
        self.assertFalse(result.bookable)
        self.assertIn("class table", result.reason)

    def test_a_quote_cannot_be_booked_once_the_rates_have_changed(self):
        later = datetime(2099, 1, 1, tzinfo=UTC)
        create_tariff_version("RATES-2026-2", {}, created_at=later)
        result = self.quote.check_bookable(NOW)
        self.assertFalse(result.bookable)
        self.assertIn("rates have changed", result.reason)

    def test_a_quote_made_under_the_new_version_can_be_booked(self):
        later = datetime(2099, 1, 1, tzinfo=UTC)
        create_tariff_version("RATES-2026-2", {}, created_at=later)
        fresh = create_quotes(example_1_request(), NOW)[1]
        self.assertTrue(fresh.check_bookable(NOW).bookable)

    def test_a_quote_cannot_be_booked_once_its_pickup_date_has_passed(self):
        # The quote (expires 2 Dec) has not expired and the versions match, but pickup was
        # Monday 30 Nov: booking on Monday 30 Nov at noon Chicago is not allowed.
        monday_noon_chicago = datetime(2026, 11, 30, 18, 0, tzinfo=UTC)
        result = self.quote.check_bookable(monday_noon_chicago)
        self.assertFalse(result.bookable)
        self.assertIn("pickup date", result.reason)

    def test_the_day_before_pickup_is_still_bookable(self):
        sunday = datetime(2026, 11, 29, 18, 0, tzinfo=UTC)
        self.assertTrue(self.quote.check_bookable(sunday).bookable)

    def test_today_is_the_date_in_chicago_not_utc(self):
        # Pickup is Tuesday 1 Dec. At 03:00 UTC on 1 Dec it is still 30 Nov (21:00) in Chicago, so
        # the pickup date is still after today.
        quote = create_quotes(make_request(pickup_date=date(2026, 12, 1)), NOW)[1]
        late_evening = datetime(2026, 12, 1, 3, 0, tzinfo=UTC)
        self.assertTrue(quote.check_bookable(late_evening).bookable)
        # At 07:00 UTC it is 01:00 on 1 Dec in Chicago: the pickup date is today, not after it.
        early_morning = datetime(2026, 12, 1, 7, 0, tzinfo=UTC)
        self.assertFalse(quote.check_bookable(early_morning).bookable)

    def test_the_expiry_is_reported_first_when_several_conditions_fail(self):
        later = datetime(2099, 1, 1, tzinfo=UTC)
        create_tariff_version("RATES-2026-2", {}, created_at=later)
        result = self.quote.check_bookable(
            NOW + timedelta(days=30)
        )  # expired, old rates, past pickup
        self.assertIn("expired", result.reason)

    def test_checking_does_not_change_the_quote(self):
        before = (self.quote.total, self.quote.expires_at, self.quote.rate_table_version)
        self.quote.check_bookable(NOW + timedelta(days=30))
        self.quote.refresh_from_db()
        self.assertEqual(
            (self.quote.total, self.quote.expires_at, self.quote.rate_table_version), before
        )
