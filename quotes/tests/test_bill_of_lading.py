"""Slice 3 step 2: the bill of lading and label builders, tested with Graham's Cases 1 to 3.

The builders take plain values, so no database is needed. Contacts, addresses, descriptions, units
and instructions are Graham's inputs from the spec; the dimensions (which the spec leaves to the
Slice 2 fixture) are passed through and only checked as pass-through.
"""

import json
from datetime import date

from django.test import SimpleTestCase

from quotes.bill_of_lading import (
    Party,
    UnitLine,
    barcode_for,
    booking_number_for,
    build_bill_of_lading,
    build_labels,
)
from quotes.contacts import Contact

DANA = Contact(name="Dana Whitfield", phone="972-555-0142")
ALLEN = Party(
    contact=DANA, street="2200 Commerce Park Way", city="Allen", state="TX",
    postal_code="75002", location_type="business_dock",
)  # fmt: skip


def unit(**overrides) -> UnitLine:
    fields = dict(
        unit_type="pallet", quantity=1, weight_lb=1000, length_in=48, width_in=40, height_in=40,
        freight_class="100", commodity_description="Widgets",
    )  # fmt: skip
    fields.update(overrides)
    return UnitLine(**fields)


def case_1() -> dict:
    return build_bill_of_lading(
        booking_number="BK-000001",
        booking_date=date(2026, 11, 25),
        pickup_date=date(2026, 11, 30),
        carrier_code="mid",
        carrier_name="Mid",
        shipper=ALLEN,
        consignee=Party(
            contact=Contact(name="Marcus Bell", phone="404-555-0178"),
            street="418 Magnolia Ridge Dr SE",
            city="Atlanta",
            state="GA",
            postal_code="30301",
            location_type="residential",
        ),  # fmt: skip
        units=[
            unit(
                weight_lb=1200,
                freight_class="55",
                commodity_description="Ceramic floor tiles, boxed",
            ),
            unit(
                unit_type="crate",
                weight_lb=400,
                freight_class="125",
                commodity_description="Rack-mount network switches",
            ),
        ],  # fmt: skip
        liftgate_requested=True,
        appointment_requested=False,
        special_instructions=(
            "Carrier must provide a liftgate for delivery; the delivery address is a residence "
            "with no loading dock. Call receiver 30 minutes before delivery."
        ),
    )


def case_2(receiver: Contact) -> dict:
    return build_bill_of_lading(
        booking_number="BK-000001",
        booking_date=date(2026, 11, 25),
        pickup_date=date(2026, 12, 1),
        carrier_code="fast",
        carrier_name="Fast",
        shipper=ALLEN,
        consignee=Party(
            contact=receiver,
            street="Lot 7, 300 Harbor Ridge Rd",
            city="Portland",
            state="ME",
            postal_code="04101",
            location_type="construction_site",
        ),  # fmt: skip
        units=[
            unit(
                weight_lb=1500,
                freight_class="70",
                commodity_description="Automotive brake parts, boxed",
            ),
            unit(
                weight_lb=1000,
                freight_class="85",
                commodity_description="Crated industrial pump assemblies",
            ),
        ],  # fmt: skip
        liftgate_requested=False,
        appointment_requested=True,
        special_instructions=(
            "Delivery appointment required; call receiver to schedule. "
            "Site gate code needed from receiver."
        ),
    )


def case_3() -> dict:
    return build_bill_of_lading(
        booking_number="BK-000001",
        booking_date=date(2026, 11, 25),
        pickup_date=date(2026, 12, 7),
        carrier_code="cheap",
        carrier_name="Cheap",
        shipper=ALLEN,
        consignee=Party(
            contact=Contact(name="Elena Ortiz", phone="323-555-0119"),
            street="4500 Distribution Ave",
            city="Los Angeles",
            state="CA",
            postal_code="90001",
            location_type="business_dock",
        ),  # fmt: skip
        units=[
            unit(
                quantity=3,
                weight_lb=400,
                freight_class="70",
                commodity_description="Packaged hardware fasteners",
            ),
            unit(
                unit_type="crate",
                quantity=2,
                weight_lb=250,
                freight_class="70",
                commodity_description="Replacement electric motor housings",
            ),
            unit(
                unit_type="drum",
                quantity=2,
                weight_lb=150,
                freight_class="150",
                commodity_description="Food-grade vegetable oil, sealed drums",
            ),
        ],  # fmt: skip
        liftgate_requested=False,
        appointment_requested=False,
        special_instructions="Receiving dock hours 7:00 to 15:00.",
    )


