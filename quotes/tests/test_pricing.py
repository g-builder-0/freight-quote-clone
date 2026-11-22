"""Slice 2 pricing rules, tested with plain inputs (no database, no web request).

The five worked examples are Graham's hand-calculated numbers from
docs/slices/slice_02_quote_engine.md and are used verbatim.
"""

from datetime import date
from decimal import ROUND_HALF_EVEN, Decimal

from django.test import SimpleTestCase

from quotes import pricing
from quotes.pricing import ShipmentUnit, price_quote
from quotes.tests.tariff_fixture import CHEAP, FAST, MID, TARIFFS


def D(value: str) -> Decimal:
    return Decimal(value)


def summary(price):
    """(kind, description, source, amount) for each line, for readable assertions."""
    return [(item.kind, item.description, item.source, item.amount) for item in price.line_items]


class ZoneTests(SimpleTestCase):
    def test_zone_gap_is_the_difference_of_first_digits(self):
        cases = [
            ("75002", "30301", 4),  # Allen to Atlanta (Example 1)
            ("75002", "75201", 0),  # Allen to Dallas (Example 2)
            ("75002", "04101", 7),  # Allen to Portland ME (Example 3)
            ("75002", "85001", 1),  # Allen to Phoenix (Example 4)
            ("75002", "90001", 2),  # Allen to Los Angeles (Example 5)
            ("00501", "99950", 9),
            ("30301", "75002", 4),  # symmetric
        ]
        for origin, destination, expected in cases:
            with self.subTest(origin=origin, destination=destination):
                self.assertEqual(pricing.zone_gap(origin, destination), expected)

    def test_zone_gap_accepts_zip_plus_four(self):
        self.assertEqual(pricing.zone_gap("75002-1234", "60601-1234"), 1)

    def test_zone_factor_is_one_plus_a_tenth_per_gap(self):
        for gap, expected in [(0, "1.00"), (1, "1.10"), (2, "1.20"), (4, "1.40"), (7, "1.70")]:
            with self.subTest(gap=gap):
                self.assertEqual(pricing.zone_factor(gap), D(expected))


class ClassTests(SimpleTestCase):
    def test_class_multiplier_is_class_over_100(self):
        cases = [("50", "0.5"), ("55", "0.55"), ("100", "1"), ("125", "1.25"), ("500", "5"),
                 ("77.5", "0.775"), ("92.5", "0.925")]  # fmt: skip
        for freight_class, expected in cases:
            with self.subTest(freight_class=freight_class):
                self.assertEqual(pricing.class_multiplier(freight_class), D(expected))

    def test_pricing_class_uses_the_supplied_class_when_there_is_one(self):
        self.assertEqual(pricing.pricing_class("70", "85"), "70")  # they disagree: supplied wins

    def test_pricing_class_falls_back_to_the_suggested_class(self):
        self.assertEqual(pricing.pricing_class("", "85"), "85")

    def test_pricing_class_when_both_agree(self):
        self.assertEqual(pricing.pricing_class("92.5", "92.5"), "92.5")


class WeightTests(SimpleTestCase):
    def test_total_weight_is_unit_weight_times_quantity(self):
        units = [
            ShipmentUnit(400, 3, "70"),
            ShipmentUnit(250, 2, "70"),
            ShipmentUnit(150, 2, "150"),
        ]
        self.assertEqual(pricing.total_weight_lb(units), 2000)  # not 800: quantities count

    def test_weight_by_class_combines_units_of_the_same_class(self):
        units = [
            ShipmentUnit(400, 3, "70"),
            ShipmentUnit(250, 2, "70"),
            ShipmentUnit(150, 2, "150"),
        ]
        self.assertEqual(pricing.weight_by_class(units), {"70": 1700, "150": 300})

    def test_weight_by_class_orders_classes_numerically(self):
        units = [
            ShipmentUnit(100, 1, "125"),
            ShipmentUnit(100, 1, "92.5"),
            ShipmentUnit(100, 1, "50"),
        ]
        self.assertEqual(list(pricing.weight_by_class(units)), ["50", "92.5", "125"])

    def test_weight_break_boundaries_for_the_mid_carrier(self):
        # Each tier includes its lower and upper weight. Rates are from the approved tariff.
        cases = [(1, "48"), (499, "48"), (500, "40"), (999, "40"), (1000, "34"), (1999, "34"),
                 (2000, "28"), (4999, "28"), (5000, "23"), (20000, "23")]  # fmt: skip
        for weight, rate in cases:
            with self.subTest(weight=weight):
                self.assertEqual(pricing.weight_break_rate(MID, weight), D(rate))

    def test_weight_break_rate_for_each_carrier_at_1000_lb(self):
        self.assertEqual(pricing.weight_break_rate(CHEAP, 1000), D("30"))
        self.assertEqual(pricing.weight_break_rate(MID, 1000), D("34"))
        self.assertEqual(pricing.weight_break_rate(FAST, 1000), D("39"))


