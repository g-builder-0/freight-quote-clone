"""Slice 2 step 5: creating a new tariff version by copying the current one."""

import json
import tempfile
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from io import StringIO
from pathlib import Path

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from quotes.freight_class import CLASS_TABLE_VERSION
from quotes.models import (
    AccessorialFee,
    CarrierTariff,
    Quote,
    QuoteRequest,
    TariffVersion,
    WeightBreakRate,
)
from quotes.tariff_versions import TariffChangeError, count_rows, create_tariff_version
from quotes.tests.tariff_fixture import TARIFFS

# Later than the seeded version, which is created when the test database is built.
LATER = datetime(2099, 1, 1, tzinfo=UTC)


def table_counts():
    return [
        TariffVersion.objects.count(),
        CarrierTariff.objects.count(),
        WeightBreakRate.objects.count(),
        AccessorialFee.objects.count(),
    ]


def data_of(version):
    return {carrier.code: carrier.to_data() for carrier in version.carriers.all()}


class CopyTests(TestCase):
    def test_an_empty_change_file_copies_every_row(self):
        old = TariffVersion.current()
        new = create_tariff_version("RATES-2026-2", {}, created_at=LATER)
        self.assertEqual(count_rows(old), 31)
        self.assertEqual(count_rows(new), 31)
        self.assertEqual(table_counts(), [2, 6, 30, 24])  # 62 rows: 31 + 31
        self.assertEqual(data_of(new), TARIFFS)

    def test_the_new_version_becomes_current_and_the_old_one_is_untouched(self):
        old = TariffVersion.current()
        new = create_tariff_version("RATES-2026-2", {}, created_at=LATER)
        self.assertEqual(TariffVersion.current(), new)
        self.assertEqual(data_of(old), TARIFFS)
        self.assertEqual(old.label, "RATES-2026-1")

    def test_a_fee_change_changes_only_that_fee(self):
        old = TariffVersion.current()
        new = create_tariff_version(
            "RATES-2026-2", {"mid": {"fees": {"liftgate": "90.00"}}}, created_at=LATER
        )
        new_mid = new.carriers.get(code="mid")
        self.assertEqual(new_mid.fees.get(fee_type="liftgate").amount, Decimal("90.00"))
        # Every other value of every carrier equals the old version.
        expected = {**TARIFFS}
        mid = TARIFFS["mid"]
        expected["mid"] = type(mid)(
            code=mid.code, name=mid.name, minimum_charge=mid.minimum_charge,
            fuel_percent=mid.fuel_percent, transit_adjustment_days=mid.transit_adjustment_days,
            weight_breaks=mid.weight_breaks, fees={**mid.fees, "liftgate": Decimal("90.00")},
        )  # fmt: skip
        self.assertEqual(data_of(new), expected)
        # The old version still says $85.
        self.assertEqual(
            old.carriers.get(code="mid").fees.get(fee_type="liftgate").amount, Decimal("85.00")
        )

    def test_a_weight_break_minimum_fuel_and_transit_change(self):
        new = create_tariff_version(
            "RATES-2026-2",
            {
                "cheap": {
                    "minimum_charge": "80",
                    "fuel_percent": "0.30",
                    "transit_adjustment_days": 2,
                    "weight_breaks": {"1000": "31.00"},
                }
            },
            created_at=LATER,
        )
        cheap = new.carriers.get(code="cheap").to_data()
        self.assertEqual(cheap.minimum_charge, Decimal("80"))
        self.assertEqual(cheap.fuel_percent, Decimal("0.30"))
        self.assertEqual(cheap.transit_adjustment_days, 2)
        self.assertEqual(
            [(b.from_lb, b.rate_per_cwt) for b in cheap.weight_breaks],
            [(0, Decimal("42")), (500, Decimal("35")), (1000, Decimal("31")),
             (2000, Decimal("25")), (5000, Decimal("20"))],
        )  # fmt: skip
        self.assertEqual(data_of(new)["mid"], TARIFFS["mid"])
        self.assertEqual(data_of(new)["fast"], TARIFFS["fast"])

    def test_the_default_created_at_is_now_and_makes_the_new_version_current(self):
        new = create_tariff_version("RATES-2026-2", {})
        self.assertEqual(TariffVersion.current(), new)