class NumberTests(SimpleTestCase):
    def test_the_booking_number_is_bk_plus_the_id_padded_to_six_digits(self):
        self.assertEqual(booking_number_for(1), "BK-000001")
        self.assertEqual(booking_number_for(123), "BK-000123")
        self.assertEqual(booking_number_for(999999), "BK-999999")

    def test_the_barcode_pads_unit_and_total_to_two_digits(self):
        self.assertEqual(barcode_for("BK-000001", 3, 7), "BK-000001-03-07")
        self.assertEqual(barcode_for("BK-000001", 12, 12), "BK-000001-12-12")

    def test_the_barcode_widens_for_a_hundred_or_more_units(self):
        self.assertEqual(barcode_for("BK-000001", 7, 100), "BK-000001-007-100")


class Case1Tests(SimpleTestCase):
    def test_header_carrier_and_dates(self):
        bol = case_1()
        self.assertEqual(bol["number"], "BK-000001")
        self.assertEqual(bol["booking_date"], "2026-11-25")
        self.assertEqual(bol["pickup_date"], "2026-11-30")
        self.assertEqual(bol["carrier"], {"code": "mid", "name": "Mid"})

    def test_shipper_and_consignee(self):
        bol = case_1()
        self.assertEqual(
            bol["shipper"],
            {
                "name": "Dana Whitfield", "phone": "972-555-0142", "email": "",
                "street": "2200 Commerce Park Way", "city": "Allen", "state": "TX",
                "postal_code": "75002", "location_type": "business_dock",
            },
        )  # fmt: skip
        self.assertEqual(
            bol["consignee"],
            {
                "name": "Marcus Bell", "phone": "404-555-0178", "email": "",
                "street": "418 Magnolia Ridge Dr SE", "city": "Atlanta", "state": "GA",
                "postal_code": "30301", "location_type": "residential",
            },
        )  # fmt: skip

    def test_units_total_weight_accessorials_and_instructions(self):
        bol = case_1()
        self.assertEqual(
            [(u["unit_type"], u["quantity"], u["weight_lb"], u["freight_class"],
              u["commodity_description"]) for u in bol["units"]],
            [
                ("pallet", 1, 1200, "55", "Ceramic floor tiles, boxed"),
                ("crate", 1, 400, "125", "Rack-mount network switches"),
            ],
        )  # fmt: skip
        self.assertEqual(bol["total_weight_lb"], 1600)
        self.assertEqual(bol["accessorials"], ["liftgate"])
        self.assertTrue(bol["special_instructions"].startswith("Carrier must provide a liftgate"))

    def test_no_price_or_fee_appears_anywhere(self):
        text = json.dumps(case_1()).lower()
        for word in ("price", 'total":', "fee", "fuel", "913", "amount", "$"):
            with self.subTest(word=word):
                self.assertNotIn(word, text)

    def test_unit_dimensions_and_nmfc_pass_through(self):
        first = case_1()["units"][0]
        self.assertEqual((first["length_in"], first["width_in"], first["height_in"]), (48, 40, 40))
        self.assertEqual((first["nmfc_code"], first["stackable"]), ("", False))

    def test_the_document_is_plain_json_data(self):
        bol = case_1()
        self.assertEqual(json.loads(json.dumps(bol)), bol)


