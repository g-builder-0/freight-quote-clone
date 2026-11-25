"""Tests for POST /api/price-preview/ (Slice 5 backend change 4).

The cases are the approved worked examples in docs/slices/slice_05_price_preview.md. Amounts marked
G there are Graham's hand-calculated values; the others were worked out from the tariff table.
"""

from decimal import Decimal
from unittest import mock

from rest_framework.test import APITestCase

from quotes.models import (
    Booking,
    HandlingUnit,
    Quote,
    QuotedUnit,
    QuoteLineItem,
    QuoteRequest,
    TariffVersion,
)
from quotes.services import create_quotes
from quotes.tests.quote_helpers import NOW, example_1_request, make_request, unit_fields
from quotes.tests.test_booking_api import example_3_request, example_5_request

URL = "/api/price-preview/"
NOTE = "Estimate only. Your final price is set when you request quotes."
CARRIERS = [
    {"code": "cheap", "name": "Cheap and slow"},
    {"code": "mid", "name": "Mid"},
    {"code": "fast", "name": "Fast and pricey"},
]


def unit(weight_lb, freight_class=None, quantity=1, length_in=48, width_in=40, height_in=40):
    body = {
        "quantity": quantity,
        "length_in": length_in,
        "width_in": width_in,
        "height_in": height_in,
        "weight_lb": weight_lb,
    }
    if freight_class is not None:
        body["freight_class"] = freight_class
    return body


def body_example_1(**overrides):
    body = {
        "origin_postal_code": "75002",
        "origin_location_type": "business_dock",
        "destination_postal_code": "30301",
        "destination_location_type": "residential",
        "liftgate_requested": True,
        "appointment_requested": False,
        "handling_units": [unit(1200, "55"), unit(400, "125")],
    }
    body.update(overrides)
    return body


def body_dallas(units, **overrides):
    body = {
        "origin_postal_code": "75002",
        "origin_location_type": "business_dock",
        "destination_postal_code": "75201",
        "destination_location_type": "business_dock",
        "handling_units": units,
    }
    body.update(overrides)
    return body


def body_for(quote_request):
    """The preview body that matches a saved quote request (price inputs only)."""
    return {
        "origin_postal_code": quote_request.origin_postal_code,
        "origin_location_type": quote_request.origin_location_type,
        "destination_postal_code": quote_request.destination_postal_code,
        "destination_location_type": quote_request.destination_location_type,
        "liftgate_requested": quote_request.liftgate_requested,
        "appointment_requested": quote_request.appointment_requested,
        "handling_units": [
            unit(u.weight_lb, u.freight_class or None, u.quantity, u.length_in, u.width_in,
                 u.height_in)
            for u in quote_request.handling_units.all()
        ],
    }  # fmt: skip


def line(kind, description, amount, source="", reason=""):
    return {
        "kind": kind,
        "description": description,
        "source": source,
        "reason": reason,
        "amount": amount,
    }


class PreviewBase(APITestCase):
    def post(self, body):
        return self.client.post(URL, body, format="json")

    def prices(self, body):
        response = self.post(body)
        self.assertEqual(response.status_code, 200, response.data)
        return response.json()["prices"]

    def assert_totals(self, body, totals, days=None):
        prices = self.prices(body)
        self.assertEqual([p["carrier"] for p in prices], CARRIERS)
        self.assertEqual([p["total"] for p in prices], totals)
        if days is not None:
            self.assertEqual([p["transit_days"] for p in prices], days)
        return prices


