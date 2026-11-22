from datetime import date

from django.test import SimpleTestCase

from quotes.pickup import (
    PickupDateError,
    add_business_days,
    is_business_day,
    validate_pickup_date,
)

# Wednesday 2026-11-11 is "today" in these tests; nothing here reads the real clock.
TODAY = date(2026, 11, 11)


class IsBusinessDayTests(SimpleTestCase):
    def test_monday_to_friday_are_business_days(self):
        for day in range(9, 14):  # Mon 9 Nov to Fri 13 Nov 2026
            with self.subTest(day=day):
                self.assertTrue(is_business_day(date(2026, 11, day)))

    def test_saturday_and_sunday_are_not(self):
        self.assertFalse(is_business_day(date(2026, 11, 14)))
        self.assertFalse(is_business_day(date(2026, 11, 15)))

    def test_holidays_are_not_considered_in_slice_1(self):
        # Thanksgiving 2026 (Thursday 26 Nov) still counts as a business day for now.
        self.assertTrue(is_business_day(date(2026, 11, 26)))


class ValidatePickupDateTests(SimpleTestCase):
    def test_weekday_after_today_is_accepted(self):
        for pickup in (date(2026, 11, 12), date(2026, 11, 13), date(2026, 11, 16)):
            with self.subTest(pickup=pickup):
                validate_pickup_date(pickup, TODAY)  # no exception

    def test_today_is_rejected(self):
        with self.assertRaisesMessage(PickupDateError, "after today"):
            validate_pickup_date(TODAY, TODAY)

    def test_past_dates_are_rejected(self):
        for pickup in (date(2026, 11, 10), date(2026, 1, 5)):
            with (
                self.subTest(pickup=pickup),
                self.assertRaisesMessage(PickupDateError, "after today"),
            ):
                validate_pickup_date(pickup, TODAY)

    def test_weekend_after_today_is_rejected(self):
        for pickup in (date(2026, 11, 14), date(2026, 11, 15)):
            with (
                self.subTest(pickup=pickup),
                self.assertRaisesMessage(PickupDateError, "business day"),
            ):
                validate_pickup_date(pickup, TODAY)

    def test_past_weekend_is_rejected_as_not_after_today(self):
        with self.assertRaisesMessage(PickupDateError, "after today"):
            validate_pickup_date(date(2026, 11, 7), TODAY)  # a past Saturday

    def test_result_depends_on_the_today_passed_in(self):
        pickup = date(2026, 11, 12)
        validate_pickup_date(pickup, TODAY)
        with self.assertRaises(PickupDateError):
            validate_pickup_date(pickup, date(2026, 11, 12))


class AddBusinessDaysTests(SimpleTestCase):
    """Delivery estimates: transit days count business days, the pickup date is day 0."""

    def test_zero_days_is_the_start_date(self):
        self.assertEqual(add_business_days(date(2026, 11, 30), 0), date(2026, 11, 30))

    def test_worked_example_1_three_days_from_monday(self):
        self.assertEqual(add_business_days(date(2026, 11, 30), 3), date(2026, 12, 3))

    def test_worked_example_2_two_days_from_monday(self):
        self.assertEqual(add_business_days(date(2026, 11, 23), 2), date(2026, 11, 25))

    def test_worked_example_3_four_days_skips_the_weekend(self):
        # Tuesday 1 Dec + 4: Wed, Thu, Fri, then Monday 7 Dec (not Saturday 5 Dec).
        self.assertEqual(add_business_days(date(2026, 12, 1), 4), date(2026, 12, 7))

    def test_worked_example_4_two_days_from_thursday(self):
        self.assertEqual(add_business_days(date(2026, 12, 3), 2), date(2026, 12, 7))

    def test_worked_example_5_three_days_from_monday(self):
        self.assertEqual(add_business_days(date(2026, 12, 7), 3), date(2026, 12, 10))

    def test_a_friday_start_lands_on_a_business_day(self):
        self.assertEqual(add_business_days(date(2026, 12, 4), 1), date(2026, 12, 7))

    def test_holidays_are_ignored(self):
        # Thanksgiving, Thursday 26 Nov 2026, still counts as a business day (Slice 1 rule).
        self.assertEqual(add_business_days(date(2026, 11, 25), 1), date(2026, 11, 26))

    def test_negative_days_are_rejected(self):
        with self.assertRaises(ValueError):
            add_business_days(date(2026, 11, 30), -1)
