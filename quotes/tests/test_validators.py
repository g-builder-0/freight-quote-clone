from django.core.exceptions import ValidationError
from django.test import SimpleTestCase

from quotes.validators import validate_nmfc_code, validate_postal_code, validate_us_state


class StateValidatorTests(SimpleTestCase):
    def test_valid_states_and_dc(self):
        for value in ("TX", "CA", "NY", "WY", "AK", "HI", "DC"):
            with self.subTest(value=value):
                validate_us_state(value)

    def test_invalid_states(self):
        for value in ("tx", "ZZ", "T", "Texas", "PR", "XX", "", "T X"):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                validate_us_state(value)

    def test_all_fifty_states_plus_dc_are_accepted(self):
        from quotes.validators import US_STATE_CODES

        self.assertEqual(len(US_STATE_CODES), 51)


class PostalCodeValidatorTests(SimpleTestCase):
    def test_valid_postal_codes(self):
        for value in ("75002", "75002-1234", "00501", "99950"):
            with self.subTest(value=value):
                validate_postal_code(value)

    def test_invalid_postal_codes(self):
        for value in ("7500", "750022", "75002-123", "75002-12345", "abcde", "75002 ", "75002-"):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                validate_postal_code(value)


class NmfcCodeValidatorTests(SimpleTestCase):
    def test_valid_nmfc_codes(self):
        for value in ("153760", "61780", "1234", "153760-03", "153760-3"):
            with self.subTest(value=value):
                validate_nmfc_code(value)

    def test_invalid_nmfc_codes(self):
        for value in (
            "abc",
            "12",
            "123",
            "1234567",
            "153760-",
            "153760 sub 3",
            "153760-003",
            "-03",
            "15 3760",
            "NMFC 153760",
        ):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                validate_nmfc_code(value)
