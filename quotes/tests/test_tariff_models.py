"""Slice 2 step 4: the seeded tariff, the "current version" rule and immutability."""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from django.db.models import ProtectedError
from django.test import TestCase

from quotes.freight_class import CLASS_TABLE_VERSION
from quotes.models import (
    AccessorialFee,
    CarrierTariff,
    HandlingUnit,
    ImmutableRecordError,
    Quote,
    QuotedUnit,
    QuoteLineItem,
    QuoteRequest,
    TariffVersion,
    WeightBreakRate,
)
from quotes.tests.tariff_fixture import TARIFFS

NOW = datetime(2026, 11, 25, 14, 10, tzinfo=UTC)


class SeededTariffTests(TestCase):
    """The first version, RATES-2026-1, matches the approved tariff table exactly."""

    def test_there_is_one_version_labelled_rates_2026_1(self):
        self.assertEqual(
            list(TariffVersion.objects.values_list("label", flat=True)), ["RATES-2026-1"]
        )

    def test_the_version_has_31_rows_in_total(self):
        # 1 version + 3 carriers + 3 x 5 weight-break rates + 3 x 4 fees = 31 rows.
        counts = [
            TariffVersion.objects.count(),
            CarrierTariff.objects.count(),
            WeightBreakRate.objects.count(),
            AccessorialFee.objects.count(),
        ]
        self.assertEqual(counts, [1, 3, 15, 12])
        self.assertEqual(sum(counts), 31)

    def test_every_carrier_matches_the_approved_table(self):
        version = TariffVersion.current()
        self.assertEqual({c.code for c in version.carriers.all()}, set(TARIFFS))
        for carrier in version.carriers.all():
            with self.subTest(carrier=carrier.code):
                self.assertEqual(carrier.to_data(), TARIFFS[carrier.code])

    def test_the_mid_carrier_numbers_one_by_one(self):
        mid = CarrierTariff.objects.get(code="mid")
        self.assertEqual(mid.name, "Mid")
        self.assertEqual(mid.minimum_charge, Decimal("90"))
        self.assertEqual(mid.fuel_percent, Decimal("0.32"))
        self.assertEqual(mid.transit_adjustment_days, 0)
        self.assertEqual(
            [(r.from_lb, r.to_lb, r.rate_per_cwt) for r in mid.weight_breaks.all()],
            [(0, 499, Decimal("48")), (500, 999, Decimal("40")), (1000, 1999, Decimal("34")),
             (2000, 4999, Decimal("28")), (5000, None, Decimal("23"))],
        )  # fmt: skip
        self.assertEqual(
            {f.fee_type: f.amount for f in mid.fees.all()},
            {"residential": Decimal("100"), "limited_access": Decimal("120"),
             "liftgate": Decimal("85"), "appointment": Decimal("50")},
        )  # fmt: skip


FAR_FUTURE = datetime(2099, 1, 1, tzinfo=UTC)


class CurrentVersionTests(TestCase):
    def test_the_current_version_is_the_one_with_the_latest_created_at(self):
        # Far in the future: the seeded RATES-2026-1 is stamped with the real clock when the
        # test database is built, so a fixed date near today would sometimes be older than it.
        newer = TariffVersion.objects.create(label="RATES-2026-2", created_at=FAR_FUTURE)
        self.assertEqual(TariffVersion.current(), newer)

    def test_an_older_created_at_does_not_become_current(self):
        TariffVersion.objects.create(label="RATES-OLD", created_at=NOW - timedelta(days=4000))
        self.assertEqual(TariffVersion.current().label, "RATES-2026-1")

    def test_the_id_breaks_a_tie_on_created_at(self):
        first = TariffVersion.objects.create(label="TIE-A", created_at=FAR_FUTURE)
        second = TariffVersion.objects.create(label="TIE-B", created_at=FAR_FUTURE)
        self.assertGreater(second.pk, first.pk)
        self.assertEqual(TariffVersion.current(), second)

    def test_no_version_means_no_current_version(self):
        for model in (AccessorialFee, WeightBreakRate, CarrierTariff, TariffVersion):
            model.objects.all()._raw_delete(using="default")
        self.assertIsNone(TariffVersion.current())


class ImmutabilityTests(TestCase):
    """Saved tariff and quote rows cannot be changed or deleted through the models."""

    @classmethod
    def setUpTestData(cls):
        request = QuoteRequest.objects.create(
            origin_street="1 A St", origin_city="Allen", origin_state="TX",
            origin_postal_code="75002", origin_location_type="business_dock",
            destination_street="2 B St", destination_city="Dallas", destination_state="TX",
            destination_postal_code="75201", destination_location_type="business_dock",
            pickup_date=date(2026, 12, 8),
        )  # fmt: skip
        unit = HandlingUnit.objects.create(
            quote_request=request, unit_type="pallet", quantity=1, length_in=48, width_in=40,
            height_in=40, weight_lb=1000, commodity_description="Widgets",
        )  # fmt: skip
        cls.quote = Quote.objects.create(
            quote_request=request, carrier_code="mid", carrier_name="Mid",
            tariff_version=TariffVersion.current(), rate_table_version="RATES-2026-1",
            class_table_version=CLASS_TABLE_VERSION, total=Decimal("493.68"), transit_days=2,
            estimated_delivery_date=date(2026, 12, 10), created_at=NOW,
            expires_at=NOW + timedelta(days=7),
        )  # fmt: skip
        cls.line = QuoteLineItem.objects.create(
            quote=cls.quote, position=0, kind="line_haul", description="Line-haul, class 100",
            amount=Decimal("374.00"),
        )  # fmt: skip
        cls.quoted_unit = QuotedUnit.objects.create(
            quote=cls.quote, handling_unit=unit, freight_class="100"
        )

    def rows(self):
        version = TariffVersion.current()
        carrier = version.carriers.first()
        return [
            version,
            carrier,
            carrier.weight_breaks.first(),
            carrier.fees.first(),
            self.quote,
            self.line,
            self.quoted_unit,
        ]

    def test_a_saved_row_cannot_be_saved_again(self):
        for row in self.rows():
            with self.subTest(model=type(row).__name__), self.assertRaises(ImmutableRecordError):
                row.save()

    def test_a_changed_quote_cannot_be_saved(self):
        self.quote.total = Decimal("1.00")
        with self.assertRaises(ImmutableRecordError):
            self.quote.save()
        self.quote.refresh_from_db()
        self.assertEqual(self.quote.total, Decimal("493.68"))

    def test_a_saved_row_cannot_be_deleted(self):
        for row in self.rows():
            with self.subTest(model=type(row).__name__), self.assertRaises(ImmutableRecordError):
                row.delete()

    def test_a_request_that_has_quotes_cannot_be_deleted(self):
        with self.assertRaises(ProtectedError):
            self.quote.quote_request.delete()

    def test_new_child_rows_can_still_be_added_to_a_saved_parent(self):
        QuoteLineItem.objects.create(
            quote=self.quote, position=1, kind="fuel", description="Fuel (32%)",
            amount=Decimal("119.68"),
        )  # fmt: skip
        self.assertEqual(self.quote.line_items.count(), 2)
