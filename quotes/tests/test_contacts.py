"""Slice 3 step 1: contact and special-instruction rules (plain input, no database)."""

from django.test import SimpleTestCase

from quotes.contacts import (
    APPOINTMENT_PHONE_MESSAGE,
    Contact,
    clean_contact,
    clean_instructions,
    clean_receiver,
    clean_shipper,
    normalize_phone,
)


class NormalizePhoneTests(SimpleTestCase):
    def test_accepted_formats_all_become_dashed(self):
        for raw in (
            "972-555-0142", "(972) 555-0142", "972.555.0142", "972 555 0142",
            "9725550142", "+1 972 555 0142", "1-972-555-0142", "  972-555-0142  ",
        ):  # fmt: skip
            with self.subTest(raw=raw):
                self.assertEqual(normalize_phone(raw), "972-555-0142")

    def test_rejected_formats(self):
        for raw in (
            "555-0142", "972-555-014", "972-555-01421", "abcdefghij", "972-555-01x2",
            "+44 972 555 0142", "2-972-555-0142", "",
        ):  # fmt: skip
            with self.subTest(raw=raw):
                self.assertIsNone(normalize_phone(raw))


class ShipperTests(SimpleTestCase):
    def test_case_1_shipper_is_accepted_unchanged(self):
        contact, errors = clean_shipper({"name": "Dana Whitfield", "phone": "972-555-0142"})
        self.assertEqual(errors, {})
        self.assertEqual(contact, Contact(name="Dana Whitfield", phone="972-555-0142"))

    def test_phone_only_email_only_and_both_are_each_enough(self):
        for data in (
            {"name": "Dana", "phone": "972-555-0142"},
            {"name": "Dana", "email": "dana@example.com"},
            {"name": "Dana", "phone": "972-555-0142", "email": "dana@example.com"},
        ):
            with self.subTest(data=data):
                contact, errors = clean_shipper(data)
                self.assertEqual(errors, {})
                self.assertIsNotNone(contact)

    def test_a_missing_or_blank_name_is_an_error(self):
        for data in ({"phone": "972-555-0142"}, {"name": "   ", "phone": "972-555-0142"}):
            with self.subTest(data=data):
                contact, errors = clean_shipper(data)
                self.assertIsNone(contact)
                self.assertEqual(errors, {"name": ["Enter a name."]})

    def test_a_name_of_100_characters_is_fine_and_101_is_not(self):
        ok, errors = clean_shipper({"name": "A" * 100, "phone": "972-555-0142"})
        self.assertEqual(errors, {})
        self.assertEqual(len(ok.name), 100)
        _, errors = clean_shipper({"name": "A" * 101, "phone": "972-555-0142"})
        self.assertEqual(errors, {"name": ["A name can be at most 100 characters."]})

    def test_neither_phone_nor_email_is_a_whole_contact_error(self):
        contact, errors = clean_shipper({"name": "Dana"})
        self.assertIsNone(contact)
        self.assertEqual(
            errors, {"non_field_errors": ["Enter a phone number or an email address."]}
        )

    def test_a_malformed_phone_or_email_is_reported_on_its_own_field(self):
        _, errors = clean_shipper({"name": "Dana", "phone": "555-0142"})
        self.assertEqual(
            errors, {"phone": ["Enter a 10-digit US phone number, for example 972-555-0142."]}
        )
        _, errors = clean_shipper({"name": "Dana", "email": "not-an-email"})
        self.assertEqual(errors, {"email": ["Enter a valid email address."]})

    def test_every_problem_is_reported_at_once(self):
        _, errors = clean_shipper({"name": "", "phone": "12", "email": "nope"})
        self.assertEqual(set(errors), {"name", "phone", "email"})

    def test_values_are_trimmed_and_missing_values_become_empty_strings(self):
        contact, _ = clean_shipper({"name": "  Dana  ", "email": " dana@example.com "})
        self.assertEqual(contact, Contact(name="Dana", phone="", email="dana@example.com"))