class Case1Tests(PreviewBase):
    def test_example_1_inputs_return_three_prices_with_their_line_items(self):
        prices = self.assert_totals(body_example_1(), ["773.62", "913.85", "1085.04"], [4, 3, 2])
        auto = ("auto", "residential delivery address")
        requested = ("requested", "requested by shipper")
        expected = [
            [("55", "277.20"), ("125", "210.00"), ("28", "136.42"), ("85.00",), ("65.00",)],
            [("55", "314.16"), ("125", "238.00"), ("32", "176.69"), ("100.00",), ("85.00",)],
            [("55", "360.36"), ("125", "273.00"), ("35", "221.68"), ("120.00",), ("110.00",)],
        ]
        for price, amounts in zip(prices, expected, strict=True):
            self.assertEqual(
                price["line_items"],
                [
                    line("line_haul", "Line-haul, class 55", amounts[0][1]),
                    line("line_haul", "Line-haul, class 125", amounts[1][1]),
                    line("fuel", f"Fuel ({amounts[2][0]}%)", amounts[2][1]),
                    line("accessorial", "Residential delivery", amounts[3][0], *auto),
                    line("accessorial", "Liftgate", amounts[4][0], *requested),
                ],
            )

    def test_the_response_has_the_note_and_nothing_about_a_quote(self):
        response = self.post(body_example_1())
        body = response.json()
        self.assertEqual(list(body), ["note", "prices"])
        self.assertEqual(body["note"], NOTE)
        for price in body["prices"]:
            self.assertEqual(list(price), ["carrier", "total", "transit_days", "line_items"])

    def test_money_is_a_string_and_the_lines_add_up_to_the_total(self):
        for price in self.prices(body_example_1()):
            self.assertIsInstance(price["total"], str)
            self.assertEqual(
                sum(Decimal(i["amount"]) for i in price["line_items"]), Decimal(price["total"])
            )


class Case2Tests(PreviewBase):
    def test_the_minimum_charge_shows_as_one_line(self):
        body = body_dallas([unit(150, "100")])
        prices = self.assert_totals(body, ["96.00", "118.80", "148.50"], [2, 1, 1])
        expected = [("75.00", "28", "21.00"), ("90.00", "32", "28.80"), ("110.00", "35", "38.50")]
        for price, (minimum, fuel_percent, fuel) in zip(prices, expected, strict=True):
            self.assertEqual(
                price["line_items"],
                [
                    line("line_haul", "Line-haul (minimum applied)", minimum),
                    line("fuel", f"Fuel ({fuel_percent}%)", fuel),
                ],
            )


class Case3Tests(PreviewBase):
    """A 200 lb pallet of 48 x 40 x 40 in has density 4.5 and suggested class 175."""

    SUGGESTED = ["188.16", "221.76", "264.60"]

    def test_a_blank_class_is_priced_with_the_suggested_class(self):
        prices = self.assert_totals(body_dallas([unit(200)]), self.SUGGESTED)
        self.assertEqual(
            prices[0]["line_items"][0], line("line_haul", "Line-haul, class 175", "147.00")
        )
        self.assertEqual(prices[1]["line_items"][0]["amount"], "168.00")
        self.assertEqual(prices[2]["line_items"][0]["amount"], "196.00")
        self.assertEqual(
            [p["line_items"][1]["amount"] for p in prices], ["41.16", "53.76", "68.60"]
        )

    def test_an_empty_class_text_is_also_blank(self):
        self.assert_totals(body_dallas([unit(200, "")]), self.SUGGESTED)

    def test_the_suggested_class_given_explicitly_prices_the_same(self):
        self.assert_totals(body_dallas([unit(200, "175")]), self.SUGGESTED)

    def test_the_shippers_class_wins_over_the_suggested_one(self):
        self.assert_totals(body_dallas([unit(200, "100")]), ["107.52", "126.72", "151.20"])


class Case4Tests(PreviewBase):
    """The preview cannot disagree with a real quote for the same inputs."""

    def assert_matches_real_quotes(self, quote_request):
        real = create_quotes(quote_request, NOW)
        preview = self.prices(body_for(quote_request))
        self.assertEqual(len(preview), len(real))
        for price, quote in zip(preview, real, strict=True):
            self.assertEqual(
                price["carrier"], {"code": quote.carrier_code, "name": quote.carrier_name}
            )
            self.assertEqual(price["total"], str(quote.total))
            self.assertEqual(price["transit_days"], quote.transit_days)
            self.assertEqual(
                [(i["kind"], i["description"], i["source"], i["reason"], i["amount"])
                 for i in price["line_items"]],
                [(i.kind, i.description, i.source, i.reason, str(i.amount))
                 for i in quote.line_items.all()],
            )  # fmt: skip
        return preview

    def test_example_1(self):
        self.assert_matches_real_quotes(example_1_request())

    def test_example_3_and_the_fast_carrier_is_grahams_value(self):
        preview = self.assert_matches_real_quotes(example_3_request())
        self.assertEqual(preview[2]["total"], "1605.36")

    def test_example_5_and_the_cheap_carrier_is_grahams_value(self):
        preview = self.assert_matches_real_quotes(example_5_request())
        self.assertEqual(preview[0]["total"], "629.76")

    def test_a_blank_class_matches_a_real_quote_too(self):
        request = make_request(units=[unit_fields(weight_lb=200, freight_class="")])
        self.assert_matches_real_quotes(request)


