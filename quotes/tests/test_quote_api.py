"""Slice 2 step 7: the quote endpoints."""

from datetime import UTC, date, datetime, timedelta
from unittest import mock

from rest_framework.test import APITestCase

from quotes.models import Quote
from quotes.tariff_versions import create_tariff_version
from quotes.tests.quote_helpers import NOW, example_1_request, make_request
from quotes.tests.test_api import request_payload, unit_payload


class QuoteApiBase(APITestCase):
    """Fixes "now" at NOW (Wednesday 2026-11-25, 08:10 in Chicago); the real clock is never read."""

    def setUp(self):
        self.now = NOW
        patcher = mock.patch("quotes.serializers.get_now", side_effect=lambda: self.now)
        patcher.start()
        self.addCleanup(patcher.stop)

    def quotes_url(self, request):
        return f"/api/quote-requests/{request.pk}/quotes/"

    def post_quotes(self, request):
        return self.client.post(self.quotes_url(request))


class CreateQuotesApiTests(QuoteApiBase):
    def test_post_creates_three_quotes_and_returns_201(self):
        response = self.post_quotes(example_1_request())
        self.assertEqual(response.status_code, 201, response.data)
        body = response.json()
        self.assertEqual(list(body), ["quotes"])
        self.assertEqual([q["carrier"]["code"] for q in body["quotes"]], ["cheap", "mid", "fast"])
        self.assertEqual(Quote.objects.count(), 3)

    def test_the_mid_quote_is_graham_worked_example_1_with_money_as_strings(self):
        mid = self.post_quotes(example_1_request()).json()["quotes"][1]
        self.assertEqual(mid["carrier"], {"code": "mid", "name": "Mid"})
        self.assertEqual(mid["total"], "913.85")
        self.assertEqual(
            [(i["kind"], i["description"], i["source"], i["reason"], i["amount"])
             for i in mid["line_items"]],
            [
                ("line_haul", "Line-haul, class 55", "", "", "314.16"),
                ("line_haul", "Line-haul, class 125", "", "", "238.00"),
                ("fuel", "Fuel (32%)", "", "", "176.69"),
                ("accessorial", "Residential delivery", "auto",
                 "residential delivery address", "100.00"),
                ("accessorial", "Liftgate", "requested", "requested by shipper", "85.00"),
            ],
        )  # fmt: skip
        self.assertEqual(mid["transit_days"], 3)
        self.assertEqual(mid["estimated_delivery_date"], "2026-12-03")

    def test_a_quote_carries_its_snapshot_and_expiry(self):
        mid = self.post_quotes(example_1_request()).json()["quotes"][1]
        self.assertEqual(mid["rate_table_version"], "RATES-2026-1")
        self.assertEqual(mid["class_table_version"], "NMFTA-2025-1")
        self.assertEqual(datetime.fromisoformat(mid["created_at"]), NOW)
        self.assertEqual(datetime.fromisoformat(mid["expires_at"]), NOW + timedelta(days=7))
        self.assertEqual([u["freight_class"] for u in mid["unit_classes"]], ["55", "125"])
        self.assertEqual(mid["quote_request"], Quote.objects.get(pk=mid["id"]).quote_request_id)

    def test_a_fresh_quote_is_bookable(self):
        for quote in self.post_quotes(example_1_request()).json()["quotes"]:
            self.assertIs(quote["bookable"], True)
            self.assertEqual(quote["not_bookable_reason"], "")

    def test_no_request_body_is_needed(self):
        response = self.client.post(self.quotes_url(example_1_request()), data=None)
        self.assertEqual(response.status_code, 201)

    def test_an_unknown_request_is_a_404(self):
        self.assertEqual(self.client.post("/api/quote-requests/9999/quotes/").status_code, 404)
        self.assertEqual(self.client.get("/api/quote-requests/9999/quotes/").status_code, 404)

    def test_a_pickup_date_that_is_today_or_earlier_is_a_400_and_saves_nothing(self):
        for pickup in (date(2026, 11, 25), date(2026, 11, 20), date(2026, 11, 28)):
            with self.subTest(pickup=pickup):
                response = self.post_quotes(make_request(pickup_date=pickup))
                self.assertEqual(response.status_code, 400, response.data)
                self.assertIn("pickup_date", response.json())
        self.assertEqual(Quote.objects.count(), 0)

    def test_the_quote_request_endpoints_return_the_new_flags(self):
        request = example_1_request()
        body = self.client.get(f"/api/quote-requests/{request.pk}/").json()
        self.assertIs(body["liftgate_requested"], True)
        self.assertIs(body["appointment_requested"], False)

    def test_end_to_end_a_request_created_through_the_api_can_be_quoted(self):
        with mock.patch("quotes.serializers.get_today", return_value=date(2026, 11, 25)):
            created = self.client.post(
                "/api/quote-requests/",
                request_payload(
                    units=[unit_payload(weight_lb=1000, freight_class="100")],
                    pickup_date="2026-11-30",
                    liftgate_requested=True,
                ),
                format="json",
            )
        self.assertEqual(created.status_code, 201, created.data)
        response = self.client.post(f"/api/quote-requests/{created.json()['id']}/quotes/")
        self.assertEqual(response.status_code, 201)
        for quote in response.json()["quotes"]:
            self.assertIn("Liftgate", [i["description"] for i in quote["line_items"]])


