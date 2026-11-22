# Slice 2 Plan: Quote Engine and Carriers

Status: APPROVED by Graham 2026-11-22; steps 1-7 implemented and tested (226 tests). The spec
(`slice_02_quote_engine.md`) wins if the plan and spec ever disagree. Names marked "proposed" are the agent's
suggestions, not decisions. Budget: 2 working days.

## Approach
Same as Slice 1: build in small steps, rule modules first. The pricing rules take plain inputs (numbers, strings,
dates, simple tariff data), so Graham's five worked examples can be tested with no database and no web request.
Models, the command, serializers and views come after the rules are tested. Every expected value in a test is
Graham's hand-calculated number; the agent never invents one.

## Steps

### 1. Request flags (changes Slice 1)
- Add `liftgate_requested` and `appointment_requested` (boolean, default false) to `QuoteRequest`, with a new migration.
- Add both fields to the Slice 1 serializer (create and read). Existing requests stay valid.
- Tests: flags default to false; each can be set; fields appear in the response.
- Done when `manage.py test` still passes with all 77 Slice 1 tests.

### 2. Pricing rules (plain-input module, proposed `quotes/pricing.py`)
- Tariff data is passed in as plain objects (proposed frozen dataclasses: `CarrierTariffData` with minimum, fuel
  percentage, transit adjustment, weight-break rates and accessorial fees).
- Functions, each small and separately tested: `zone_gap` and `zone_factor` (first digit of each ZIP, 1.00 + 0.10 x gap);
  `class_multiplier` (class / 100, as Decimal, so 92.5 gives 0.925); `weight_break_rate` (ONE function that holds the
  weight-break lookup and the line-haul, so the rating-up rule can be added later); `line_haul` per class;
  `apply_minimum`; `fuel_amount` (percentage x line-haul after the minimum); `accessorial_fee(carrier, fee_type, end)`
  (ignores `end`); `apply_markup(carrier_cost)` (returns it unchanged); `transit_days` (1 + ceil(gap / 2) + adjustment, minimum 1).
- Each line item is rounded ROUND_HALF_UP to cents when created; the total is the sum of the rounded lines. Decimal only.
- Weights: unit weight x quantity; weight break from the total pounds; units of the same class combine into one line.
- Pricing class per unit: the supplied class if there is one, otherwise the suggested class.
- Tests: the five worked examples verbatim (every line item, total, transit days); the 1,000/999, 1,999/2,000 and
  499/500 lb boundaries; minimum applies and does not apply; liftgate and appointment each add exactly their fee and
  leave fuel unchanged; residential, limited access, construction site (limited access) and business dock, at each end;
  denser shipment gets a lower class and a lower line-haul than a bulky one of the same weight; `apply_markup` and the
  tariff calculation tested separately.

### 3. Business-day arithmetic (extends `quotes/pickup.py`)
- Add `add_business_days(start, n)` using `is_business_day` (weekends skipped, holidays ignored, pickup date is day 0).
- Tests: Example 1 (Mon 2026-11-30 + 3 = Thu 2026-12-03), Example 2 (Mon 2026-11-23 + 2 = Wed 2026-11-25), Example 3
  (Tue 2026-12-01 + 4 = Mon 2026-12-07), a span over a weekend, and Example 5 (Mon 2026-12-07 + 3 = Thu 2026-12-10).

### 4. Models and migrations
- Tariff tables (immutable once created): `TariffVersion` (label, `created_at`), `CarrierTariff`, `WeightBreakRate`,
  `AccessorialFee`. The current version is the one with the latest `created_at` (id breaks ties); no flag.
- Quote tables (immutable once created): `Quote` (request, carrier code and name, tariff version, `rate_table_version`
  text, `class_table_version`, total, transit days, estimated delivery date, `created_at`, `expires_at`) and
  `QuoteLineItem` (kind, description, source and reason, amount, order).
