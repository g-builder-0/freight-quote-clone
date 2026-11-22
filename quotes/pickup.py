"""Pickup-date rule.

Plain-input module: it takes dates and returns nothing or raises, with no database, no web
request and no reading of the clock. The caller passes "today" in, so tests can supply any date.
"""

from datetime import date, timedelta


class PickupDateError(ValueError):
    """The requested pickup date breaks a pickup rule."""


def is_business_day(day: date) -> bool:
    """Return True for Monday to Friday.

    Holidays are NOT considered in Slice 1. This is the one place to change if they are added
    later (for example with the `holidays` package); see docs/slices/slice_01_quote_request.md.
    """
    return day.weekday() < 5


def validate_pickup_date(pickup_date: date, today: date) -> None:
    """Raise PickupDateError unless pickup_date is a business day AFTER today.

    "today" is the caller's current date in America/Chicago (supplied by the serializer).
    """
    if pickup_date <= today:
        raise PickupDateError("Pickup date must be after today.")
    if not is_business_day(pickup_date):
        raise PickupDateError("Pickup date must be a business day (Monday to Friday).")


def add_business_days(start: date, days: int) -> date:
    """Return the date that is `days` business days after `start` (`start` itself is day 0).

    Weekends are skipped; holidays are ignored because `is_business_day` ignores them. Used for the
    estimated delivery date: transit days are counted from the pickup date.
    """
    if days < 0:
        raise ValueError("days must not be negative.")
    current = start
    remaining = days
    while remaining > 0:
        current += timedelta(days=1)
        if is_business_day(current):
            remaining -= 1
    return current