class QuoteHistoryApiTests(QuoteApiBase):
    def test_a_request_with_no_quotes_has_an_empty_history(self):
        response = self.client.get(self.quotes_url(example_1_request()))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"quotes": []})

    def test_history_is_newest_first_with_carrier_order_inside_each_call(self):
        request = example_1_request()
        self.post_quotes(request)
        self.now = NOW + timedelta(hours=2)
        self.post_quotes(request)
        quotes = self.client.get(self.quotes_url(request)).json()["quotes"]
        self.assertEqual(len(quotes), 6)
        self.assertEqual(
            [(datetime.fromisoformat(q["created_at"]), q["carrier"]["code"]) for q in quotes],
            [(NOW + timedelta(hours=2), c) for c in ("cheap", "mid", "fast")]
            + [(NOW, c) for c in ("cheap", "mid", "fast")],
        )

    def test_history_only_lists_the_quotes_of_that_request(self):
        mine, other = example_1_request(), make_request()
        self.post_quotes(mine)
        self.post_quotes(other)
        quotes = self.client.get(self.quotes_url(mine)).json()["quotes"]
        self.assertEqual({q["quote_request"] for q in quotes}, {mine.pk})

    def test_a_second_post_keeps_the_first_quotes(self):
        request = example_1_request()
        first = self.post_quotes(request).json()["quotes"]
        self.now = NOW + timedelta(hours=1)
        second = self.post_quotes(request).json()["quotes"]
        self.assertEqual(Quote.objects.count(), 6)
        self.assertFalse({q["id"] for q in first} & {q["id"] for q in second})
        for quote in first:
            self.assertEqual(
                self.client.get(f"/api/quotes/{quote['id']}/").json()["total"], quote["total"]
            )


class RetrieveQuoteApiTests(QuoteApiBase):
    def test_get_one_quote_returns_what_post_returned(self):
        posted = self.post_quotes(example_1_request()).json()["quotes"][1]
        response = self.client.get(f"/api/quotes/{posted['id']}/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), posted)

    def test_an_unknown_quote_is_a_404(self):
        self.assertEqual(self.client.get("/api/quotes/9999/").status_code, 404)

    def test_quotes_cannot_be_updated_or_deleted(self):
        quote_id = self.post_quotes(example_1_request()).json()["quotes"][1]["id"]
        url = f"/api/quotes/{quote_id}/"
        for method in ("put", "patch", "delete"):
            with self.subTest(method=method):
                response = getattr(self.client, method)(url, {"total": "1.00"}, format="json")
                self.assertEqual(response.status_code, 405)
        self.assertEqual(self.client.get(url).json()["total"], "913.85")

    def test_there_is_no_way_to_list_or_create_quotes_at_the_top_level(self):
        self.assertEqual(self.client.get("/api/quotes/").status_code, 404)
        self.assertEqual(self.client.post("/api/quotes/", {}, format="json").status_code, 404)

    def test_the_nested_path_does_not_allow_update_or_delete(self):
        url = self.quotes_url(example_1_request())
        for method in ("put", "patch", "delete"):
            with self.subTest(method=method):
                self.assertEqual(getattr(self.client, method)(url).status_code, 405)


class BookableFlagApiTests(QuoteApiBase):
    def setUp(self):
        super().setUp()
        # A pickup far enough away that the quote's own 7-day expiry is what runs out first.
        self.request = make_request(pickup_date=date(2026, 12, 14))
        self.quote_id = self.post_quotes(self.request).json()["quotes"][1]["id"]
        self.url = f"/api/quotes/{self.quote_id}/"

    def test_the_flag_matches_check_bookable_when_fresh(self):
        quote = Quote.objects.get(pk=self.quote_id)
        body = self.client.get(self.url).json()
        self.assertEqual(body["bookable"], quote.check_bookable(NOW).bookable)
        self.assertIs(body["bookable"], True)

    def test_an_expired_quote_reads_as_not_bookable_with_the_reason(self):
        self.now = NOW + timedelta(days=8)
        body = self.client.get(self.url).json()
        quote = Quote.objects.get(pk=self.quote_id)
        self.assertIs(body["bookable"], False)
        self.assertEqual(body["not_bookable_reason"], quote.check_bookable(self.now).reason)
        self.assertIn("expired", body["not_bookable_reason"])

    def test_a_quote_reads_as_not_bookable_after_the_rates_change(self):
        create_tariff_version("RATES-2026-2", {}, created_at=datetime(2099, 1, 1, tzinfo=UTC))
        body = self.client.get(self.url).json()
        self.assertIs(body["bookable"], False)
        self.assertIn("rates have changed", body["not_bookable_reason"])

    def test_the_flag_is_not_stored(self):
        self.assertNotIn("bookable", {f.name for f in Quote._meta.get_fields()})
        self.assertNotIn("not_bookable_reason", {f.name for f in Quote._meta.get_fields()})

    def test_the_flag_follows_the_clock_so_the_same_quote_can_change(self):
        self.assertIs(self.client.get(self.url).json()["bookable"], True)
        self.now = NOW + timedelta(days=7, seconds=1)
        self.assertIs(self.client.get(self.url).json()["bookable"], False)