class MoneyRuleTests(SimpleTestCase):
    def test_to_cents_rounds_half_up(self):
        self.assertEqual(pricing.to_cents(D("1.005")), D("1.01"))
        self.assertEqual(pricing.to_cents(D("1.004")), D("1.00"))
        # Half-even would give 1.00 here; the project rule is half up.
        self.assertEqual(D("1.005").quantize(D("0.01"), rounding=ROUND_HALF_EVEN), D("1.00"))

    def test_apply_minimum_raises_a_low_line_haul_to_the_minimum(self):
        self.assertEqual(pricing.apply_minimum(D("63.00"), D("75")), D("75"))

    def test_apply_minimum_leaves_a_line_haul_above_the_minimum(self):
        self.assertEqual(pricing.apply_minimum(D("552.16"), D("90")), D("552.16"))

    def test_apply_minimum_at_exactly_the_minimum(self):
        self.assertEqual(pricing.apply_minimum(D("90.00"), D("90")), D("90.00"))

    def test_fuel_is_the_percentage_of_the_whole_line_haul(self):
        # 0.32 x 552.16 = 176.6912, rounded half up to cents (Example 1).
        self.assertEqual(pricing.fuel_amount(D("552.16"), D("0.32")), D("176.69"))

    def test_fuel_applies_on_top_of_the_minimum(self):
        self.assertEqual(pricing.fuel_amount(D("75.00"), D("0.28")), D("21.00"))  # Example 2

    def test_apply_markup_returns_the_carrier_cost_unchanged(self):
        self.assertEqual(pricing.apply_markup(D("913.85")), D("913.85"))

    def test_accessorial_fee_ignores_the_end(self):
        for fee_type in pricing.FEE_TYPES:
            with self.subTest(fee_type=fee_type):
                self.assertEqual(
                    pricing.accessorial_fee(MID, fee_type, pricing.PICKUP),
                    pricing.accessorial_fee(MID, fee_type, pricing.DELIVERY),
                )

    def test_accessorial_fees_of_the_mid_carrier(self):
        expected = {"residential": "100", "limited_access": "120", "liftgate": "85",
                    "appointment": "50"}  # fmt: skip
        for fee_type, amount in expected.items():
            with self.subTest(fee_type=fee_type):
                self.assertEqual(
                    pricing.accessorial_fee(MID, fee_type, pricing.DELIVERY), D(amount)
                )


class TransitTests(SimpleTestCase):
    def test_transit_days_formula(self):
        cases = [
            (4, 0, 3),  # Example 1: 1 + ceil(4/2) + 0
            (0, 1, 2),  # Example 2: 1 + 0 + 1
            (7, -1, 4),  # Example 3: 1 + ceil(7/2) - 1
            (1, 0, 2),  # Example 4: 1 + ceil(1/2) + 0
            (2, 1, 3),  # Example 5: 1 + ceil(2/2) + 1
        ]
        for gap, adjustment, expected in cases:
            with self.subTest(gap=gap, adjustment=adjustment):
                self.assertEqual(pricing.transit_days(gap, adjustment), expected)

    def test_transit_days_is_never_less_than_one(self):
        self.assertEqual(pricing.transit_days(0, -1), 1)  # 1 + 0 - 1 = 0, raised to 1

    def test_an_odd_gap_rounds_up(self):
        self.assertEqual(pricing.transit_days(3, 0), 3)  # 1 + ceil(1.5)


