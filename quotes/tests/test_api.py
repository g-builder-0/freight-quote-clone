from datetime import UTC, date, datetime
from unittest import mock

from django.test import SimpleTestCase
from rest_framework.test import APITestCase

from quotes.models import HandlingUnit, LocationType, QuoteRequest, UnitType
from quotes.serializers import get_today

LIST_URL = "/api/quote-requests/"

# Wednesday 11 November 2026 is "today" in these tests (the real clock is never read), so
# Thursday 12th and Monday 16th are valid pickup dates and Saturday 14th and Sunday 15th are not.
TODAY = date(2026, 11, 11)
VALID_PICKUP = "2026-11-16"


def unit_payload(**overrides):
    unit = {
        "unit_type": "pallet",
        "quantity": 1,
        "length_in": 60,
        "width_in": 40,
        "height_in": 30,
        "weight_lb": 400,
        "stackable": True,
        "commodity_description": "Boxed widgets",
    }
    unit.update(overrides)
    return unit


def request_payload(units=None, **overrides):
    payload = {
        "origin_street": "100 Main St",
        "origin_city": "Allen",
        "origin_state": "TX",
        "origin_postal_code": "75002",
        "origin_location_type": "business_dock",
        "destination_street": "200 Oak Ave",
        "destination_city": "Chicago",
        "destination_state": "IL",
        "destination_postal_code": "60601-1234",
        "destination_location_type": "residential",
        "pickup_date": VALID_PICKUP,
        "handling_units": [unit_payload()] if units is None else units,
    }
    payload.update(overrides)
    return payload


class QuoteApiTestCase(APITestCase):
    """Base class: fixes "today" at TODAY and offers small helpers."""

    def setUp(self):
        patcher = mock.patch("quotes.serializers.get_today", return_value=TODAY)
        patcher.start()
        self.addCleanup(patcher.stop)

    def post(self, payload):
        return self.client.post(LIST_URL, payload, format="json")

    def assert_created(self, payload):
        response = self.post(payload)
        self.assertEqual(response.status_code, 201, response.data)
        return response.json()

    def assert_rejected(self, payload, *, field=None, unit_field=None, message=None):
        """Expect a 400 that names the offending field, and nothing saved."""
        response = self.post(payload)
        self.assertEqual(response.status_code, 400, response.data)
        if unit_field is not None:
            errors = response.data["handling_units"][0]
            self.assertIn(unit_field, errors)
            text = str(errors[unit_field])
        else:
            self.assertIn(field, response.data)
            text = str(response.data[field])
        if message is not None:
            self.assertIn(message, text)
        self.assertEqual(QuoteRequest.objects.count(), 0)
        self.assertEqual(HandlingUnit.objects.count(), 0)


