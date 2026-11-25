"""Slice 3 step 5: the booking endpoints, Graham's Cases 1 to 4 end to end."""

from datetime import UTC, date, datetime
from unittest import mock

from rest_framework.test import APITestCase

from quotes.models import Booking, Quote
from quotes.services import create_quotes
from quotes.tariff_versions import create_tariff_version
from quotes.tests.quote_helpers import NOW, make_request, unit_fields
from quotes.tests.test_booking_service import (
    INSTRUCTIONS,
    case_1_request,
    example_4_request,
)

AT_0930 = datetime(2026, 11, 25, 15, 30, tzinfo=UTC)
DANA = {"name": "Dana Whitfield", "phone": "972-555-0142"}
MARCUS = {"name": "Marcus Bell", "phone": "404-555-0178"}
APPOINTMENT_MESSAGE = (
    "A phone number is required for the receiver when the quote includes a delivery appointment."
)


class BookingApiBase(APITestCase):
    """Fixes "now" (the time the API sees); the real clock is never read."""

    def setUp(self):
        self.now = AT_0930
        patcher = mock.patch("quotes.serializers.get_now", side_effect=lambda: self.now)
        patcher.start()
        self.addCleanup(patcher.stop)

    def book(self, quote, shipper=DANA, receiver=MARCUS, instructions=INSTRUCTIONS, **extra):
        body = {"shipper_contact": shipper, "receiver_contact": receiver, **extra}
        if instructions is not None:
            body["special_instructions"] = instructions
        return self.client.post(f"/api/quotes/{quote.pk}/bookings/", body, format="json")

    def cancel(self, booking_id, reason="Shipper cancelled"):
        body = {} if reason is None else {"reason": reason}
        return self.client.post(f"/api/bookings/{booking_id}/cancel/", body, format="json")


def example_3_request():
    return make_request(
        units=[
            unit_fields(weight_lb=1500, freight_class="70",
                        commodity_description="Automotive brake parts, boxed"),
            unit_fields(weight_lb=1000, freight_class="85",
                        commodity_description="Crated industrial pump assemblies"),
        ],
        origin_street="2200 Commerce Park Way",
        destination_street="Lot 7, 300 Harbor Ridge Rd", destination_city="Portland",
        destination_state="ME", destination_postal_code="04101",
        destination_location_type="construction_site",
        pickup_date=date(2026, 12, 1), appointment_requested=True,
    )  # fmt: skip


def example_5_request():
    return make_request(
        units=[
            unit_fields(quantity=3, weight_lb=400, freight_class="70",
                        commodity_description="Packaged hardware fasteners"),
            unit_fields(unit_type="crate", quantity=2, weight_lb=250, freight_class="70",
                        commodity_description="Replacement electric motor housings"),
            unit_fields(unit_type="drum", quantity=2, weight_lb=150, freight_class="150",
                        commodity_description="Food-grade vegetable oil, sealed drums"),
        ],
        origin_street="2200 Commerce Park Way",
        destination_street="4500 Distribution Ave", destination_city="Los Angeles",
        destination_state="CA", destination_postal_code="90001",
        pickup_date=date(2026, 12, 7),
    )  # fmt: skip


