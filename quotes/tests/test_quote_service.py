"""Slice 2 step 6: creating quotes for a request, all in one transaction."""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from unittest import mock

from django.test import TestCase

from quotes import pricing
from quotes.freight_class import CLASS_TABLE_VERSION
from quotes.models import Quote, QuotedUnit, QuoteLineItem, TariffVersion
from quotes.pickup import PickupDateError
from quotes.services import create_quotes
from quotes.tariff_versions import create_tariff_version
from quotes.tests.quote_helpers import NOW, example_1_request, make_request, unit_fields
from quotes.tests.tariff_fixture import TARIFFS


def D(value: str) -> Decimal:
    return Decimal(value)


def nothing_saved(test):
    test.assertEqual(Quote.objects.count(), 0)
    test.assertEqual(QuoteLineItem.objects.count(), 0)
    test.assertEqual(QuotedUnit.objects.count(), 0)


class CreateQuotesTests(TestCase):
    def test_one_call_creates_one_quote_per_carrier_in_a_fixed_order(self):
        quotes = create_quotes(example_1_request(), NOW)
        self.assertEqual([q.carrier_code for q in quotes], ["cheap", "mid", "fast"])
        self.assertEqual(Quote.objects.count(), 3)

    def test_the_mid_quote_matches_graham_worked_example_1(self):
        mid = create_quotes(example_1_request(), NOW)[1]
        self.assertEqual(
            [(i.kind, i.description, i.source, i.amount) for i in mid.line_items.all()],
            [
                ("line_haul", "Line-haul, class 55", "", D("314.16")),
                ("line_haul", "Line-haul, class 125", "", D("238.00")),
                ("fuel", "Fuel (32%)", "", D("176.69")),
                ("accessorial", "Residential delivery", "auto", D("100.00")),
                ("accessorial", "Liftgate", "requested", D("85.00")),
            ],
        )
        self.assertEqual(mid.total, D("913.85"))
        self.assertEqual(mid.transit_days, 3)
        self.assertEqual(mid.estimated_delivery_date, date(2026, 12, 3))

    def test_every_quote_agrees_with_the_pricing_rules_for_its_carrier(self):
        request = example_1_request()
        for quote in create_quotes(request, NOW):
            with self.subTest(carrier=quote.carrier_code):
                expected = pricing.price_quote(
                    TARIFFS[quote.carrier_code],
                    origin_postal_code="75002",
                    destination_postal_code="30301",
                    origin_location_type="business_dock",
                    destination_location_type="residential",
                    pickup_date=date(2026, 11, 30),
                    units=[
                        pricing.ShipmentUnit(1200, 1, "55"),
                        pricing.ShipmentUnit(400, 1, "125"),
                    ],
                    liftgate_requested=True,
                )
                self.assertEqual(quote.total, expected.price)
                self.assertEqual(
                    [(i.description, i.amount) for i in quote.line_items.all()],
                    [(i.description, i.amount) for i in expected.line_items],
                )

    def test_the_lines_of_every_quote_add_up_exactly_to_its_total(self):
        for quote in create_quotes(example_1_request(), NOW):
            with self.subTest(carrier=quote.carrier_code):
                self.assertEqual(sum(i.amount for i in quote.line_items.all()), quote.total)

    def test_line_items_keep_their_order(self):
        quote = create_quotes(example_1_request(), NOW)[1]
        self.assertEqual([i.position for i in quote.line_items.all()], [0, 1, 2, 3, 4])

    def test_the_quote_snapshots_the_versions_and_the_expiry(self):
        version = TariffVersion.current()
        for quote in create_quotes(example_1_request(), NOW):
            with self.subTest(carrier=quote.carrier_code):
                self.assertEqual(quote.tariff_version, version)
                self.assertEqual(quote.rate_table_version, "RATES-2026-1")
                self.assertEqual(quote.class_table_version, CLASS_TABLE_VERSION)
                self.assertEqual(quote.created_at, NOW)
                self.assertEqual(quote.expires_at, NOW + timedelta(days=7))

    def test_the_total_is_the_price_with_no_markup(self):
        # No broker markup in Slice 2: the stored total equals the carrier cost (sum of lines).
        quote = create_quotes(example_1_request(), NOW)[0]
        self.assertEqual(quote.total, sum(i.amount for i in quote.line_items.all()))


class PricingClassSnapshotTests(TestCase):
    def classes_used(self, request):
        quote = create_quotes(request, NOW)[1]
        return [qu.freight_class for qu in quote.quoted_units.all()]

    def test_a_supplied_class_prices_the_unit_and_is_recorded(self):
        request = make_request(units=[unit_fields(freight_class="70")])
        self.assertEqual(self.classes_used(request), ["70"])

    def test_the_suggested_class_is_used_when_none_is_supplied(self):
        # 48 x 40 x 48 in at 1,000 lb is 1000 x 1728 / 92,160 = 18.75 lb/ft3: suggested class 70.
        request = make_request(units=[unit_fields(height_in=48, freight_class="")])
        unit = request.handling_units.get()
        self.assertEqual(unit.suggested_class, "70")
        self.assertEqual(self.classes_used(request), ["70"])

    def test_the_supplied_class_wins_when_it_disagrees_with_the_suggestion(self):
        request = make_request(units=[unit_fields(height_in=48, freight_class="85")])
        self.assertEqual(request.handling_units.get().suggested_class, "70")
        quote = create_quotes(request, NOW)[1]
        self.assertEqual(quote.line_items.first().description, "Line-haul, class 85")
        self.assertEqual([qu.freight_class for qu in quote.quoted_units.all()], ["85"])

    def test_one_quoted_unit_per_handling_unit_per_quote(self):
        request = example_1_request()
        quotes = create_quotes(request, NOW)
        for quote in quotes:
            with self.subTest(carrier=quote.carrier_code):
                self.assertEqual(
                    [qu.freight_class for qu in quote.quoted_units.all()], ["55", "125"]
                )


