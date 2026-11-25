"""Slice 3 step 4: the table of allowed booking status changes."""

from django.test import SimpleTestCase

from quotes.booking_status import ALLOWED_TRANSITIONS, can_transition
from quotes.models import BookingStatus


class CanTransitionTests(SimpleTestCase):
    def test_booked_can_become_cancelled(self):
        self.assertTrue(can_transition(BookingStatus.BOOKED, BookingStatus.CANCELLED))

    def test_every_other_pair_is_refused(self):
        allowed = {(BookingStatus.BOOKED, BookingStatus.CANCELLED)}
        for current in BookingStatus.values:
            for new in BookingStatus.values:
                with self.subTest(current=current, new=new):
                    self.assertEqual(can_transition(current, new), (current, new) in allowed)

    def test_cancelled_is_final(self):
        self.assertEqual(ALLOWED_TRANSITIONS[BookingStatus.CANCELLED], frozenset())

    def test_every_status_has_a_row_in_the_table(self):
        self.assertEqual(set(ALLOWED_TRANSITIONS), set(BookingStatus.values))

    def test_an_unknown_status_cannot_change(self):
        self.assertFalse(can_transition("shipped", BookingStatus.CANCELLED))
