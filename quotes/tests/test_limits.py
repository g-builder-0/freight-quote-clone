"""Tests for GET /api/limits/ (Slice 5 backend change 3).

The expected body is Graham's approved Case 1 (docs/slices/slice_05_limits_endpoint.md). Case 3
checks that the numbers in the body are the numbers the validation really enforces.
"""

from unittest import mock

from rest_framework.test import APITestCase

from quotes import contacts, models
from quotes.models import Booking, HandlingUnit, QuoteRequest
from quotes.services import create_quotes
from quotes.tests.quote_helpers import NOW
from quotes.tests.test_booking_api import DANA, MARCUS, BookingApiBase
from quotes.tests.test_booking_service import case_1_request

LIMITS_URL = "/api/limits/"
PREVIEW_URL = "/api/class-preview/"

CASE_1_BODY = {
    "unit": {
        "weight_lb": {"min": 1, "max": 4000},
        "length_in": {"min": 1, "max": 144},
        "width_in": {"min": 1, "max": 96},
        "height_in": {"min": 1, "max": 96},
    },
    "text": {
        "special_instructions_max": 500,
        "cancel_reason_max": 200,
    },
}

UNIT_FIELDS = ("weight_lb", "length_in", "width_in", "height_in")


class LimitsCase1And2Tests(APITestCase):
    def test_case_1_the_exact_body(self):
        response = self.client.get(LIMITS_URL)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), CASE_1_BODY)

    def test_case_2_other_methods_are_not_allowed(self):
        for method in (self.client.post, self.client.put, self.client.patch, self.client.delete):
            with self.subTest(method=method.__name__):
                self.assertEqual(method(LIMITS_URL).status_code, 405)

    def test_no_sign_in_is_needed(self):
        self.assertEqual(self.client.get(LIMITS_URL).status_code, 200)

    def test_the_endpoint_stores_nothing(self):
        before = (
            QuoteRequest.objects.count(),
            HandlingUnit.objects.count(),
            Booking.objects.count(),
        )
        self.client.get(LIMITS_URL)
        after = (
            QuoteRequest.objects.count(),
            HandlingUnit.objects.count(),
            Booking.objects.count(),
        )
        self.assertEqual(before, after)


class LimitsMatchTheUnitRulesTests(APITestCase):
    """Case 3: each unit limit in the body is accepted, and one past it is rejected."""

    def preview(self, **overrides):
        body = {"weight_lb": 500, "length_in": 48, "width_in": 40, "height_in": 48}
        body.update(overrides)
        return self.client.post(PREVIEW_URL, body, format="json")

    def test_max_is_accepted_and_one_over_is_rejected(self):
        limits = self.client.get(LIMITS_URL).json()["unit"]
        for field in UNIT_FIELDS:
            top = limits[field]["max"]
            with self.subTest(field=field, value=top):
                self.assertEqual(self.preview(**{field: top}).status_code, 200)
            with self.subTest(field=field, value=top + 1):
                self.assertEqual(self.preview(**{field: top + 1}).status_code, 400)

    def test_min_is_accepted_and_one_under_is_rejected(self):
        limits = self.client.get(LIMITS_URL).json()["unit"]
        for field in UNIT_FIELDS:
            bottom = limits[field]["min"]
            with self.subTest(field=field, value=bottom):
                self.assertEqual(self.preview(**{field: bottom}).status_code, 200)
            with self.subTest(field=field, value=bottom - 1):
                self.assertEqual(self.preview(**{field: bottom - 1}).status_code, 400)


class LimitsMatchTheTextRulesTests(BookingApiBase):
    """Case 3: the instructions and cancel reason limits are the ones booking and cancel enforce."""

    def limits(self):
        return self.client.get(LIMITS_URL).json()["text"]

    def test_instructions_at_the_limit_are_accepted_and_one_more_is_rejected(self):
        limit = self.limits()["special_instructions_max"]
        exact = create_quotes(case_1_request(), NOW)[1]
        response = self.book(exact, instructions="x" * limit)
        self.assertEqual(response.status_code, 201, response.data)
        over = create_quotes(case_1_request(), NOW)[1]
        response = self.book(over, shipper=DANA, receiver=MARCUS, instructions="x" * (limit + 1))
        self.assertEqual(response.status_code, 400)
        self.assertIn("special_instructions", response.json())

    def test_a_cancel_reason_at_the_limit_is_accepted_and_one_more_is_rejected(self):
        limit = self.limits()["cancel_reason_max"]
        quote = create_quotes(case_1_request(), NOW)[1]
        booking_id = self.book(quote).json()["id"]
        too_long = self.cancel(booking_id, reason="x" * (limit + 1))
        self.assertEqual(too_long.status_code, 400)
        self.assertIn("reason", too_long.json())
        exact = self.cancel(booking_id, reason="x" * limit)
        self.assertEqual(exact.status_code, 200, exact.data)


class LimitsReadTheConstantsTests(APITestCase):
    """Case 3: the endpoint holds no numbers of its own. Patching a constant changes the answer."""

    def test_each_value_follows_its_constant(self):
        cases = (
            (models, "MAX_WEIGHT_LB", ("unit", "weight_lb", "max")),
            (models, "MAX_LENGTH_IN", ("unit", "length_in", "max")),
            (models, "MAX_WIDTH_IN", ("unit", "width_in", "max")),
            (models, "MAX_HEIGHT_IN", ("unit", "height_in", "max")),
            (models, "MIN_UNIT_VALUE", ("unit", "weight_lb", "min")),
            (models, "MIN_UNIT_VALUE", ("unit", "length_in", "min")),
            (models, "MIN_UNIT_VALUE", ("unit", "width_in", "min")),
            (models, "MIN_UNIT_VALUE", ("unit", "height_in", "min")),
            (contacts, "INSTRUCTIONS_MAX_LENGTH", ("text", "special_instructions_max")),
            (contacts, "CANCEL_REASON_MAX_LENGTH", ("text", "cancel_reason_max")),
        )
        for module, name, path in cases:
            with self.subTest(constant=name, path=path):
                with mock.patch.object(module, name, 12345):
                    body = self.client.get(LIMITS_URL).json()
                value = body
                for key in path:
                    value = value[key]
                self.assertEqual(value, 12345)