class Case5Tests(PreviewBase):
    MODELS = (QuoteRequest, HandlingUnit, Quote, QuoteLineItem, QuotedUnit, Booking)

    def counts(self):
        return [model.objects.count() for model in self.MODELS]

    def test_a_preview_saves_nothing(self):
        before = self.counts()
        self.assertEqual(self.post(body_example_1()).status_code, 200)
        self.assertEqual(self.counts(), before)

    def test_a_rejected_preview_saves_nothing_either(self):
        before = self.counts()
        self.assertEqual(self.post(body_example_1(handling_units=[])).status_code, 400)
        self.assertEqual(self.counts(), before)


class Case6Tests(PreviewBase):
    """Bad input returns 400 and names the field, with the quote request's own messages."""

    def assert_rejected(self, body, expected):
        response = self.post(body)
        self.assertEqual(response.status_code, 400, response.data)
        self.assertEqual(response.json(), expected)

    def test_6a_the_second_unit_has_no_weight(self):
        second = unit(400, "125")
        del second["weight_lb"]
        body = body_example_1(handling_units=[unit(1200, "55"), second])
        self.assert_rejected(
            body, {"handling_units": [{}, {"weight_lb": ["This field is required."]}]}
        )

    def test_6b_a_short_zip_code(self):
        self.assert_rejected(
            body_example_1(destination_postal_code="7520"),
            {"destination_postal_code": [
                "Enter a 5-digit ZIP code, with an optional +4 (12345 or 12345-6789)."]},
        )  # fmt: skip

    def test_6c_an_unknown_location_type(self):
        self.assert_rejected(
            body_example_1(destination_location_type="bogus"),
            {"destination_location_type": ['"bogus" is not a valid choice.']},
        )

    def test_6d_an_empty_list_of_units(self):
        self.assert_rejected(
            body_example_1(handling_units=[]),
            {"handling_units": {"non_field_errors": ["This list may not be empty."]}},
        )

    def test_6e_a_missing_origin_zip_code(self):
        body = body_example_1()
        del body["origin_postal_code"]
        self.assert_rejected(body, {"origin_postal_code": ["This field is required."]})

    def test_6f_a_unit_over_the_weight_limit(self):
        response = self.post(body_example_1(handling_units=[unit(4001, "55")]))
        self.assertEqual(response.status_code, 400)
        self.assertEqual(list(response.json()), ["handling_units"])
        self.assertEqual(list(response.json()["handling_units"][0]), ["weight_lb"])

    def test_every_required_field_is_named_when_missing(self):
        response = self.post({})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            sorted(response.json()),
            [
                "destination_location_type",
                "destination_postal_code",
                "handling_units",
                "origin_location_type",
                "origin_postal_code",
            ],
        )

    def test_the_flags_default_to_false(self):
        body = body_example_1()
        del body["liftgate_requested"], body["appointment_requested"]
        for price in self.prices(body):
            self.assertNotIn("Liftgate", [i["description"] for i in price["line_items"]])
            self.assertNotIn("Appointment", [i["description"] for i in price["line_items"]])


class Case7Tests(PreviewBase):
    def test_no_current_tariff_is_a_503_with_the_quote_creation_message(self):
        # Tariff rows are immutable and protected, so "no tariff" is simulated at the lookup.
        with mock.patch.object(TariffVersion, "current", return_value=None):
            response = self.post(body_example_1())
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {"detail": "There is no current tariff version."})


class Case8Tests(PreviewBase):
    def test_only_post_is_allowed(self):
        for method in (self.client.get, self.client.put, self.client.patch, self.client.delete):
            with self.subTest(method=method.__name__):
                self.assertEqual(method(URL).status_code, 405)

    def test_no_sign_in_is_needed(self):
        self.assertEqual(self.post(body_example_1()).status_code, 200)

    def test_fields_the_endpoint_does_not_use_are_ignored(self):
        extra = body_example_1(pickup_date="2026-11-30", origin_street="1 A St", bogus=1)
        extra["handling_units"][0]["commodity_description"] = "Widgets"
        self.assertEqual(self.prices(extra), self.prices(body_example_1()))