class Case2Tests(SimpleTestCase):
    def test_2a_phone_only_receiver(self):
        bol = case_2(Contact(name="Priya Raman", phone="207-555-0163"))
        self.assertEqual(bol["consignee"]["phone"], "207-555-0163")
        self.assertEqual(bol["consignee"]["email"], "")

    def test_2c_phone_and_email_are_both_shown(self):
        bol = case_2(
            Contact(name="Priya Raman", phone="207-555-0163", email="priya.raman@example.com")
        )
        self.assertEqual(bol["consignee"]["phone"], "207-555-0163")
        self.assertEqual(bol["consignee"]["email"], "priya.raman@example.com")

    def test_destination_is_a_construction_site_and_the_accessorial_is_the_appointment(self):
        bol = case_2(Contact(name="Priya Raman", phone="207-555-0163"))
        self.assertEqual(bol["consignee"]["location_type"], "construction_site")
        self.assertEqual(bol["consignee"]["street"], "Lot 7, 300 Harbor Ridge Rd")
        self.assertEqual(bol["accessorials"], ["appointment"])
        self.assertEqual(bol["carrier"]["name"], "Fast")
        self.assertEqual(bol["pickup_date"], "2026-12-01")

    def test_total_weight_is_2500_and_no_price_appears(self):
        bol = case_2(Contact(name="Priya Raman", phone="207-555-0163"))
        self.assertEqual(bol["total_weight_lb"], 2500)
        text = json.dumps(bol).lower()
        for word in ("1605", "price", "fee", "limited"):
            with self.subTest(word=word):
                self.assertNotIn(word, text)


class Case3LabelTests(SimpleTestCase):
    def test_seven_labels_counted_across_the_booking(self):
        labels = build_labels(case_3())
        self.assertEqual(len(labels), 7)  # the sum of the quantities, not the 3 lines
        self.assertEqual(
            [
                (label["unit_number"], label["total_units"], label["unit_type"], label["weight_lb"],
                 label["freight_class"], label["barcode"])
                for label in labels
            ],
            [
                (1, 7, "pallet", 400, "70", "BK-000001-01-07"),
                (2, 7, "pallet", 400, "70", "BK-000001-02-07"),
                (3, 7, "pallet", 400, "70", "BK-000001-03-07"),
                (4, 7, "crate", 250, "70", "BK-000001-04-07"),
                (5, 7, "crate", 250, "70", "BK-000001-05-07"),
                (6, 7, "drum", 150, "150", "BK-000001-06-07"),
                (7, 7, "drum", 150, "150", "BK-000001-07-07"),
            ],
        )  # fmt: skip

    def test_each_label_shows_one_units_weight_not_the_lines_weight(self):
        weights = {label["weight_lb"] for label in build_labels(case_3())}
        self.assertEqual(weights, {400, 250, 150})

    def test_every_label_carries_the_shared_details(self):
        for label in build_labels(case_3()):
            with self.subTest(unit=label["unit_number"]):
                self.assertEqual(label["booking_number"], "BK-000001")
                self.assertEqual(label["shipper_name"], "Dana Whitfield")
                self.assertEqual((label["shipper_city"], label["shipper_state"]), ("Allen", "TX"))
                self.assertEqual(label["consignee_name"], "Elena Ortiz")
                self.assertEqual(
                    (label["consignee_city"], label["consignee_state"]), ("Los Angeles", "CA")
                )
                self.assertEqual(label["destination_postal_code"], "90001")
                self.assertEqual(label["carrier_name"], "Cheap")
                self.assertEqual(label["pickup_date"], "2026-12-07")

    def test_each_label_carries_its_units_description(self):
        descriptions = [label["commodity_description"] for label in build_labels(case_3())]
        self.assertEqual(
            descriptions,
            ["Packaged hardware fasteners"] * 3
            + ["Replacement electric motor housings"] * 2
            + ["Food-grade vegetable oil, sealed drums"] * 2,
        )

    def test_barcodes_are_unique_within_a_booking(self):
        barcodes = [label["barcode"] for label in build_labels(case_3())]
        self.assertEqual(len(set(barcodes)), len(barcodes))

    def test_case_3_total_weight_is_2000(self):
        self.assertEqual(case_3()["total_weight_lb"], 2000)

    def test_one_unit_gives_one_label(self):
        labels = build_labels(case_1())
        self.assertEqual(
            [(label["unit_number"], label["total_units"]) for label in labels], [(1, 2), (2, 2)]
        )

    def test_labels_come_from_the_stored_document_alone(self):
        # A document that went through JSON (as a stored snapshot does) gives the same labels.
        stored = json.loads(json.dumps(case_3()))
        self.assertEqual(build_labels(stored), build_labels(case_3()))