class RejectedChangeTests(TestCase):
    """A bad request creates nothing: the table counts stay at the seeded 1 / 3 / 15 / 12."""

    def assert_rejected(self, label, changes, **kwargs):
        with self.assertRaises(TariffChangeError):
            create_tariff_version(label, changes, **kwargs)
        self.assertEqual(table_counts(), [1, 3, 15, 12])
        self.assertEqual(TariffVersion.current().label, "RATES-2026-1")

    def test_unknown_carrier(self):
        self.assert_rejected(
            "RATES-2026-2", {"nope": {"fees": {"liftgate": "90"}}}, created_at=LATER
        )

    def test_unknown_fee_type(self):
        self.assert_rejected("RATES-2026-2", {"mid": {"fees": {"hazmat": "90"}}}, created_at=LATER)

    def test_unknown_weight_break(self):
        self.assert_rejected(
            "RATES-2026-2", {"mid": {"weight_breaks": {"1500": "30"}}}, created_at=LATER
        )

    def test_unknown_field(self):
        self.assert_rejected("RATES-2026-2", {"mid": {"colour": "red"}}, created_at=LATER)

    def test_a_non_numeric_amount(self):
        self.assert_rejected(
            "RATES-2026-2", {"mid": {"fees": {"liftgate": "ninety"}}}, created_at=LATER
        )

    def test_a_negative_amount(self):
        self.assert_rejected("RATES-2026-2", {"mid": {"minimum_charge": "-1"}}, created_at=LATER)

    def test_a_fractional_transit_adjustment(self):
        self.assert_rejected(
            "RATES-2026-2", {"mid": {"transit_adjustment_days": 1.5}}, created_at=LATER
        )

    def test_a_change_file_that_is_not_an_object(self):
        self.assert_rejected("RATES-2026-2", ["mid"], created_at=LATER)

    def test_a_valid_change_followed_by_a_bad_one_creates_nothing(self):
        # The valid cheap change must not be left behind when the mid change is rejected.
        self.assert_rejected(
            "RATES-2026-2",
            {"cheap": {"fees": {"liftgate": "70"}}, "mid": {"fees": {"hazmat": "1"}}},
            created_at=LATER,
        )

    def test_a_duplicate_label(self):
        self.assert_rejected("RATES-2026-1", {}, created_at=LATER)

    def test_an_empty_label(self):
        self.assert_rejected("  ", {}, created_at=LATER)

    def test_a_created_at_that_is_not_later_than_the_current_version(self):
        current = TariffVersion.current()
        self.assert_rejected("RATES-2026-2", {}, created_at=current.created_at)
        self.assert_rejected("RATES-2026-2", {}, created_at=current.created_at - timedelta(days=1))


class QuoteAfterANewVersionTests(TestCase):
    def test_a_quote_made_under_the_old_version_fails_the_booking_check(self):
        request = QuoteRequest.objects.create(
            origin_street="1 A St", origin_city="Allen", origin_state="TX",
            origin_postal_code="75002", origin_location_type="business_dock",
            destination_street="2 B St", destination_city="Dallas", destination_state="TX",
            destination_postal_code="75201", destination_location_type="business_dock",
            pickup_date=date(2099, 6, 2),
        )  # fmt: skip
        created = datetime(2098, 12, 30, 12, 0, tzinfo=UTC)
        quote = Quote.objects.create(
            quote_request=request, carrier_code="mid", carrier_name="Mid",
            tariff_version=TariffVersion.current(), rate_table_version="RATES-2026-1",
            class_table_version=CLASS_TABLE_VERSION, total=Decimal("493.68"), transit_days=2,
            estimated_delivery_date=date(2099, 6, 4), created_at=created,
            expires_at=created + timedelta(days=7),
        )  # fmt: skip
        before = datetime(2098, 12, 31, 12, 0, tzinfo=UTC)
        self.assertTrue(quote.check_bookable(before).bookable)
        create_tariff_version("RATES-2026-2", {}, created_at=LATER)
        result = quote.check_bookable(before)
        self.assertFalse(result.bookable)
        self.assertIn("rates have changed", result.reason)


class CommandTests(TestCase):
    def run_command(self, label, changes):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "changes.json"
            path.write_text(changes if isinstance(changes, str) else json.dumps(changes))
            out = StringIO()
            call_command("create_tariff_version", label, str(path), stdout=out)
            return out.getvalue()

    def test_the_command_creates_the_version_and_reports_it(self):
        output = self.run_command("RATES-2026-2", {"mid": {"fees": {"liftgate": "90.00"}}})
        self.assertIn("RATES-2026-2", output)
        self.assertIn("31 rows", output)
        self.assertEqual(table_counts(), [2, 6, 30, 24])
        self.assertEqual(TariffVersion.current().label, "RATES-2026-2")

    def test_the_command_reports_a_bad_change_and_creates_nothing(self):
        with self.assertRaisesMessage(CommandError, "Unknown carrier"):
            self.run_command("RATES-2026-2", {"nope": {}})
        self.assertEqual(table_counts(), [1, 3, 15, 12])

    def test_the_command_rejects_a_file_that_is_not_json(self):
        with self.assertRaisesMessage(CommandError, "not valid JSON"):
            self.run_command("RATES-2026-2", "{not json")
        self.assertEqual(table_counts(), [1, 3, 15, 12])

    def test_the_command_rejects_a_missing_file(self):
        with self.assertRaisesMessage(CommandError, "Cannot read"):
            call_command("create_tariff_version", "RATES-2026-2", "/nonexistent/changes.json")