class Case1Tests(BookingApiBase):
    def test_a_normal_booking(self):
        quote = create_quotes(case_1_request(), NOW)[1]
        before = Quote.objects.values().get(pk=quote.pk)
        response = self.book(quote)
        self.assertEqual(response.status_code, 201, response.data)
        body = response.json()
        self.assertEqual(body["booking_number"], "BK-000001")
        self.assertRegex(body["booking_number"], r"^BK-\d{6}$")
        self.assertEqual(body["status"], "booked")
        self.assertEqual(body["confirmation_total"], "913.85")
        self.assertEqual(body["carrier"]["code"], "mid")
        self.assertEqual(body["quote"], quote.pk)
        self.assertEqual(body["shipper_contact"], {**DANA, "email": ""})
        self.assertEqual(body["receiver_contact"], {**MARCUS, "email": ""})
        self.assertEqual(body["special_instructions"], INSTRUCTIONS)
        self.assertIsNone(body["cancelled_at"])
        self.assertTrue(body["booked_at"].startswith("2026-11-25T09:30:00"))
        self.assertEqual(Booking.objects.count(), 1)
        self.assertEqual(Quote.objects.values().get(pk=quote.pk), before)

    def test_the_bill_of_lading_endpoint_serves_the_snapshot_without_a_price(self):
        quote = create_quotes(case_1_request(), NOW)[1]
        booking_id = self.book(quote).json()["id"]
        response = self.client.get(f"/api/bookings/{booking_id}/bill-of-lading/")
        self.assertEqual(response.status_code, 200)
        bol = response.json()
        self.assertEqual(bol["number"], "BK-000001")
        self.assertEqual(bol["booking_date"], "2026-11-25")
        self.assertEqual(bol["pickup_date"], "2026-11-30")
        self.assertEqual(bol["total_weight_lb"], 1600)
        self.assertEqual(bol["accessorials"], ["liftgate"])
        self.assertEqual(bol["consignee"]["street"], "418 Magnolia Ridge Dr SE")
        self.assertEqual(bol["special_instructions"], INSTRUCTIONS)
        self.assertNotIn("913.85", response.content.decode())
        for key in ("total", "price", "fees", "line_items"):
            self.assertNotIn(key, bol)

    def test_the_bill_of_lading_does_not_change_when_the_request_is_edited_later(self):
        quote = create_quotes(case_1_request(), NOW)[1]
        booking_id = self.book(quote).json()["id"]
        url = f"/api/bookings/{booking_id}/bill-of-lading/"
        before = self.client.get(url).json()
        request = quote.quote_request
        request.origin_street = "99 Somewhere Else"
        request.destination_city = "Elsewhere"
        request.save()
        request.handling_units.update(commodity_description="Changed")
        self.assertEqual(self.client.get(url).json(), before)

    def test_get_booking_returns_the_same_booking(self):
        quote = create_quotes(case_1_request(), NOW)[1]
        created = self.book(quote).json()
        self.assertEqual(self.client.get(f"/api/bookings/{created['id']}/").json(), created)


class Case2Tests(BookingApiBase):
    def setUp(self):
        super().setUp()
        self.quote = create_quotes(example_3_request(), NOW)[2]  # fast carrier
        self.instructions = (
            "Delivery appointment required; call receiver to schedule. "
            "Site gate code needed from receiver."
        )

    def test_2a_receiver_with_a_phone(self):
        response = self.book(
            self.quote,
            receiver={"name": "Priya Raman", "phone": "207-555-0163"},
            instructions=self.instructions,
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.json()["booking_number"], "BK-000001")
        self.assertEqual(response.json()["confirmation_total"], "1605.36")

    def test_2b_receiver_with_only_an_email_is_refused_and_the_retry_works(self):
        before = Quote.objects.values().get(pk=self.quote.pk)
        response = self.book(
            self.quote,
            receiver={"name": "Priya Raman", "email": "priya.raman@example.com"},
            instructions=self.instructions,
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {"receiver_contact": {"phone": [APPOINTMENT_MESSAGE]}})
        self.assertEqual(Booking.objects.count(), 0)
        self.assertEqual(Quote.objects.values().get(pk=self.quote.pk), before)

        retry = self.book(
            self.quote,
            receiver={"name": "Priya Raman", "phone": "207-555-0163"},
            instructions=self.instructions,
        )
        self.assertEqual(retry.status_code, 201)
        self.assertEqual(retry.json()["booking_number"], "BK-000001")

    def test_2c_phone_and_email_are_both_stored_and_on_the_bill_of_lading(self):
        receiver = {
            "name": "Priya Raman", "phone": "207-555-0163", "email": "priya.raman@example.com"
        }  # fmt: skip
        response = self.book(self.quote, receiver=receiver, instructions=self.instructions)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["receiver_contact"], receiver)
        bol = self.client.get(f"/api/bookings/{response.json()['id']}/bill-of-lading/").json()
        self.assertEqual(bol["consignee"]["phone"], "207-555-0163")
        self.assertEqual(bol["consignee"]["email"], "priya.raman@example.com")
        self.assertEqual(bol["accessorials"], ["appointment"])
        self.assertEqual(bol["total_weight_lb"], 2500)

    def test_a_request_without_an_appointment_accepts_an_email_only_receiver(self):
        quote = create_quotes(case_1_request(), NOW)[1]
        response = self.book(quote, receiver={"name": "Marcus Bell", "email": "m@example.com"})
        self.assertEqual(response.status_code, 201)


