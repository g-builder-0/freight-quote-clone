"""Which booking status changes are allowed (Slice 3).

One small lookup decides every status change, so a rule such as "cancel only while booked" is a
consequence of the table and not a separate check scattered through the code. Slice 4 adds the
later statuses by adding rows here.
"""

from .models import BookingStatus

ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    BookingStatus.BOOKED: frozenset({BookingStatus.CANCELLED}),
    BookingStatus.CANCELLED: frozenset(),
}


def can_transition(current: str, new: str) -> bool:
    """May a booking go from the status `current` to the status `new`?"""
    return new in ALLOWED_TRANSITIONS.get(current, frozenset())