class WorkedExampleApiTests(QuoteApiTestCase):
    # Graham's hand-calculated examples (Slice 1 spec). Density is shown to 2 decimals as a string.
    # (case, weight_lb, length_in, width_in, height_in, density as shown, expected class)
    EXAMPLES = [
        ("1 ordinary mid-density pallet", 400, 60, 40, 30, "9.60", "100"),
        ("2 very dense unit", 1500, 52, 36, 28, "49.45", "55"),
        ("3 light bulky unit", 250, 41, 36, 72, "4.07", "175"),
        ("4 exact boundary 35.0", 2240, 48, 48, 48, "35.00", "55"),
        ("5 just under boundary", 2239, 48, 48, 48, "34.98", "60"),
    ]

    def test_worked_example_payloads_return_the_expected_class_and_density(self):
        for name, weight, length, width, height, density, expected_class in self.EXAMPLES:
            with self.subTest(name):
                unit = unit_payload(
                    weight_lb=weight, length_in=length, width_in=width, height_in=height
                )
                data = self.assert_created(request_payload(units=[unit]))
                returned = data["handling_units"][0]
                self.assertEqual(returned["suggested_class"], expected_class)
                self.assertEqual(returned["density"], density)

    def test_density_is_a_json_string(self):
        data = self.assert_created(request_payload())
        self.assertIsInstance(data["handling_units"][0]["density"], str)

    def test_quantity_does_not_change_density_or_class(self):
        data = self.assert_created(request_payload(units=[unit_payload(quantity=10)]))
        returned = data["handling_units"][0]
        self.assertEqual(returned["density"], "9.60")
        self.assertEqual(returned["suggested_class"], "100")

    def test_each_unit_gets_its_own_density_and_class(self):
        units = [
            unit_payload(),  # worked example 1: class 100
            unit_payload(weight_lb=1500, length_in=52, width_in=36, height_in=28),  # example 2
        ]
        data = self.assert_created(request_payload(units=units))
        self.assertEqual(
            [unit["suggested_class"] for unit in data["handling_units"]], ["100", "55"]
        )

    def test_display_rounding_never_changes_the_class(self):
        # Agent-derived (NOT one of Graham's hand examples), arithmetic checked by hand:
        # 144 x 96 x 62 in = 857,088 cubic inches, and 8 lb per cubic foot is 3,968 lb.
        # 3,967 lb is 7.9979... lb/ft3: shown as "8.00" but still class 125 (below the 8 boundary).
        # 3,968 lb is exactly 8: class 100.
        size = {"length_in": 144, "width_in": 96, "height_in": 62}
        under = self.assert_created(request_payload(units=[unit_payload(weight_lb=3967, **size)]))
        exact = self.assert_created(request_payload(units=[unit_payload(weight_lb=3968, **size)]))
        self.assertEqual(under["handling_units"][0]["density"], "8.00")
        self.assertEqual(under["handling_units"][0]["suggested_class"], "125")
        self.assertEqual(exact["handling_units"][0]["density"], "8.00")
        self.assertEqual(exact["handling_units"][0]["suggested_class"], "100")


class HandlingUnitValidationTests(QuoteApiTestCase):
    def test_at_least_one_handling_unit_is_required(self):
        self.assert_rejected(request_payload(units=[]), field="handling_units", message="empty")

    def test_missing_handling_units_is_rejected(self):
        payload = request_payload()
        del payload["handling_units"]
        self.assert_rejected(payload, field="handling_units")

    def test_weight_dimensions_and_quantity_must_be_positive_whole_numbers(self):
        bad_values = {
            "weight_lb": [0, -5, 400.5, "abc"],
            "length_in": [0, -1, 41.5],
            "width_in": [0, -1, 36.5],
            "height_in": [0, -1, 30.5],
            "quantity": [0, -1, 2.5],
        }
        for field, values in bad_values.items():
            for value in values:
                with self.subTest(field=field, value=value):
                    self.assert_rejected(
                        request_payload(units=[unit_payload(**{field: value})]),
                        unit_field=field,
                    )

    def test_values_above_the_hard_limits_are_rejected(self):
        for field, too_big in (
            ("length_in", 145),
            ("width_in", 97),
            ("height_in", 97),
            ("weight_lb", 4001),
        ):
            with self.subTest(field=field):
                self.assert_rejected(
                    request_payload(units=[unit_payload(**{field: too_big})]),
                    unit_field=field,
                    message="less than or equal to",
                )

    def test_values_exactly_at_the_hard_limits_are_accepted(self):
        unit = unit_payload(length_in=144, width_in=96, height_in=96, weight_lb=4000)
        self.assert_created(request_payload(units=[unit]))

    def test_smallest_allowed_values_are_accepted(self):
        unit = unit_payload(length_in=1, width_in=1, height_in=1, weight_lb=1, quantity=1)
        self.assert_created(request_payload(units=[unit]))

    def test_unit_type_must_be_one_of_the_four(self):
        for value in ("box", "", "PALLET"):
            with self.subTest(value=value):
                self.assert_rejected(
                    request_payload(units=[unit_payload(unit_type=value)]), unit_field="unit_type"
                )
        for value in UnitType.values:
            with self.subTest(accepted=value):
                self.assertEqual(
                    self.assert_created(request_payload(units=[unit_payload(unit_type=value)]))[
                        "handling_units"
                    ][0]["unit_type"],
                    value,
                )
                QuoteRequest.objects.all().delete()

    def test_commodity_description_is_required(self):
        unit = unit_payload()
        del unit["commodity_description"]
        self.assert_rejected(request_payload(units=[unit]), unit_field="commodity_description")
        self.assert_rejected(
            request_payload(units=[unit_payload(commodity_description="")]),
            unit_field="commodity_description",
        )

    def test_stackable_defaults_to_false(self):
        unit = unit_payload()
        del unit["stackable"]
        data = self.assert_created(request_payload(units=[unit]))
        self.assertFalse(data["handling_units"][0]["stackable"])