class Case3Tests(BookingApiBase):
    def test_seven_labels_with_the_expected_barcodes(self):
        quote = create_quotes(example_5_request(), NOW)[0]  # cheap carrier
        response = self.book(
            quote,
            receiver={"name": "Elena Ortiz", "phone": "323-555-0119"},
            instructions="Receiving dock hours 7:00 to 15:00.",
        )
        self.assertEqual(response.status_code, 201, response.data)
        booking_id = response.json()["id"]
        self.assertEqual(response.json()["booking_number"], "BK-000001")

        labels = self.client.get(f"/api/bookings/{booking_id}/labels/").json()["labels"]
        self.assertEqual(
            [(x["unit_number"], x["unit_type"], x["weight_lb"], x["freight_class"], x["barcode"])
             for x in labels],
            [
                (1, "pallet", 400, "70", "BK-000001-01-07"),
                (2, "pallet", 400, "70", "BK-000001-02-07"),
                (3, "pallet", 400, "70", "BK-000001-03-07"),
                (4, "crate", 250, "70", "BK-000001-04-07"),
                (5, "crate", 250, "70", "BK-000001-05-07"),
                (6, "drum", 150, "150", "BK-000001-06-07"),
                (7, "drum", 150, "150", "BK-000001-07-07"),
            ],
        )  # fmt: skip
        self.assertTrue(all(x["total_units"] == 7 for x in labels))
        first, last = labels[0], labels[-1]
        self.assertEqual(first["shipper_name"], "Dana Whitfield")
        self.assertEqual(first["shipper_city"], "Allen")
        self.assertEqual(first["consignee_name"], "Elena Ortiz")
        self.assertEqual(first["consignee_city"], "Los Angeles")
        self.assertEqual(first["destination_postal_code"], "90001")
        self.assertEqual(first["pickup_date"], "2026-12-07")
        self.assertEqual(first["commodity_description"], "Packaged hardware fasteners")
        self.assertEqual(last["commodity_description"], "Food-grade vegetable oil, sealed drums")
        self.assertEqual(first["carrier_name"], quote.carrier_name)


