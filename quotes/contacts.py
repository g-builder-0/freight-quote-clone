"""Contact and special-instruction rules for booking (Slice 3, tightened in Slice 5).

Plain-input functions: they take dictionaries and strings and return cleaned values and error
messages. Nothing here touches the database, the clock or the web layer, so every rule is tested
on its own. Error dictionaries use the same field names the API returns, for example
{"phone": ["..."]}; a problem with the contact as a whole is reported under "non_field_errors".
"""

from collections.abc import Mapping
from dataclasses import dataclass

from django.core.exceptions import ValidationError
from django.core.validators import validate_email

NAME_MAX_LENGTH = 100
INSTRUCTIONS_MAX_LENGTH = 500
CANCEL_REASON_MAX_LENGTH = 200


@dataclass(frozen=True)
class Contact:
    """A cleaned contact. `phone` is stored as NNN-NNN-NNNN; unused fields are empty strings."""

    name: str
    phone: str = ""
    email: str = ""


def normalize_phone(raw: str) -> str | None:
    """Return a US phone number as NNN-NNN-NNNN, or None if it is not one.

    Spaces, dashes, dots, parentheses and a leading +1 or 1 are accepted. Only the format is
    checked: the number is not looked up, and the area code is not validated.
    """
    stripped = raw.strip()
    if stripped.startswith("+"):
        stripped = stripped[1:]
        if not stripped.startswith("1"):
            return None
    digits = "".join(ch for ch in stripped if ch not in " -.()")
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    if len(digits) != 10 or not digits.isdigit():
        return None
    return f"{digits[:3]}-{digits[3:6]}-{digits[6:]}"


def _text(data: Mapping, key: str) -> str:
    value = data.get(key)
    return value.strip() if isinstance(value, str) else ""


def clean_contact(data: Mapping) -> tuple[Contact | None, dict]:
    """Check one contact: a name, a phone and an email are all required.

    The same rule applies to the shipper and the receiver. Values are trimmed first, so a value
    of only spaces counts as missing. Returns the cleaned contact and a dictionary of errors keyed
    by field; the contact is None when there are errors.
    """
    errors: dict[str, list[str]] = {}

    name = _text(data, "name")
    if not name:
        errors["name"] = ["Enter a name."]
    elif len(name) > NAME_MAX_LENGTH:
        errors["name"] = [f"A name can be at most {NAME_MAX_LENGTH} characters."]

    raw_phone = _text(data, "phone")
    phone = ""
    if not raw_phone:
        errors["phone"] = ["Enter a phone number."]
    else:
        normalized = normalize_phone(raw_phone)
        if normalized is None:
            errors["phone"] = ["Enter a 10-digit US phone number, for example 972-555-0142."]
        else:
            phone = normalized

    email = _text(data, "email")
    if not email:
        errors["email"] = ["Enter an email address."]
    else:
        try:
            validate_email(email)
        except ValidationError:
            errors["email"] = ["Enter a valid email address."]

    if errors:
        return None, errors
    return Contact(name=name, phone=phone, email=email), {}


def clean_instructions(value) -> tuple[str, list[str]]:
    """Special instructions: optional text of at most 500 characters (after trimming)."""
    text = value.strip() if isinstance(value, str) else ""
    if len(text) > INSTRUCTIONS_MAX_LENGTH:
        return "", [f"Special instructions can be at most {INSTRUCTIONS_MAX_LENGTH} characters."]
    return text, []


def clean_cancel_reason(value) -> tuple[str, list[str]]:
    """The reason for cancelling a booking: required text of at most 200 characters."""
    text = value.strip() if isinstance(value, str) else ""
    if not text:
        return "", ["Enter a reason for cancelling."]
    if len(text) > CANCEL_REASON_MAX_LENGTH:
        return "", [f"A reason can be at most {CANCEL_REASON_MAX_LENGTH} characters."]
    return text, []
