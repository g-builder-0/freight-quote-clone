# Slice 5 backend change 4: price preview, implementation plan

Status: APPROVED by Graham 2026-11-25 (Option A: "i choose option A if the preview has no pickup date"; "yes" to the shared lookup and the plan). Spec: `slice_05_price_preview.md` (cases and definition of done approved 2026-11-25: "i approve all 3"). Built; see the decisions rows.

## One thing the spec did not cover
`price_quote` in `quotes/pricing.py` requires a `pickup_date` and uses it only to compute the estimated delivery date (`add_business_days`). The preview has no pickup date and returns no delivery date (Graham: "include transit days only"). Two ways to deal with it:
- **Option A (recommended):** make `pickup_date` optional in `price_quote`; when it is left out, `estimated_delivery_date` is `None`. Every real quote still passes a date, so stored quotes do not change. One small test added to `test_pricing.py`.
- **Option B:** the preview passes a made-up date and throws the delivery date away. No change to `pricing.py`, but the preview would carry a date that means nothing.

## Steps (tests first, as in the earlier Slice 5 changes)
1. **Tests, red first.** New `quotes/tests/test_price_preview.py` for Cases 1 to 8 (the Case 4 test builds a real quote request and its quotes for Examples 1, 3 and 5 and compares them with the preview). In `test_pricing.py`, one test that `price_quote` with no pickup date returns no delivery date and the same prices (Option A). Run the suite and show the new tests failing; the existing tests must stay as they are.
2. **`quotes/pricing.py`** (Option A): `pickup_date` optional; `QuotePrice.estimated_delivery_date` becomes `date | None`.
3. **`quotes/services.py`: one shared pricing function.** Pull out of `create_quotes` the part that works out each unit's pricing class (the shipper's class, else the suggested class) and prices the shipment with every carrier of the current tariff version, in carrier order. `create_quotes` keeps everything that is about saving (the pickup-date check, the `Quote`, line item and quoted unit rows) and calls the shared function for the prices. A helper that returns the current tariff version or raises `NoTariffError` is shared the same way, so the 503 message cannot differ. The existing quote service, API, booking and pricing tests must pass unchanged; that is the proof that behaviour did not move.
4. **`quotes/serializers.py`:** a request serializer for the preview built from the models (so the ZIP check, location type choices, limits, whole-number rule and messages are the quote request's own and cannot drift), with a unit serializer for quantity, the three dimensions, weight and the optional class, and `allow_empty=False` on the units. A result serializer for one carrier's entry, reusing `QuoteLineItemSerializer` for the line items.
5. **`quotes/views.py` and `quotes/urls.py`:** `PricePreviewView` (POST only), at `path("price-preview/", ...)`. It validates, builds the units in memory (the same unsaved-`HandlingUnit` approach as the class preview, so the suggested class comes from the model), calls the shared function, and returns the note and the prices. `NoTariffError` becomes 503 with `{"detail": ...}` as in quote creation. Nothing is saved.
6. **README and docs:** one row in the README Endpoints table; spec and plan copied to `docs/slices/` by Graham; decisions rows drafted by the agent for `docs/decisions.md`.
7. **Checks:** `python manage.py test`, `ruff check .`, `ruff format --check .`, `makemigrations --check` (no model change, so no migration). Report test counts (the suite is 372 now).
8. **Delivery:** a patch against a baseline copy (verified with `git apply` on a copy), sent with the decisions rows; Graham applies, tests, deletes the patch, commits and pushes. The agent does not commit or push.

## Risks I will watch
- Refactoring `create_quotes` is the only change to existing behaviour. The three Slice 2 service tests that compare stored quotes with `price_quote` directly, and the booking tests that use quotes, are the guard.
- The preview must not touch the database for writes; Case 5 counts the rows to prove it.

## Questions for Graham
1. Option A or Option B for the pickup date?
2. Do you approve making the preview and `create_quotes` share the tariff-version lookup as well as the pricing step (so the 503 message exists in one place)?
3. Do you approve the plan?