class FreightClassAndNmfcCodeTests(QuoteApiTestCase):
    def test_supplied_class_must_be_one_of_the_18_standard_classes(self):
        for value in ("56", "5", "abc", "1000", "77", "60.0"):
            with self.subTest(value=value):
                self.assert_rejected(
                    request_payload(units=[unit_payload(freight_class=value)]),
                    unit_field="freight_class",
                )

    def test_every_standard_class_is_accepted_and_stored_as_given(self):
        classes = "50 55 60 65 70 77.5 85 92.5 100 110 125 150 175 200 250 300 400 500".split()
        for value in classes:
            with self.subTest(value=value):
                data = self.assert_created(
                    request_payload(units=[unit_payload(freight_class=value)])
                )
                self.assertEqual(data["handling_units"][0]["freight_class"], value)
                QuoteRequest.objects.all().delete()

    def test_numeric_class_is_accepted(self):
        data = self.assert_created(request_payload(units=[unit_payload(freight_class=55)]))
        self.assertEqual(data["handling_units"][0]["freight_class"], "55")

    def test_supplied_class_is_returned_alongside_the_suggestion_and_never_overwritten(self):
        # Worked example 1 is suggested class 100; the shipper says 110.
        data = self.assert_created(request_payload(units=[unit_payload(freight_class="110")]))
        returned = data["handling_units"][0]
        self.assertEqual(returned["freight_class"], "110")
        self.assertEqual(returned["suggested_class"], "100")

    def test_class_and_nmfc_code_are_optional(self):
        omitted = self.assert_created(request_payload())["handling_units"][0]
        self.assertEqual(omitted["freight_class"], "")
        self.assertEqual(omitted["nmfc_code"], "")
        blank = self.assert_created(
            request_payload(units=[unit_payload(freight_class="", nmfc_code="")])
        )["handling_units"][0]
        self.assertEqual(blank["freight_class"], "")
        self.assertEqual(blank["nmfc_code"], "")

    def test_valid_nmfc_codes_are_accepted(self):
        for value in ("153760", "61780", "1234", "153760-03", "153760-3"):
            with self.subTest(value=value):
                data = self.assert_created(request_payload(units=[unit_payload(nmfc_code=value)]))
                self.assertEqual(data["handling_units"][0]["nmfc_code"], value)
                QuoteRequest.objects.all().delete()

    def test_invalid_nmfc_codes_are_rejected(self):
        for value in ("abc", "12", "1234567", "153760-", "153760 sub 3", "NMFC 153760"):
            with self.subTest(value=value):
                self.assert_rejected(
                    request_payload(units=[unit_payload(nmfc_code=value)]),
                    unit_field="nmfc_code",
                )