class ReceiverTests(SimpleTestCase):
    """Graham's Case 1 and Case 2 receivers, with and without the appointment flag."""

    def test_case_1_receiver_without_an_appointment(self):
        contact, errors = clean_receiver(
            {"name": "Marcus Bell", "phone": "404-555-0178"}, appointment_requested=False
        )
        self.assertEqual(errors, {})
        self.assertEqual(contact, Contact(name="Marcus Bell", phone="404-555-0178"))

    def test_case_2a_appointment_with_a_phone_is_accepted(self):
        contact, errors = clean_receiver(
            {"name": "Priya Raman", "phone": "207-555-0163"}, appointment_requested=True
        )
        self.assertEqual(errors, {})
        self.assertEqual(contact, Contact(name="Priya Raman", phone="207-555-0163"))

    def test_case_2b_appointment_with_an_email_only_is_rejected_on_the_phone_field(self):
        contact, errors = clean_receiver(
            {"name": "Priya Raman", "email": "priya.raman@example.com"}, appointment_requested=True
        )
        self.assertIsNone(contact)
        self.assertEqual(errors, {"phone": [APPOINTMENT_PHONE_MESSAGE]})
        self.assertEqual(
            APPOINTMENT_PHONE_MESSAGE,
            "A phone number is required for the receiver when the quote includes a delivery "
            "appointment.",
        )

    def test_case_2c_appointment_with_phone_and_email_keeps_both(self):
        contact, errors = clean_receiver(
            {"name": "Priya Raman", "phone": "207-555-0163", "email": "priya.raman@example.com"},
            appointment_requested=True,
        )
        self.assertEqual(errors, {})
        self.assertEqual(
            contact,
            Contact(name="Priya Raman", phone="207-555-0163", email="priya.raman@example.com"),
        )

    def test_without_an_appointment_an_email_only_receiver_is_accepted(self):
        contact, errors = clean_receiver(
            {"name": "Priya Raman", "email": "priya.raman@example.com"}, appointment_requested=False
        )
        self.assertEqual(errors, {})
        self.assertEqual(contact.email, "priya.raman@example.com")

    def test_an_appointment_receiver_with_nothing_at_all_gets_only_the_phone_error(self):
        _, errors = clean_receiver({"name": "Priya Raman"}, appointment_requested=True)
        self.assertEqual(errors, {"phone": [APPOINTMENT_PHONE_MESSAGE]})

    def test_a_malformed_phone_on_an_appointment_receiver_gets_the_format_message(self):
        _, errors = clean_receiver(
            {"name": "Priya Raman", "phone": "555-0163"}, appointment_requested=True
        )
        self.assertEqual(
            errors, {"phone": ["Enter a 10-digit US phone number, for example 972-555-0142."]}
        )

    def test_the_receiver_still_needs_a_name(self):
        _, errors = clean_receiver({"phone": "207-555-0163"}, appointment_requested=True)
        self.assertEqual(errors, {"name": ["Enter a name."]})


class CleanContactTests(SimpleTestCase):
    def test_a_non_string_value_is_treated_as_missing(self):
        contact, errors = clean_contact({"name": "Dana", "phone": 9725550142, "email": None})
        self.assertIsNone(contact)
        self.assertEqual(
            errors, {"non_field_errors": ["Enter a phone number or an email address."]}
        )


class InstructionsTests(SimpleTestCase):
    def test_case_1_instructions_are_kept_as_written(self):
        text = (
            "Carrier must provide a liftgate for delivery; the delivery address is a residence "
            "with no loading dock. Call receiver 30 minutes before delivery."
        )
        self.assertEqual(clean_instructions(text), (text, []))

    def test_instructions_are_optional(self):
        for value in (None, "", "   "):
            with self.subTest(value=value):
                self.assertEqual(clean_instructions(value), ("", []))

    def test_the_500_character_boundary(self):
        self.assertEqual(clean_instructions("x" * 500), ("x" * 500, []))
        self.assertEqual(
            clean_instructions("x" * 501),
            ("", ["Special instructions can be at most 500 characters."]),
        )

    def test_surrounding_spaces_do_not_count_toward_the_limit(self):
        self.assertEqual(clean_instructions("  " + "x" * 500 + "  "), ("x" * 500, []))
