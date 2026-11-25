"""Contact and special-instruction rules (plain input, no database).

Slice 3 step 1, tightened in Slice 5: every contact needs a name, a phone and an email.
"""

from django.test import SimpleTestCase

from quotes.contacts import (
    Contact,
    clean_contact,
    clean_instructions,
    normalize_phone,
)

NEED_PHONE = "Enter a phone number."
NEED_EMAIL = "Enter an email address."
BAD_PHONE = "Enter a 10-digit US phone number, for example 972-555-0142."


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


class CleanContactTests(SimpleTestCase):
    """The one rule for both contacts: a name, a phone and an email, all required."""

    def test_a_complete_contact_is_accepted_and_the_phone_is_normalised(self):
        contact, errors = clean_contact(
            {
                "name": "Dana Whitfield",
                "phone": "(972) 555-0142",
                "email": "dana.whitfield@example.com",
            }
        )
        self.assertEqual(errors, {})
        self.assertEqual(
            contact,
            Contact(
                name="Dana Whitfield", phone="972-555-0142", email="dana.whitfield@example.com"
            ),
        )

    def test_case_5a_and_5d_a_missing_phone(self):
        contact, errors = clean_contact({"name": "Dana", "email": "dana@example.com"})
        self.assertIsNone(contact)
        self.assertEqual(errors, {"phone": [NEED_PHONE]})

    def test_case_5b_and_5e_a_missing_email(self):
        contact, errors = clean_contact({"name": "Dana", "phone": "972-555-0142"})
        self.assertIsNone(contact)
        self.assertEqual(errors, {"email": [NEED_EMAIL]})

    def test_case_5c_and_5f_neither_phone_nor_email_reports_both(self):
        contact, errors = clean_contact({"name": "Dana"})
        self.assertIsNone(contact)
        self.assertEqual(errors, {"phone": [NEED_PHONE], "email": [NEED_EMAIL]})

    def test_case_5g_a_malformed_phone_gets_the_format_message_only(self):
        _, errors = clean_contact({"name": "Dana", "phone": "972-555", "email": "d@example.com"})
        self.assertEqual(errors, {"phone": [BAD_PHONE]})

    def test_case_5h_a_malformed_email_gets_the_format_message_only(self):
        _, errors = clean_contact(
            {"name": "Dana", "phone": "972-555-0142", "email": "not-an-email"}
        )
        self.assertEqual(errors, {"email": ["Enter a valid email address."]})

    def test_case_5i_a_missing_or_blank_name_is_an_error(self):
        full = {"phone": "972-555-0142", "email": "dana@example.com"}
        for data in (dict(full), {"name": "   ", **full}):
            with self.subTest(data=data):
                contact, errors = clean_contact(data)
                self.assertIsNone(contact)
                self.assertEqual(errors, {"name": ["Enter a name."]})

    def test_a_name_of_100_characters_is_fine_and_101_is_not(self):
        rest = {"phone": "972-555-0142", "email": "dana@example.com"}
        ok, errors = clean_contact({"name": "A" * 100, **rest})
        self.assertEqual(errors, {})
        self.assertEqual(len(ok.name), 100)
        _, errors = clean_contact({"name": "A" * 101, **rest})
        self.assertEqual(errors, {"name": ["A name can be at most 100 characters."]})

    def test_every_problem_is_reported_at_once(self):
        _, errors = clean_contact({"name": "", "phone": "12", "email": "nope"})
        self.assertEqual(set(errors), {"name", "phone", "email"})

    def test_values_that_are_only_spaces_count_as_missing(self):
        _, errors = clean_contact({"name": "Dana", "phone": "   ", "email": "   "})
        self.assertEqual(errors, {"phone": [NEED_PHONE], "email": [NEED_EMAIL]})

    def test_values_are_trimmed(self):
        contact, errors = clean_contact(
            {"name": "  Dana  ", "phone": " 972-555-0142 ", "email": " dana@example.com "}
        )
        self.assertEqual(errors, {})
        self.assertEqual(
            contact, Contact(name="Dana", phone="972-555-0142", email="dana@example.com")
        )

    def test_a_non_string_value_is_treated_as_missing(self):
        contact, errors = clean_contact({"name": "Dana", "phone": 9725550142, "email": None})
        self.assertIsNone(contact)
        self.assertEqual(errors, {"phone": [NEED_PHONE], "email": [NEED_EMAIL]})

    def test_the_appointment_rule_and_the_old_either_or_message_are_gone(self):
        from quotes import contacts

        self.assertFalse(hasattr(contacts, "APPOINTMENT_PHONE_MESSAGE"))
        self.assertFalse(hasattr(contacts, "clean_shipper"))
        self.assertFalse(hasattr(contacts, "clean_receiver"))


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