class AddressAndLocationValidationTests(QuoteApiTestCase):
    PREFIXES = ("origin", "destination")

    def test_state_must_be_a_two_letter_us_state_or_dc(self):
        for prefix in self.PREFIXES:
            for value in ("tx", "ZZ", "Texas", "PR", ""):
                with self.subTest(prefix=prefix, value=value):
                    self.assert_rejected(
                        request_payload(**{f"{prefix}_state": value}), field=f"{prefix}_state"
                    )

    def test_dc_and_other_states_are_accepted(self):
        data = self.assert_created(request_payload(origin_state="DC", destination_state="WY"))
        self.assertEqual(data["origin_state"], "DC")
        self.assertEqual(data["destination_state"], "WY")

    def test_postal_code_must_be_five_digits_with_optional_plus_four(self):
        for prefix in self.PREFIXES:
            for value in ("7500", "750022", "75002-12", "abcde", ""):
                with self.subTest(prefix=prefix, value=value):
                    self.assert_rejected(
                        request_payload(**{f"{prefix}_postal_code": value}),
                        field=f"{prefix}_postal_code",
                    )

    def test_street_and_city_are_required(self):
        for prefix in self.PREFIXES:
            for part in ("street", "city"):
                with self.subTest(prefix=prefix, part=part):
                    payload = request_payload()
                    del payload[f"{prefix}_{part}"]
                    self.assert_rejected(payload, field=f"{prefix}_{part}")
                    self.assert_rejected(
                        request_payload(**{f"{prefix}_{part}": ""}), field=f"{prefix}_{part}"
                    )

    def test_location_type_must_be_one_of_the_four(self):
        for prefix in self.PREFIXES:
            with self.subTest(prefix=prefix):
                self.assert_rejected(
                    request_payload(**{f"{prefix}_location_type": "warehouse"}),
                    field=f"{prefix}_location_type",
                )
        for value in LocationType.values:
            with self.subTest(accepted=value):
                data = self.assert_created(request_payload(origin_location_type=value))
                self.assertEqual(data["origin_location_type"], value)
                QuoteRequest.objects.all().delete()


class PickupDateTests(QuoteApiTestCase):
    def test_weekday_after_today_is_accepted(self):
        for value in ("2026-11-12", "2026-11-13", "2026-11-16"):
            with self.subTest(value=value):
                self.assert_created(request_payload(pickup_date=value))
                QuoteRequest.objects.all().delete()

    def test_weekend_is_rejected(self):
        for value in ("2026-11-14", "2026-11-15"):
            with self.subTest(value=value):
                self.assert_rejected(
                    request_payload(pickup_date=value), field="pickup_date", message="business day"
                )

    def test_today_and_past_dates_are_rejected(self):
        for value in ("2026-11-11", "2026-11-10", "2026-11-07", "2025-01-06"):
            with self.subTest(value=value):
                self.assert_rejected(
                    request_payload(pickup_date=value), field="pickup_date", message="after today"
                )

    def test_pickup_date_is_required_and_must_be_a_date(self):
        payload = request_payload()
        del payload["pickup_date"]
        self.assert_rejected(payload, field="pickup_date")
        self.assert_rejected(request_payload(pickup_date="11/16/2026"), field="pickup_date")


class PickupTimeZoneTests(APITestCase):
    """ "Today" is the date in America/Chicago, even when it is already tomorrow in UTC."""

    def post_pickup(self, pickup_date):
        return self.client.post(LIST_URL, request_payload(pickup_date=pickup_date), format="json")

    def test_today_is_chicagos_date_not_utc(self):
        # 03:00 UTC on 12 Nov is 21:00 on 11 Nov in Chicago, so Chicago's "today" is the 11th.
        late_evening_chicago = datetime(2026, 11, 12, 3, 0, tzinfo=UTC)
        with mock.patch("django.utils.timezone.now", return_value=late_evening_chicago):
            self.assertEqual(self.post_pickup("2026-11-12").status_code, 201)

    def test_pickup_on_chicagos_today_is_rejected(self):
        # 07:00 UTC on 12 Nov is 01:00 on 12 Nov in Chicago, so the 12th is now "today".
        early_morning_chicago = datetime(2026, 11, 12, 7, 0, tzinfo=UTC)
        with mock.patch("django.utils.timezone.now", return_value=early_morning_chicago):
            self.assertEqual(self.post_pickup("2026-11-12").status_code, 400)


class GetTodayTests(SimpleTestCase):
    def test_get_today_uses_the_america_chicago_date(self):
        evening = datetime(2026, 11, 12, 3, 0, tzinfo=UTC)
        morning = datetime(2026, 11, 12, 7, 0, tzinfo=UTC)
        with mock.patch("django.utils.timezone.now", return_value=evening):
            self.assertEqual(get_today(), date(2026, 11, 11))
        with mock.patch("django.utils.timezone.now", return_value=morning):
            self.assertEqual(get_today(), date(2026, 11, 12))


