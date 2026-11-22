from decimal import Decimal

from django.test import SimpleTestCase, TestCase

from quotes.models import HandlingUnit, LocationType, QuoteRequest, UnitType

# Hand-calculated worked examples from the Slice 1 spec: (weight, length, width, height, class).
WORKED_EXAMPLES = [
    (400, 60, 40, 30, "100"),
    (1500, 52, 36, 28, "55"),
    (250, 41, 36, 72, "175"),
    (2240, 48, 48, 48, "55"),
    (2239, 48, 48, 48, "60"),
]


def make_request(**overrides):
    values = {
        "origin_street": "100 Main St",
        "origin_city": "Allen",
        "origin_state": "TX",
        "origin_postal_code": "75002",
        "origin_location_type": LocationType.BUSINESS_DOCK,
        "destination_street": "200 Oak Ave",
        "destination_city": "Chicago",
        "destination_state": "IL",
        "destination_postal_code": "60601",
        "destination_location_type": LocationType.RESIDENTIAL,
        "pickup_date": "2026-11-16",
    }
    values.update(overrides)
    return QuoteRequest.objects.create(**values)


def make_unit(request, **overrides):
    values = {
        "quote_request": request,
        "unit_type": UnitType.PALLET,
        "quantity": 1,
        "length_in": 48,
        "width_in": 40,
        "height_in": 48,
        "weight_lb": 500,
        "commodity_description": "Boxed widgets",
    }
    values.update(overrides)
    return HandlingUnit.objects.create(**values)


class HandlingUnitComputedValueTests(SimpleTestCase):
    def test_density_and_suggested_class_match_worked_examples(self):
        for weight, length, width, height, expected_class in WORKED_EXAMPLES:
            with self.subTest(weight=weight, size=(length, width, height)):
                unit = HandlingUnit(
                    weight_lb=weight, length_in=length, width_in=width, height_in=height
                )
                self.assertEqual(unit.suggested_class, expected_class)

    def test_density_is_exact_for_terminating_cases(self):
        unit = HandlingUnit(weight_lb=400, length_in=60, width_in=40, height_in=30)
        self.assertEqual(unit.density, Decimal("9.6"))

    def test_quantity_does_not_change_density(self):
        one = HandlingUnit(quantity=1, weight_lb=400, length_in=60, width_in=40, height_in=30)
        ten = HandlingUnit(quantity=10, weight_lb=400, length_in=60, width_in=40, height_in=30)
        self.assertEqual(one.density, ten.density)
        self.assertEqual(one.suggested_class, ten.suggested_class)

    def test_density_and_class_are_not_stored_columns(self):
        field_names = {field.name for field in HandlingUnit._meta.get_fields()}
        self.assertNotIn("density", field_names)
        self.assertNotIn("suggested_class", field_names)


class ModelStorageTests(TestCase):
    def test_handling_units_belong_to_a_request_in_creation_order(self):
        request = make_request()
        first = make_unit(request, commodity_description="First")
        second = make_unit(request, commodity_description="Second")
        self.assertEqual(list(request.handling_units.all()), [first, second])

    def test_requests_are_ordered_newest_first(self):
        older = make_request()
        newer = make_request()
        self.assertEqual(list(QuoteRequest.objects.all()), [newer, older])

    def test_supplied_class_is_stored_without_changing_the_suggestion(self):
        request = make_request()
        unit = make_unit(request, weight_lb=400, length_in=60, width_in=40, height_in=30)
        unit.freight_class = "110"
        unit.save()
        unit.refresh_from_db()
        self.assertEqual(unit.freight_class, "110")
        self.assertEqual(unit.suggested_class, "100")

    def test_deleting_a_request_deletes_its_units(self):
        request = make_request()
        make_unit(request)
        request.delete()
        self.assertEqual(HandlingUnit.objects.count(), 0)