- Proposed: a small `QuotedUnit` table (quote, handling unit, class used) to snapshot the class used for each handling unit.
- Immutability: the models refuse to save changes to an existing row and refuse deletes; the admin shows tariff rows read-only.
- A data migration creates RATES-2026-1 with the approved tariff (31 rows).
- Tests: the seeded rows match the approved table exactly (every rate, minimum, fuel percentage, fee, adjustment, for all
  three carriers); saved quotes and tariff rows cannot be changed.

### 5. `create_tariff_version` command
- `python manage.py create_tariff_version <label> <change file>`: in one transaction, adds a `TariffVersion`, copies
  every row of the current version, applies the change file, saves.
- Proposed change-file format: JSON listing only the values to change, for example
  `{"mid": {"fees": {"liftgate": "90.00"}}}`. A value that does not exist makes the command fail and create nothing.
- Tests: 31 rows copied; only the named values differ; the old version is untouched; a bad change file creates nothing;
  after a new version exists, a quote made under the old version fails the booking check and new quotes use the new rates.

### 6. Quote service and booking check
- A `create_quotes(quote_request, now)` function (proposed `quotes/services.py`): re-checks the pickup date with
  `validate_pickup_date`, loads the current tariff version, prices the request with each carrier, and saves three
  quotes and their line items in one transaction. Each quote snapshots the class used per unit, `CLASS_TABLE_VERSION`,
  the tariff version, and `expires_at` = `created_at` + 7 days. Fixed carrier order: cheap and slow, mid, fast and pricey.
- `check_bookable(now)` on the quote returns OK or the reason: not expired, class table version current, tariff version
  current, pickup date still a business day after today (America/Chicago).
- The current time is passed in, so tests supply the clock.
- Tests: three quotes per call; lines sum exactly to the total; if one carrier is forced to fail nothing is saved; a
  second call creates three new quotes and leaves the first three unchanged; each of the four booking-check
  conditions, and a fresh quote passes; a past pickup date is rejected and saves nothing.

### 7. Serializers, views and URLs
- Routes: `POST /api/quote-requests/{id}/quotes/` (201, no body; 404 unknown request; 400 pickup date today or earlier),
  `GET /api/quote-requests/{id}/quotes/` (history, newest first), `GET /api/quotes/{id}/`. No update or delete (405).
- A quote response includes id, request, carrier, total as a two-decimal string, line items, transit days, estimated
  delivery date, `created_at`, `expires_at`, both version labels, the class used per unit, and `bookable` and
  `not_bookable_reason` (computed on each read, never stored).
- Tests: the happy path with a worked-example payload; 404 and 400 cases; history ordering; 405 on update and delete;
  `bookable` matches `check_bookable`; money is a string with two decimals.

### 8. Finish
- Run `python manage.py test`, `ruff check .` and `ruff format --check .`.
- Write a short report: what was built, what was tested, anything the agent had to ask or decide, anything it found
  ambiguous. Log each decision in `docs/decisions.md`. Do not edit `docs/intervention_log.md`.
- Add the Slice 2 simplifications to the README list (invented tariffs, zone factor, transit formula, one minimum per
  carrier, weight-break rating-up not built, no broker markup, no reweigh adjustment after booking).

## Time and cut line
Steps 1 to 3 are the pure-rule work and the highest value (about half a day). Steps 4 and 5 are the database tariff
(about a day, the biggest cost). Steps 6 and 7 are about half a day. If time runs short, the `create_tariff_version`
command (step 5) is the part to simplify first: the seeded RATES-2026-1 plus the version guard would still work, and
a new version could be created by a data migration instead.

## Questions for Graham
1. Approve the order of steps and the time estimate?
2. Approve the proposed names: `quotes/pricing.py`, `quotes/services.py`, `QuotedUnit`, and the JSON change-file format.
3. Is the command (step 5) the right thing to cut first if time runs short?