class CreateAndRetrieveTests(QuoteApiTestCase):
    def test_create_returns_201_with_ids_and_nested_units(self):
        data = self.assert_created(request_payload())
        self.assertIn("id", data)
        self.assertIn("created_at", data)
        self.assertEqual(len(data["handling_units"]), 1)
        self.assertIn("id", data["handling_units"][0])
        self.assertEqual(QuoteRequest.objects.count(), 1)
        self.assertEqual(HandlingUnit.objects.count(), 1)

    def test_create_then_fetch_returns_the_same_request(self):
        created = self.assert_created(
            request_payload(units=[unit_payload(freight_class="110", nmfc_code="153760-03")])
        )
        response = self.client.get(f"{LIST_URL}{created['id']}/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), created)

    def test_no_credentials_are_needed(self):
        # Slice 1 has no authentication (that arrives in Slice 5).
        self.assertEqual(self.post(request_payload()).status_code, 201)
        self.assertEqual(self.client.get(LIST_URL).status_code, 200)

    def test_fetching_a_missing_request_is_404(self):
        self.assertEqual(self.client.get(f"{LIST_URL}999999/").status_code, 404)

    def test_a_failed_create_saves_nothing(self):
        units = [unit_payload(), unit_payload(weight_lb=0)]
        self.assert_rejected(request_payload(units=units), field="handling_units")


class ListTests(APITestCase):
    def make_requests(self, count):
        created = []
        for number in range(count):
            quote_request = QuoteRequest.objects.create(
                origin_street=f"{number} Main St",
                origin_city="Allen",
                origin_state="TX",
                origin_postal_code="75002",
                origin_location_type=LocationType.BUSINESS_DOCK,
                destination_street="200 Oak Ave",
                destination_city="Chicago",
                destination_state="IL",
                destination_postal_code="60601",
                destination_location_type=LocationType.RESIDENTIAL,
                pickup_date="2026-11-16",
            )
            HandlingUnit.objects.create(
                quote_request=quote_request,
                unit_type=UnitType.PALLET,
                quantity=1,
                length_in=60,
                width_in=40,
                height_in=30,
                weight_lb=400,
                commodity_description="Boxed widgets",
            )
            created.append(quote_request)
        return created

    def test_empty_list_has_the_paginated_shape(self):
        data = self.client.get(LIST_URL).json()
        self.assertEqual(data, {"count": 0, "next": None, "previous": None, "results": []})

    def test_list_is_paginated_with_page_size_20_and_newest_first(self):
        created = self.make_requests(25)
        first_page = self.client.get(LIST_URL).json()
        self.assertEqual(set(first_page), {"count", "next", "previous", "results"})
        self.assertEqual(first_page["count"], 25)
        self.assertEqual(len(first_page["results"]), 20)
        self.assertIn("page=2", first_page["next"])
        self.assertIsNone(first_page["previous"])

        second_page = self.client.get(LIST_URL, {"page": 2}).json()
        self.assertEqual(len(second_page["results"]), 5)
        self.assertIsNone(second_page["next"])
        self.assertIsNotNone(second_page["previous"])

        listed_ids = [item["id"] for item in first_page["results"] + second_page["results"]]
        newest_first = [quote_request.id for quote_request in reversed(created)]
        self.assertEqual(listed_ids, newest_first)

    def test_list_items_include_nested_units_with_density_and_class(self):
        self.make_requests(1)
        item = self.client.get(LIST_URL).json()["results"][0]
        unit = item["handling_units"][0]
        self.assertEqual(unit["density"], "9.60")
        self.assertEqual(unit["suggested_class"], "100")


class UnsupportedMethodTests(QuoteApiTestCase):
    def test_update_and_delete_are_not_allowed(self):
        created = self.assert_created(request_payload())
        detail_url = f"{LIST_URL}{created['id']}/"
        for method in ("put", "patch", "delete"):
            with self.subTest(method=method, url="detail"):
                response = getattr(self.client, method)(
                    detail_url, request_payload(), format="json"
                )
                self.assertEqual(response.status_code, 405)
        for method in ("put", "patch", "delete"):
            with self.subTest(method=method, url="list"):
                response = getattr(self.client, method)(LIST_URL, request_payload(), format="json")
                self.assertEqual(response.status_code, 405)
        self.assertEqual(QuoteRequest.objects.count(), 1)
