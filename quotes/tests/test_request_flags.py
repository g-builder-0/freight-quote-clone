"""Slice 2 step 1: the liftgate and appointment flags on a quote request."""

from quotes.tests.test_api import QuoteApiTestCase, request_payload


class RequestedAccessorialFlagTests(QuoteApiTestCase):
    def test_flags_default_to_false_when_omitted(self):
        body = self.assert_created(request_payload())
        self.assertIs(body["liftgate_requested"], False)
        self.assertIs(body["appointment_requested"], False)

    def test_liftgate_can_be_requested(self):
        body = self.assert_created(request_payload(liftgate_requested=True))
        self.assertIs(body["liftgate_requested"], True)
        self.assertIs(body["appointment_requested"], False)

    def test_appointment_can_be_requested(self):
        body = self.assert_created(request_payload(appointment_requested=True))
        self.assertIs(body["liftgate_requested"], False)
        self.assertIs(body["appointment_requested"], True)

    def test_flags_are_returned_when_the_request_is_fetched(self):
        created = self.assert_created(
            request_payload(liftgate_requested=True, appointment_requested=True)
        )
        fetched = self.client.get(f"/api/quote-requests/{created['id']}/").json()
        self.assertIs(fetched["liftgate_requested"], True)
        self.assertIs(fetched["appointment_requested"], True)

    def test_a_non_boolean_flag_is_rejected(self):
        self.assert_rejected(
            request_payload(liftgate_requested="maybe"), field="liftgate_requested"
        )