class DensityToPriceTests(TestCase):
    def test_a_denser_shipment_gets_a_lower_class_and_a_lower_price_than_a_bulky_one(self):
        # Same weight, same lane, no class supplied, so the class comes from the density.
        # 1,000 lb in 48 x 40 x 20 in is 45 lb/ft3 (class 55); in 48 x 40 x 72 in it is 12.5
        # lb/ft3 (class 85).
        dense = make_request(units=[unit_fields(height_in=20, freight_class="")])
        bulky = make_request(units=[unit_fields(height_in=72, freight_class="")])
        self.assertEqual(dense.handling_units.get().suggested_class, "55")
        self.assertEqual(bulky.handling_units.get().suggested_class, "85")
        for index, carrier in enumerate(("cheap", "mid", "fast")):
            with self.subTest(carrier=carrier):
                dense_quote = create_quotes(dense, NOW)[index]
                bulky_quote = create_quotes(bulky, NOW)[index]
                self.assertLess(dense_quote.total, bulky_quote.total)
                self.assertLess(
                    dense_quote.line_items.first().amount, bulky_quote.line_items.first().amount
                )


class AllOrNothingTests(TestCase):
    def test_if_a_carrier_calculation_fails_no_quote_is_saved(self):
        request = example_1_request()
        real = pricing.price_quote
        calls = []

        def fail_on_the_third(*args, **kwargs):
            calls.append(1)
            if len(calls) == 3:
                raise RuntimeError("carrier failure")
            return real(*args, **kwargs)

        with (
            mock.patch("quotes.services.price_quote", side_effect=fail_on_the_third),
            self.assertRaises(RuntimeError),
        ):
            create_quotes(request, NOW)
        self.assertEqual(len(calls), 3)  # two quotes had been saved before the failure
        nothing_saved(self)

    def test_a_second_call_creates_three_new_quotes_and_leaves_the_first_three_unchanged(self):
        request = example_1_request()
        first = create_quotes(request, NOW)
        snapshot = [
            (q.pk, q.total, q.created_at, q.expires_at, q.rate_table_version,
             [(i.description, i.amount) for i in q.line_items.all()])
            for q in first
        ]  # fmt: skip
        second = create_quotes(request, NOW + timedelta(hours=1))
        self.assertEqual(Quote.objects.count(), 6)
        self.assertEqual(len({q.pk for q in first} & {q.pk for q in second}), 0)
        reread = [Quote.objects.get(pk=pk) for pk, *_ in snapshot]
        self.assertEqual(
            [
                (q.pk, q.total, q.created_at, q.expires_at, q.rate_table_version,
                 [(i.description, i.amount) for i in q.line_items.all()])
                for q in reread
            ],
            snapshot,
        )  # fmt: skip


class PickupDateRecheckTests(TestCase):
    def assert_not_quoted(self, request, now=NOW):
        with self.assertRaises(PickupDateError):
            create_quotes(request, now)
        nothing_saved(self)

    def test_a_pickup_date_today_is_rejected(self):
        self.assert_not_quoted(make_request(pickup_date=date(2026, 11, 25)))

    def test_a_pickup_date_in_the_past_is_rejected(self):
        self.assert_not_quoted(make_request(pickup_date=date(2026, 11, 20)))

    def test_a_weekend_pickup_date_is_rejected(self):
        self.assert_not_quoted(make_request(pickup_date=date(2026, 11, 28)))  # Saturday

    def test_today_is_the_date_in_chicago_not_utc(self):
        # 03:00 UTC on 1 Dec is 21:00 on 30 Nov in Chicago, so Tuesday 1 Dec is still tomorrow.
        late_evening = datetime(2026, 12, 1, 3, 0, tzinfo=UTC)
        quotes = create_quotes(make_request(pickup_date=date(2026, 12, 1)), late_evening)
        self.assertEqual(len(quotes), 3)

    def test_the_next_business_day_is_accepted(self):
        quotes = create_quotes(make_request(pickup_date=date(2026, 11, 26)), NOW)
        self.assertEqual(len(quotes), 3)


class NewTariffVersionTests(TestCase):
    def test_new_quotes_use_the_new_rates_and_label(self):
        create_tariff_version(
            "RATES-2026-2",
            {"mid": {"fees": {"liftgate": "90.00"}}},
            created_at=NOW - timedelta(minutes=1) + timedelta(days=3650),
        )
        mid = create_quotes(example_1_request(), NOW)[1]
        self.assertEqual(mid.rate_table_version, "RATES-2026-2")
        # Example 1 with a $90 liftgate instead of $85: 913.85 + 5.00.
        self.assertEqual(mid.total, D("918.85"))