class Case4Tests(BookingApiBase):
    def test_4a_and_4b_the_boundary_pair_around_expiry(self):
        quote = create_quotes(example_4_request(), NOW)[1]
        luis = {"name": "Luis Herrera", "phone": "602-555-0126"}
        self.now = datetime(2026, 12, 2, 14, 10, tzinfo=UTC)
        refused = self.book(quote, receiver=luis, instructions="")
        self.assertEqual(refused.status_code, 409)
        self.assertEqual(refused.json(), {"detail": "The quote has expired."})
        self.assertEqual(Booking.objects.count(), 0)
        self.now = datetime(2026, 12, 2, 14, 9, tzinfo=UTC)
        self.assertEqual(self.book(quote, receiver=luis, instructions="").status_code, 201)

    def test_4c_pickup_date_passed(self):
        quote = create_quotes(case_1_request(), NOW)[1]
        before = Quote.objects.values().get(pk=quote.pk)
        self.now = datetime(2026, 11, 30, 16, 0, tzinfo=UTC)
        response = self.book(quote)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json(), {"detail": "The pickup date is no longer available."})
        self.assertEqual(Booking.objects.count(), 0)
        self.assertEqual(Quote.objects.values().get(pk=quote.pk), before)

    def test_4d_new_tariff_version(self):
        quote = create_quotes(case_1_request(), NOW)[1]
        create_tariff_version("RATES-2026-2", {}, created_at=datetime(2099, 1, 1, tzinfo=UTC))
        response = self.book(quote)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json(), {"detail": "The rates have changed since this quote."})
        self.assertEqual(Booking.objects.count(), 0)

    def test_4e_class_table_version_changed(self):
        quote = create_quotes(case_1_request(), NOW)[1]
        with mock.patch("quotes.models.CLASS_TABLE_VERSION", "NMFTA-2099-1"):
            response = self.book(quote)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(
            response.json(),
            {"detail": "The freight class table has changed since this quote."},
        )

    def test_4f_double_booking(self):
        quote = create_quotes(case_1_request(), NOW)[1]
        first = self.book(quote)
        self.assertEqual(first.status_code, 201)
        self.now = datetime(2026, 11, 25, 15, 31, tzinfo=UTC)
        second = self.book(quote)
        self.assertEqual(second.status_code, 409)
        self.assertEqual(second.json(), {"detail": "This quote has already been booked."})
        self.assertEqual(Booking.objects.count(), 1)
        self.assertEqual(
            self.client.get(f"/api/bookings/{first.json()['id']}/").json(), first.json()
        )

    def test_4g_4h_4i_cancel_then_cancel_again_then_rebook(self):
        quote = create_quotes(case_1_request(), NOW)[1]
        booking_id = self.book(quote).json()["id"]

        self.now = datetime(2026, 11, 25, 16, 0, tzinfo=UTC)  # 10:00 in Chicago
        cancelled = self.cancel(booking_id)
        self.assertEqual(cancelled.status_code, 200, cancelled.data)
        body = cancelled.json()
        self.assertEqual(body["status"], "cancelled")
        self.assertTrue(body["cancelled_at"].startswith("2026-11-25T10:00:00"))
        self.assertEqual(body["cancel_reason"], "Shipper cancelled")

        labels = self.client.get(f"/api/bookings/{booking_id}/labels/")
        self.assertEqual(labels.status_code, 409)
        self.assertEqual(
            labels.json(), {"detail": "Labels are not available for a cancelled booking."}
        )
        # The bill of lading is still available for a cancelled booking.
        self.assertEqual(
            self.client.get(f"/api/bookings/{booking_id}/bill-of-lading/").status_code, 200
        )

        again = self.cancel(booking_id, reason="Second try")
        self.assertEqual(again.status_code, 409)
        self.assertEqual(again.json(), {"detail": "This booking is already cancelled."})
        self.assertEqual(Booking.objects.get().cancel_reason, "Shipper cancelled")

        rebook = self.book(quote)
        self.assertEqual(rebook.status_code, 409)
        self.assertEqual(rebook.json(), {"detail": "This quote has already been booked."})
        self.assertEqual(Booking.objects.count(), 1)

    def test_another_quote_of_the_request_is_refused_then_allowed_after_cancelling(self):
        quotes = create_quotes(case_1_request(), NOW)
        first = self.book(quotes[1]).json()
        refused = self.book(quotes[0])
        self.assertEqual(refused.status_code, 409)
        self.assertEqual(
            refused.json(), {"detail": "This quote request already has an active booking."}
        )
        self.cancel(first["id"])
        self.assertEqual(self.book(quotes[0]).status_code, 201)


