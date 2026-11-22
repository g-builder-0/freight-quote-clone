from decimal import Decimal
from fractions import Fraction

from django.test import SimpleTestCase

from quotes.freight_class import (
    CLASS_TABLE_VERSION,
    STANDARD_NMFC_CLASSES,
    calculate_density,
    format_class,
    suggest_class,
)

# Hand-calculated by Graham (Slice 1 spec, "Worked examples"). Quantity is 1 in every case.
# (case, weight_lb, length_in, width_in, height_in, exact density as a fraction, expected class)
WORKED_EXAMPLES = [
    ("1 ordinary mid-density pallet", 400, 60, 40, 30, Fraction(48, 5), "100"),
    ("2 very dense unit", 1500, 52, 36, 28, Fraction(4500, 91), "55"),
    ("3 light bulky unit", 250, 41, 36, 72, Fraction(500, 123), "175"),
    ("4 exact boundary 35.0", 2240, 48, 48, 48, Fraction(35), "55"),
    ("5 just under boundary", 2239, 48, 48, 48, Fraction(2239, 64), "60"),
]

# Spec table, "lower bound inclusive, upper bound exclusive": a density just below a boundary
# and exactly on it. (density, expected class)
TABLE_BOUNDARY_CASES = [
    ("0.99", "400"),
    ("1", "300"),
    ("1.99", "300"),
    ("2", "250"),
    ("3.99", "250"),
    ("4", "175"),
    ("5.99", "175"),
    ("6", "125"),
    ("7.99", "125"),
    ("8", "100"),
    ("9.99", "100"),
    ("10", "92.5"),
    ("11.99", "92.5"),
    ("12", "85"),
    ("14.99", "85"),
    ("15", "70"),
    ("22.49", "70"),
    ("22.5", "65"),
    ("29.99", "65"),
    ("30", "60"),
    ("34.99", "60"),
    ("35", "55"),
    ("49.99", "55"),
    ("50", "50"),
    ("500", "50"),
]


class WorkedExampleTests(SimpleTestCase):
    def test_worked_examples_give_expected_class(self):
        for name, weight, length, width, height, _density, expected_class in WORKED_EXAMPLES:
            with self.subTest(name):
                density = calculate_density(weight, length, width, height)
                self.assertEqual(format_class(suggest_class(density)), expected_class)

    def test_worked_examples_density_matches_exact_fraction(self):
        # Rows with repeating decimals (2 and 3) are compared to the exact fraction with a stated
        # tolerance of 1e-20; the terminating ones must match exactly.
        tolerance = Fraction(1, 10**20)
        for name, weight, length, width, height, exact, _expected_class in WORKED_EXAMPLES:
            with self.subTest(name):
                density = calculate_density(weight, length, width, height)
                self.assertLess(abs(Fraction(density) - exact), tolerance)

    def test_terminating_densities_are_exact(self):
        self.assertEqual(calculate_density(400, 60, 40, 30), Decimal("9.6"))
        self.assertEqual(calculate_density(2240, 48, 48, 48), Decimal("35"))
        self.assertEqual(calculate_density(2239, 48, 48, 48), Decimal("34.984375"))

    def test_boundary_35_is_class_55_and_just_under_is_class_60(self):
        self.assertEqual(format_class(suggest_class(calculate_density(2240, 48, 48, 48))), "55")
        self.assertEqual(format_class(suggest_class(calculate_density(2239, 48, 48, 48))), "60")

    def test_density_is_not_rounded_before_class_lookup(self):
        # 34.984375 would display as 34.98 (or 35.0 at one decimal) but must still be class 60.
        density = calculate_density(2239, 48, 48, 48)
        self.assertEqual(format_class(suggest_class(density)), "60")
        self.assertEqual(
            format_class(suggest_class(round(density, 1))), "55"
        )  # what rounding breaks


class ClassTableTests(SimpleTestCase):
    def test_every_tier_boundary(self):
        for density, expected_class in TABLE_BOUNDARY_CASES:
            with self.subTest(density=density):
                self.assertEqual(format_class(suggest_class(Decimal(density))), expected_class)

    def test_class_table_version_is_set(self):
        self.assertIsInstance(CLASS_TABLE_VERSION, str)
        self.assertTrue(CLASS_TABLE_VERSION)

    def test_standard_classes_are_the_18_nmfc_classes(self):
        self.assertEqual(len(STANDARD_NMFC_CLASSES), 18)
        self.assertEqual(STANDARD_NMFC_CLASSES[0], "50")
        self.assertEqual(STANDARD_NMFC_CLASSES[-1], "500")
        for expected in ("77.5", "92.5", "110", "150", "200", "500"):
            self.assertIn(expected, STANDARD_NMFC_CLASSES)

    def test_every_suggested_class_is_a_standard_class(self):
        for _density, expected_class in TABLE_BOUNDARY_CASES:
            self.assertIn(expected_class, STANDARD_NMFC_CLASSES)


class CalculateDensityInputTests(SimpleTestCase):
    def test_zero_weight_or_dimension_is_rejected(self):
        for args in [(0, 10, 10, 10), (10, 0, 10, 10), (10, 10, 0, 10), (10, 10, 10, 0)]:
            with self.subTest(args=args), self.assertRaises(ValueError):
                calculate_density(*args)

    def test_format_class_plain_text(self):
        self.assertEqual(format_class(Decimal("55")), "55")
        self.assertEqual(format_class(Decimal("92.5")), "92.5")
        self.assertEqual(format_class(Decimal("100")), "100")
        self.assertEqual(format_class(Decimal("400")), "400")