class WorkedExampleTests(SimpleTestCase):
    """Graham's five hand-calculated examples, line by line."""

    def test_example_1_mid_two_classes_auto_residential_and_requested_liftgate(self):
        price = price_quote(
            MID,
            origin_postal_code="75002",
            destination_postal_code="30301",
            origin_location_type="business_dock",
            destination_location_type="residential",
            pickup_date=date(2026, 11, 30),
            units=[ShipmentUnit(1200, 1, "55"), ShipmentUnit(400, 1, "125")],
            liftgate_requested=True,
        )
        self.assertEqual(
            summary(price),
            [
                ("line_haul", "Line-haul, class 55", "", D("314.16")),
                ("line_haul", "Line-haul, class 125", "", D("238.00")),
                ("fuel", "Fuel (32%)", "", D("176.69")),
                ("accessorial", "Residential delivery", "auto", D("100.00")),
                ("accessorial", "Liftgate", "requested", D("85.00")),
            ],
        )
        self.assertEqual(price.price, D("913.85"))
        self.assertEqual(price.transit_days, 3)
        self.assertEqual(price.estimated_delivery_date, date(2026, 12, 3))

    def test_example_2_cheap_minimum_charge_applies(self):
        price = price_quote(
            CHEAP,
            origin_postal_code="75002",
            destination_postal_code="75201",
            origin_location_type="business_dock",
            destination_location_type="business_dock",
            pickup_date=date(2026, 11, 23),
            units=[ShipmentUnit(150, 1, "100")],
        )
        self.assertEqual(
            summary(price),
            [
                ("line_haul", "Line-haul (minimum applied)", "", D("75.00")),
                ("fuel", "Fuel (28%)", "", D("21.00")),
            ],
        )
        self.assertEqual(price.price, D("96.00"))
        self.assertEqual(price.transit_days, 2)
        self.assertEqual(price.estimated_delivery_date, date(2026, 11, 25))

    def test_example_3_fast_construction_site_auto_limited_access_and_requested_appointment(self):
        price = price_quote(
            FAST,
            origin_postal_code="75002",
            destination_postal_code="04101",
            origin_location_type="business_dock",
            destination_location_type="construction_site",
            pickup_date=date(2026, 12, 1),
            units=[ShipmentUnit(1500, 1, "70"), ShipmentUnit(1000, 1, "85")],
            appointment_requested=True,
        )
        self.assertEqual(
            summary(price),
            [
                ("line_haul", "Line-haul, class 70", "", D("571.20")),
                ("line_haul", "Line-haul, class 85", "", D("462.40")),
                ("fuel", "Fuel (35%)", "", D("361.76")),
                ("accessorial", "Limited-access delivery", "auto", D("150.00")),
                ("accessorial", "Appointment", "requested", D("60.00")),
            ],
        )
        self.assertEqual(price.price, D("1605.36"))
        self.assertEqual(price.transit_days, 4)
        self.assertEqual(price.estimated_delivery_date, date(2026, 12, 7))

    def test_example_4_mid_exactly_1000_lb_uses_the_1000_to_1999_tier(self):
        price = price_quote(
            MID,
            origin_postal_code="75002",
            destination_postal_code="85001",
            origin_location_type="business_dock",
            destination_location_type="business_dock",
            pickup_date=date(2026, 12, 3),
            units=[ShipmentUnit(1000, 1, "100")],
        )
        self.assertEqual(
            summary(price),
            [
                ("line_haul", "Line-haul, class 100", "", D("374.00")),
                ("fuel", "Fuel (32%)", "", D("119.68")),
            ],
        )
        self.assertEqual(price.price, D("493.68"))
        self.assertEqual(price.transit_days, 2)
        self.assertEqual(price.estimated_delivery_date, date(2026, 12, 7))

    def test_example_5_cheap_quantities_above_one_and_same_class_lines_combine(self):
        price = price_quote(
            CHEAP,
            origin_postal_code="75002",
            destination_postal_code="90001",
            origin_location_type="business_dock",
            destination_location_type="business_dock",
            pickup_date=date(2026, 12, 7),
            units=[
                ShipmentUnit(400, 3, "70"),
                ShipmentUnit(250, 2, "70"),
                ShipmentUnit(150, 2, "150"),
            ],
        )
        self.assertEqual(
            summary(price),
            [
                ("line_haul", "Line-haul, class 70", "", D("357.00")),
                ("line_haul", "Line-haul, class 150", "", D("135.00")),
                ("fuel", "Fuel (28%)", "", D("137.76")),
            ],
        )
        self.assertEqual(price.price, D("629.76"))
        self.assertEqual(price.transit_days, 3)
        self.assertEqual(price.estimated_delivery_date, date(2026, 12, 10))

    def test_the_1000_lb_example_at_999_lb_uses_the_dearer_tier(self):
        # The same shipment as Example 4 but 999 lb: the 500-999 tier ($40), not $34.
        price = price_quote(
            MID,
            origin_postal_code="75002",
            destination_postal_code="85001",
            origin_location_type="business_dock",
            destination_location_type="business_dock",
            pickup_date=date(2026, 12, 3),
            units=[ShipmentUnit(999, 1, "100")],
        )
        # 9.99 cwt x $40 x 1.00 x 1.10 = 439.56
        self.assertEqual(price.line_items[0].amount, D("439.56"))