class ErrorTests(BookingApiBase):
    def setUp(self):
        super().setUp()
        self.quote = create_quotes(case_1_request(), NOW)[1]

    def test_booking_an_unknown_quote_is_404(self):
        response = self.client.post(
            "/api/quotes/99999/bookings/",
            {"shipper_contact": DANA, "receiver_contact": MARCUS},
            format="json",
        )
        self.assertEqual(response.status_code, 404)

    def test_an_unknown_booking_is_404_on_every_endpoint(self):
        for suffix in ("", "bill-of-lading/", "labels/"):
            self.assertEqual(self.client.get(f"/api/bookings/99999/{suffix}").status_code, 404)
        self.assertEqual(self.cancel(99999).status_code, 404)

    def test_both_contacts_are_required(self):
        response = self.client.post(f"/api/quotes/{self.quote.pk}/bookings/", {}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json(),
            {
                "shipper_contact": ["This field is required."],
                "receiver_contact": ["This field is required."],
            },
        )

    def test_a_contact_needs_a_name_and_a_phone_or_an_email(self):
        response = self.book(self.quote, shipper={"name": "", "phone": ""})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json(),
            {"shipper_contact": {
                "name": ["Enter a name."],
                "non_field_errors": ["Enter a phone number or an email address."],
            }},
        )  # fmt: skip

    def test_a_bad_phone_is_refused(self):
        response = self.book(self.quote, receiver={"name": "Marcus Bell", "phone": "12345"})
        self.assertEqual(response.status_code, 400)
        self.assertIn("phone", response.json()["receiver_contact"])

    def test_a_phone_is_stored_in_dashed_form(self):
        response = self.book(
            self.quote, receiver={"name": "Marcus Bell", "phone": "(404) 555 0178"}
        )
        self.assertEqual(response.json()["receiver_contact"]["phone"], "404-555-0178")

    def test_instructions_over_500_characters_are_refused_and_500_is_accepted(self):
        too_long = self.book(self.quote, instructions="x" * 501)
        self.assertEqual(too_long.status_code, 400)
        self.assertIn("special_instructions", too_long.json())
        self.assertEqual(Booking.objects.count(), 0)
        self.assertEqual(self.book(self.quote, instructions="x" * 500).status_code, 201)

    def test_instructions_are_optional(self):
        response = self.book(self.quote, instructions=None)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["special_instructions"], "")

    def test_a_body_that_is_not_an_object_is_400(self):
        response = self.client.post(
            f"/api/quotes/{self.quote.pk}/bookings/", ["nope"], format="json"
        )
        self.assertEqual(response.status_code, 400)

    def test_a_contact_that_is_not_an_object_is_400(self):
        response = self.book(self.quote, shipper="Dana")
        self.assertEqual(response.status_code, 400)
        self.assertIn("shipper_contact", response.json())

    def test_a_bad_body_is_reported_before_a_state_conflict(self):
        self.now = datetime(2026, 11, 30, 16, 0, tzinfo=UTC)  # pickup date passed: would be 409
        response = self.book(self.quote, receiver={"name": ""})
        self.assertEqual(response.status_code, 400)

    def test_cancelling_needs_a_reason(self):
        booking_id = self.book(self.quote).json()["id"]
        for reason in (None, "", "   "):
            response = self.cancel(booking_id, reason=reason)
            self.assertEqual(response.status_code, 400)
            self.assertEqual(response.json(), {"reason": ["Enter a reason for cancelling."]})
        self.assertEqual(Booking.objects.get().status, "booked")

    def test_a_cancel_reason_of_200_characters_is_accepted_and_201_is_refused(self):
        booking_id = self.book(self.quote).json()["id"]
        self.assertEqual(self.cancel(booking_id, reason="x" * 201).status_code, 400)
        self.assertEqual(self.cancel(booking_id, reason="x" * 200).status_code, 200)

    def test_a_bad_cancel_body_is_reported_before_already_cancelled(self):
        booking_id = self.book(self.quote).json()["id"]
        self.cancel(booking_id)
        self.assertEqual(self.cancel(booking_id, reason=None).status_code, 400)

    def test_methods_that_are_not_offered_are_405(self):
        booking_id = self.book(self.quote).json()["id"]
        url = f"/api/bookings/{booking_id}/"
        for method in ("put", "patch", "delete", "post"):
            self.assertEqual(getattr(self.client, method)(url, {}, format="json").status_code, 405)
        for suffix in ("bill-of-lading/", "labels/", "cancel/"):
            wrong = "post" if suffix != "cancel/" else "get"
            response = getattr(self.client, wrong)(f"{url}{suffix}")
            self.assertEqual(response.status_code, 405, suffix)
        self.assertEqual(self.client.get(f"/api/quotes/{self.quote.pk}/bookings/").status_code, 405)
        self.assertEqual(self.client.get("/api/bookings/").status_code, 404)
        self.assertEqual(Booking.objects.count(), 1)
