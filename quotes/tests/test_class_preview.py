"""Tests for POST /api/class-preview/ (Slice 5 backend change 1).

The cases are Graham's approved worked examples (docs/slices/slice_05_class_preview.md): the
inputs and expected results below are copied from it, not worked out here.
"""

from rest_framework.test import APITestCase

from quotes.models import HandlingUnit, QuoteRequest
from quotes.tests.test_api import LIST_URL, TODAY, request_payload, unit_payload

PREVIEW_URL = "/api/class-preview/"


def preview_input(weight_lb, length_in, width_in, height_in):
    return {
        "weight_lb": weight_lb,
        "length_in": length_in,
        "width_in": width_in,
        "height_in": height_in,
    }


class ClassPreviewCaseTests(APITestCase):
    def post(self, body):
        return self.client.post(PREVIEW_URL, body, format="json")

    def assert_result(self, body, density, suggested_class):
        response = self.post(body)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.json(), {"density": density, "suggested_class": suggested_class})

    def test_case_1_normal_unit_density_rounds_up_for_display(self):
        self.assert_result(preview_input(500, 48, 40, 48), "9.38", "100")

    def test_case_2a_density_exactly_on_a_boundary_belongs_to_the_upper_tier(self):
        self.assert_result(preview_input(35, 12, 12, 12), "35.00", "55")

    def test_case_2b_density_just_under_the_boundary(self):
        self.assert_result(preview_input(34, 12, 12, 12), "34.00", "60")

    def test_case_3_very_light_unit(self):
        self.assert_result(preview_input(10, 48, 40, 48), "0.19", "400")

    def test_case_4_largest_allowed_unit(self):
        self.assert_result(preview_input(4000, 144, 96, 96), "5.21", "175")

    def test_density_is_a_json_string(self):
        response = self.post(preview_input(500, 48, 40, 48))
        self.assertIsInstance(response.json()["density"], str)


class ClassPreviewRejectionTests(APITestCase):
    """Case 5: each bad input is a 400 that names the failing field."""

    def post(self, body):
        return self.client.post(PREVIEW_URL, body, format="json")

    def assert_rejected(self, body, field):
        response = self.post(body)
        self.assertEqual(response.status_code, 400, response.data)
        self.assertEqual(list(response.json()), [field])

    def test_case_5a_weight_zero(self):
        self.assert_rejected(preview_input(0, 48, 40, 48), "weight_lb")

    def test_case_5b_weight_over_the_limit(self):
        self.assert_rejected(preview_input(4001, 48, 40, 48), "weight_lb")

    def test_case_5c_length_over_the_limit(self):
        self.assert_rejected(preview_input(500, 145, 40, 48), "length_in")

    def test_case_5d_fractional_width(self):
        self.assert_rejected(preview_input(500, 48, 40.5, 48), "width_in")

    def test_case_5e_missing_height(self):
        body = preview_input(500, 48, 40, 48)
        del body["height_in"]
        self.assert_rejected(body, "height_in")

    def test_case_5f_get_is_not_allowed(self):
        self.assertEqual(self.client.get(PREVIEW_URL).status_code, 405)

    def test_other_methods_are_not_allowed(self):
        for method in (self.client.put, self.client.patch, self.client.delete):
            with self.subTest(method=method.__name__):
                self.assertEqual(
                    method(PREVIEW_URL, preview_input(500, 48, 40, 48)).status_code, 405
                )

    def test_every_field_is_required(self):
        for field in ("weight_lb", "length_in", "width_in", "height_in"):
            with self.subTest(field=field):
                body = preview_input(500, 48, 40, 48)
                del body[field]
                self.assert_rejected(body, field)


class ClassPreviewSharesRulesTests(APITestCase):
    """The preview uses the quote request's own field rules, not a copy that can drift."""

    def test_messages_match_the_quote_request_for_the_same_bad_value(self):
        from unittest import mock

        with mock.patch("quotes.serializers.get_today", return_value=TODAY):
            for field, value in (
                ("weight_lb", 0),
                ("weight_lb", 4001),
                ("length_in", 145),
                ("width_in", 97),
                ("height_in", 97),
                ("width_in", 40.5),
            ):
                with self.subTest(field=field, value=value):
                    quote_response = self.client.post(
                        LIST_URL,
                        request_payload(units=[unit_payload(**{field: value})]),
                        format="json",
                    )
                    body = preview_input(500, 48, 40, 48)
                    body[field] = value
                    preview_response = self.client.post(PREVIEW_URL, body, format="json")
                    self.assertEqual(
                        preview_response.json()[field],
                        quote_response.json()["handling_units"][0][field],
                    )

    def test_values_exactly_at_the_limits_are_accepted(self):
        response = self.client.post(PREVIEW_URL, preview_input(4000, 144, 96, 96), format="json")
        self.assertEqual(response.status_code, 200)

    def test_smallest_allowed_values_are_accepted(self):
        response = self.client.post(PREVIEW_URL, preview_input(1, 1, 1, 1), format="json")
        self.assertEqual(response.status_code, 200)


class ClassPreviewSavesNothingTests(APITestCase):
    def counts(self):
        return QuoteRequest.objects.count(), HandlingUnit.objects.count()

    def test_a_successful_call_saves_nothing(self):
        before = self.counts()
        response = self.client.post(PREVIEW_URL, preview_input(500, 48, 40, 48), format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.counts(), before)

    def test_a_failed_call_saves_nothing(self):
        before = self.counts()
        response = self.client.post(PREVIEW_URL, preview_input(0, 48, 40, 48), format="json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.counts(), before)

    def test_counts_are_unchanged_when_data_already_exists(self):
        request = QuoteRequest.objects.create(
            origin_street="100 Main St",
            origin_city="Allen",
            origin_state="TX",
            origin_postal_code="75002",
            origin_location_type="business_dock",
            destination_street="200 Oak Ave",
            destination_city="Chicago",
            destination_state="IL",
            destination_postal_code="60601",
            destination_location_type="residential",
            pickup_date=TODAY,
        )
        HandlingUnit.objects.create(
            quote_request=request,
            unit_type="pallet",
            quantity=1,
            length_in=48,
            width_in=40,
            height_in=48,
            weight_lb=500,
            commodity_description="Boxed widgets",
        )
        before = self.counts()
        self.client.post(PREVIEW_URL, preview_input(500, 48, 40, 48), format="json")
        self.assertEqual(self.counts(), before)