class BehaviourTests(SimpleTestCase):
    """Rules from the spec that the worked examples do not isolate on their own."""

    base = dict(
        origin_postal_code="75002",
        destination_postal_code="75201",
        origin_location_type="business_dock",
        destination_location_type="business_dock",
        pickup_date=date(2026, 12, 8),
        units=[ShipmentUnit(1000, 1, "100")],
    )

    def quote(self, tariff=MID, **overrides):
        return price_quote(tariff, **{**self.base, **overrides})

    def test_lines_sum_exactly_to_the_total_for_every_carrier(self):
        for tariff in TARIFFS.values():
            with self.subTest(carrier=tariff.code):
                price = self.quote(tariff, liftgate_requested=True, appointment_requested=True)
                self.assertEqual(sum(item.amount for item in price.line_items), price.price)

    def test_price_equals_carrier_cost_with_no_markup(self):
        price = self.quote()
        self.assertEqual(price.price, price.carrier_cost)

    def test_adding_a_liftgate_raises_the_total_by_exactly_the_liftgate_fee(self):
        for tariff in TARIFFS.values():
            with self.subTest(carrier=tariff.code):
                without = self.quote(tariff)
                with_liftgate = self.quote(tariff, liftgate_requested=True)
                self.assertEqual(with_liftgate.price - without.price, tariff.fees[pricing.LIFTGATE])

    def test_adding_an_appointment_raises_the_total_by_exactly_the_appointment_fee(self):
        for tariff in TARIFFS.values():
            with self.subTest(carrier=tariff.code):
                without = self.quote(tariff)
                with_appointment = self.quote(tariff, appointment_requested=True)
                self.assertEqual(
                    with_appointment.price - without.price, tariff.fees[pricing.APPOINTMENT]
                )

    def test_requested_fees_do_not_change_the_fuel_line(self):
        plain = self.quote()
        fees = self.quote(liftgate_requested=True, appointment_requested=True)
        self.assertEqual(
            [i.amount for i in plain.line_items if i.kind == "fuel"],
            [i.amount for i in fees.line_items if i.kind == "fuel"],
        )

    def test_a_business_dock_has_no_automatic_fee_at_either_end(self):
        price = self.quote()
        self.assertEqual([i for i in price.line_items if i.kind == "accessorial"], [])

    def test_residential_pickup_and_delivery_are_two_separate_lines(self):
        price = self.quote(
            origin_location_type="residential", destination_location_type="residential"
        )
        fees = [i for i in price.line_items if i.kind == "accessorial"]
        self.assertEqual(
            [(i.description, i.source, i.amount) for i in fees],
            [
                ("Residential pickup", "auto", D("100.00")),
                ("Residential delivery", "auto", D("100.00")),
            ],
        )

    def test_limited_access_is_charged_at_each_end(self):
        price = self.quote(origin_location_type="limited_access")
        fees = [(i.description, i.amount) for i in price.line_items if i.kind == "accessorial"]
        self.assertEqual(fees, [("Limited-access pickup", D("120.00"))])

    def test_a_construction_site_is_charged_as_limited_access_with_a_reason(self):
        price = self.quote(origin_location_type="construction_site")
        (fee,) = [i for i in price.line_items if i.kind == "accessorial"]
        self.assertEqual(
            (fee.description, fee.amount, fee.source),
            ("Limited-access pickup", D("120.00"), "auto"),
        )
        self.assertIn("construction site", fee.reason)

    def test_automatic_fees_carry_a_reason_and_requested_fees_say_so(self):
        price = self.quote(destination_location_type="residential", liftgate_requested=True)
        reasons = {i.description: i.reason for i in price.line_items if i.kind == "accessorial"}
        self.assertEqual(reasons["Residential delivery"], "residential delivery address")
        self.assertEqual(reasons["Liftgate"], "requested by shipper")

    def test_the_minimum_applies_to_the_whole_line_haul_not_each_class(self):
        # With the cheap carrier (rate $42 at under 500 lb... here 200 lb in total), class 100
        # prices at 1 cwt x 42 x 1.00 = 42.00 and class 200 at 1 cwt x 42 x 2.00 = 84.00. Each
        # line is tested against the whole: the sum 126.00 is above the $75 minimum, so it is not
        # applied even though the class 100 line alone (42.00) is below it.
        price = self.quote(CHEAP, units=[ShipmentUnit(100, 1, "100"), ShipmentUnit(100, 1, "200")])
        self.assertEqual(
            [(i.description, i.amount) for i in price.line_items if i.kind == "line_haul"],
            [("Line-haul, class 100", D("42.00")), ("Line-haul, class 200", D("84.00"))],
        )

    def test_a_denser_shipment_gets_a_lower_class_and_a_lower_line_haul_than_a_bulky_one(self):
        # Same weight; a lower class (denser freight) has a lower multiplier, so a lower line-haul.
        dense = self.quote(units=[ShipmentUnit(1000, 1, "50")])
        bulky = self.quote(units=[ShipmentUnit(1000, 1, "250")])
        self.assertLess(dense.line_items[0].amount, bulky.line_items[0].amount)

    def test_the_shipper_class_prices_the_shipment_when_it_differs_from_the_suggestion(self):
        supplied = pricing.pricing_class("70", "85")
        price = self.quote(units=[ShipmentUnit(1000, 1, supplied)])
        self.assertEqual(price.line_items[0].description, "Line-haul, class 70")

    def test_a_slightly_heavier_shipment_can_cost_less_because_rating_up_is_not_built(self):
        # Known simplification (README): 1,999 lb costs more than 2,000 lb for the mid carrier,
        # class 100, zone gap 0: 19.99 x 34 = 679.66 against 20 x 28 = 560.00.
        lighter = self.quote(units=[ShipmentUnit(1999, 1, "100")])
        heavier = self.quote(units=[ShipmentUnit(2000, 1, "100")])
        self.assertEqual(lighter.line_items[0].amount, D("679.66"))
        self.assertEqual(heavier.line_items[0].amount, D("560.00"))
        self.assertGreater(lighter.line_items[0].amount, heavier.line_items[0].amount)

    def test_fast_carrier_with_a_zero_gap_still_takes_one_transit_day(self):
        self.assertEqual(self.quote(FAST).transit_days, 1)
