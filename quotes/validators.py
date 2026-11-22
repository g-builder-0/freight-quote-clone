"""Shared field validators.

Each rule is written once here and reused by every field that needs it (for example the
origin and destination address fields), so a rule changes in exactly one place.
"""

from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator

# The 50 states plus DC. US territories are not accepted in Slice 1.
US_STATE_CODES = frozenset(
    "AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ "
    "NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY DC".split()
)


def validate_us_state(value: str) -> None:
    if value not in US_STATE_CODES:
        raise ValidationError("Enter a valid 2-letter US state or DC code, for example TX.")


# 5 digits, with an optional ZIP+4 (12345 or 12345-6789). Existence of the address is not checked.
validate_postal_code = RegexValidator(
    regex=r"^\d{5}(-\d{4})?\Z",
    message="Enter a 5-digit ZIP code, with an optional +4 (12345 or 12345-6789).",
)

# NMFC item number: 4 to 6 digits, with an optional hyphen and a 1- or 2-digit sub-number
# (for example 153760 or 153760-03). This checks the format only: it cannot confirm that the code
# exists or fits the commodity, which needs the paid NMFC database.
validate_nmfc_code = RegexValidator(
    regex=r"^\d{4,6}(-\d{1,2})?\Z",
    message="Enter an NMFC code: 4 to 6 digits, with an optional sub-number (153760-03).",
)
