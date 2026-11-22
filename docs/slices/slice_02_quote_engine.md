# Slice 2: Quote Engine and Carriers

Status: ACCEPTED by Graham 2026-11-21 (all open questions resolved; every suggestion that was marked PROPOSED was accepted). The carriers, tariffs, accessorials, pricing rules, expiry, versioning and worked examples are Graham's decisions; Goal, Models, Validation rules, API, Definition of done and Open questions were drafted by the agent from `docs/decisions.md` and the Slice 1 spec and then reviewed and accepted by Graham. Carried-forward requirements are in `slice_02_notes.md`. Implementation starts only after Graham approves the Slice 2 plan.

## Goal

Given a saved QuoteRequest, one API call creates one immutable Quote for each of the three simulated carriers (cheap and slow, mid, fast and pricey). Each quote has a line-item breakdown that sums exactly to its total, a transit estimate, an expiry time, and a snapshot of the class table and rate table versions that priced it. All three quotes are saved together in one transaction. A quote can be booked only while it is unexpired and both table versions are current. The booking itself is built in Slice 3; Slice 2 provides the check that Slice 3 calls (see Open questions).

No real carrier is called. All tariffs are illustrative (see "Carriers and tariffs").

## Models

Names accepted 2026-11-21; the field lists follow the decisions already made.

**Carriers and tariffs** (agreed 2026-11-19: stored in the database). There are three simulated carriers behind one common interface; the interface and the formulas are code, and the tariff numbers are database rows in four tables. Published rows are never edited.
- `TariffVersion`: the version label (for example "RATES-2026-1") and `created_at`. The current version is the one with the latest `created_at` (id breaks ties); agreed 2026-11-20. There is no flag and no draft state, so no row ever changes after it is created. A version is created complete, in one transaction, and is live immediately; changes are prepared outside production until they are meant to be used.
- `CarrierTariff`: belongs to one `TariffVersion`; carrier code, carrier name, minimum charge, fuel percentage, transit adjustment in days.
- `WeightBreakRate`: belongs to one `CarrierTariff`; from weight, to weight (empty for "and up"), rate per cwt at class 100.
- `AccessorialFee`: belongs to one `CarrierTariff`; fee type (residential, limited access, liftgate, appointment) and amount.
- A rate change creates a new `TariffVersion` and copies every row below it, then the copy is edited. The earlier version and its rows stay as history. A version's label is stored once, on `TariffVersion`; the other tables reach it through their parent.
- Agreed 2026-11-21: the first version, RATES-2026-1 with the approved tariff, is created by a data migration. Every later version is created by a management command, `create_tariff_version <label> <change file>`. In one transaction it adds a new `TariffVersion`, copies every row of the current version into it (31 rows: 3 carriers x (5 rates + 4 fees + 1 carrier row), plus the version row), applies the change file, and saves. The change file is a small file prepared in git that lists only the values to change (for example `mid.liftgate = 90`). Versions are full copies, not chains of changes, and the old version's rows are never touched. The model refuses to change rows of an existing version, and the admin shows them read-only.

**QuoteRequest** (Slice 1 model, changed): add two yes/no fields, `liftgate_requested` and `appointment_requested`, both defaulting to false so existing requests stay valid. This needs a new migration.

**Quote** (new). One row per carrier per quote call. Immutable once created.
- the QuoteRequest it prices (foreign key)
- carrier code and carrier name
- `carrier_cost` is NOT stored in Slice 2; one `price` (the total) is stored (see "Broker markup seam")
- `total`: Decimal, equal to the sum of its line items
- `class_table_version`: the label in force when the quote was created; and the `TariffVersion` that priced it (foreign key), with its label also copied as `rate_table_version` so the quote reads on its own
- `transit_days` and `estimated_delivery_date`
- `created_at` and `expires_at` (`created_at` + 7 days)
- the freight class used for each handling unit, snapshotted at creation: the supplied class if the shipper gave one, otherwise the suggested class (agreed 2026-11-19)

**QuoteLineItem** (new). Belongs to one Quote; ordered.
- `kind`: line-haul, fuel or accessorial
- `description`: for example "Line-haul, class 55", "Fuel (32%)", "Residential delivery", "Liftgate"
- `source`: for accessorials, `auto` (with the reason, for example "residential delivery address") or `requested`; empty for line-haul and fuel
- `amount`: Decimal, rounded half up to cents

**Immutability.** The API offers no update or delete for quotes or line items. The model also refuses to save changes to an existing quote, so a bug in a view cannot edit one. A re-quote creates three new quotes; the old ones stay as history.

**Money** is `Decimal` everywhere. In JSON, money is a string with two decimals (for example "913.85"), like density in Slice 1.

## Carriers and tariffs (all numbers illustrative)

Approved by Graham 2026-11-17. All numbers are illustrative and are not real carrier tariffs. The initial tariff version is labelled `"RATES-2026-1"` and is stored in the database (see Models).

There are three simulated carriers behind a common interface. Rates are dollars per cwt (hundred pounds) at class 100.

| | Cheap and slow | Mid | Fast and pricey |
|---|---|---|---|
| Under 500 lb | $42 | $48 | $56 |
| 500 to 999 lb | $35 | $40 | $46 |
| 1,000 to 1,999 lb | $30 | $34 | $39 |
| 2,000 to 4,999 lb | $25 | $28 | $32 |
| 5,000 lb and up | $20 | $23 | $26 |
| Minimum charge | $75 | $90 | $110 |
| Fuel surcharge | 28% | 32% | 35% |
| Residential fee | $85 | $100 | $120 |
| Limited-access fee | $95 | $120 | $150 |
| Liftgate fee | $65 | $85 | $110 |
| Appointment fee | $40 | $50 | $60 |
| Transit adjustment | +1 day | 0 | -1 day |

Shared by all carriers:

- **Class multiplier** = class / 100 (0.500 for class 50 up to 5.000 for class 500; class 92.5 is 0.925 and class 77.5 is 0.775).
- **Zone gap** = absolute difference between the first digits of the origin and destination ZIP codes (0 to 9). **Zone factor** = 1.00 + 0.10 x zone gap.
- **Transit days** (business days from the pickup date) = 1 + ceil(zone gap / 2) + carrier adjustment, minimum 1. The delivery date is an estimate.
- The README must say that the tariffs, the zone factor and the transit formula are invented simplifications, that no real carrier rates or lane tables are used, and that there is one minimum per carrier where real tariffs have several.

## Accessorials

(Graham to write the full list. Agreed so far, 2026-11-13:)

### Automatic location-type fees (agreed 2026-11-13)

- Location type is checked separately for the origin (pickup) and the destination (delivery). Each address has one location type, so each end triggers at most one automatic fee, and a quote has at most two automatic fee lines.
- Residential address: residential fee. Limited access address: limited-access fee. Construction site: treated as limited access (limited-access fee). Business dock: no automatic fee.
- Each automatic fee is its own line item inside the quote total, naming the end, for example "Residential pickup" or "Limited-access delivery".
- Every accessorial line item carries a source: `auto` (with the reason, for example "residential delivery address") or `requested` (the shipper asked for it). The front end uses `auto` lines to show a notice before the shipper books.
- Liftgate is not automatic. The shipper chooses it, because the location type does not tell us whether a site has a dock.

### Requested accessorials (agreed 2026-11-17)

- The shipper can request two accessorials: **liftgate** and **appointment**. Each is a yes/no flag on the quote request (new fields on the Slice 1 `QuoteRequest`, with a new migration; existing requests default to no).
- Each requested accessorial is a fee per carrier and appears as its own line item with the source `requested` ("requested by shipper").
- Appointment is a flag and a fee only. There is no date or time-of-day scheduling, because the carrier arranges the appointment with the receiver. The delivery contact the carrier needs is collected in Slice 3 with the bill of lading details.
- Proposed illustrative fees (pending approval of the full tariff): liftgate $65 / $85 / $110 and appointment $40 / $50 / $60 for the cheap, mid and fast carriers.
- Test from the build plan: adding a liftgate raises the total by exactly the liftgate fee. The same must hold for appointment.

### Accessorial fee lookup seam (agreed 2026-11-13; per-end pricing deferred)

- Each carrier has one amount per fee type (residential, limited access), charged the same at pickup and at delivery in Slice 2.
- Fees are looked up through one function, `accessorial_fee(carrier, fee_type, end)`, where `end` is pickup or delivery. In Slice 2 it ignores `end`.
- Pricing the two ends differently later means: tariff data with a pickup amount and a delivery amount per fee, a change to this function only, a new tariff version, and new worked examples and tests. The line-item shape and the API do not change, and existing quotes are unaffected because each stores its own line-item amounts.

## Pricing rules

Order of calculation (agreed 2026-11-14 to 2026-11-17):

1. Weight break: chosen from the total weight of the whole shipment.
2. Line-haul: for each class in the shipment, (weight of that class / 100) x the carrier's rate at that weight break x class multiplier x zone factor. Handling units of the same class may be combined. Each class is priced at its own multiplier and the results are summed.
3. Minimum: if the summed line-haul is below the carrier's minimum, it becomes the minimum.
4. Fuel: ONE fuel line item = the carrier's fuel percentage x the whole line-haul from step 3 (fuel is added on top of the minimum), rounded half up to cents. It is not calculated per class. Fuel is not applied to accessorials.
5. Accessorials: automatic location-type fees and requested fees, each a separate line item.
6. Total = line-haul + fuel + accessorials.

Rounding (agreed 2026-11-17): `Decimal` throughout; each line item rounded half up to cents (ROUND_HALF_UP) when it is created; the total is the sum of the rounded line items, so the lines always sum exactly to the total.

### Weight-break rating-up rule: not built (agreed 2026-11-16; may be added later)

- Slice 2 prices each shipment at its actual total weight. It does NOT bill at the next weight break's weight when that is cheaper (for example 1,800 lb billed as 2,000 lb).
- Known consequence, to be stated in the README: with the mid carrier's class 100 rates, 1,999 lb costs 19.99 x $34 = $679.66 while 2,000 lb costs 20 x $28 = $560.00, so a slightly heavier shipment can cost less.
- Seam: the line-haul calculation, including the weight-break lookup, is in ONE function. No weight-break logic is scattered elsewhere.
- Adding the rule later means: a change to that function, a new tariff version, and new worked examples for shipments just below a break. Open question for that time: for shipments with several classes, which class the extra (deficit) weight is assigned to.

### Broker markup seam (agreed 2026-11-12; markup itself deferred)

- Each carrier's tariff calculation produces a **carrier cost**. It is named `carrier_cost` in code and tests, never "price".
- The carrier cost passes through a single function, `apply_markup(carrier_cost)`, which in Slice 2 returns the carrier cost unchanged (a 0% markup). Its result is the customer **price**, which is the number stored on the quote and shown to the shipper.
- No markup rate, setting or column is added in Slice 2. Quotes store one price only.
- Adding the markup later means: a migration that adds a `carrier_cost` column to quotes (existing rows get `carrier_cost = price`), a markup setting that is snapshotted on each quote, and a change to `apply_markup` only. The tariff code and the 0% worked examples must not need to change.
- Tests call the tariff function and `apply_markup` separately, so the seam is covered.

## Quote validity and expiry

- A quote is valid for 7 calendar days from its creation time: `expires_at` = `created_at` + 7 days (agreed 2026-11-13).
- After `expires_at` the quote cannot be booked. A re-quote creates a new quote; the expired one stays as history.
- The expiry is measured from creation, not from the pickup date, so a quote for a pickup weeks away can expire before the pickup. The API returns `expires_at`, and the front end must show the expiry time visibly (agreed 2026-11-13).

## Versioning (class table and rate table)

- `CLASS_TABLE_VERSION` (from Slice 1) identifies the density-to-class table. The tariff version (the `TariffVersion` label, for example RATES-2026-1; agreed 2026-11-16, and stored in the database from 2026-11-19) identifies the rate table: each carrier's rates by weight break, minimum charge, fuel percentage, and accessorial fees. These are two separate labels, and neither is the version of the application.
- Every quote stores both labels as they were when it was created.
- Booking is rejected if either stored label differs from the current one. The shipper must request a new quote; the old quote stays as history.
- Any change to the rate table data creates a new `TariffVersion`; published versions are never edited.
- Agreed 2026-11-21: the formulas stay in code (class multiplier = class / 100, zone factor = 1.00 + 0.10 x zone gap, transit formula, order of calculation). A code change to a formula ships together with a new `TariffVersion` (a data migration, or the `create_tariff_version` command with a change file that changes nothing else), so quotes priced under the old formula fail the booking check; the affected worked examples are updated in the same change.

## Validation rules

Inputs and rules for creating quotes (all from decisions already made or accepted by Graham).

- The QuoteRequest must exist; otherwise the API returns 404.
- Handling-unit rules (whole numbers, size and weight limits, classes, NMFC format) and address rules are the Slice 1 rules, unchanged. They are checked when the request is created, not again when it is quoted. The one exception is the pickup date, which is checked again (next two rules).
- Pickup date at quote time (agreed 2026-11-19): creating quotes is rejected with a 400 if the request's pickup date is not a business day strictly after today (America/Chicago), using the Slice 1 `validate_pickup_date` function. The shipper must create a new request with a new date.
- `liftgate_requested` and `appointment_requested` must be true or false. Omitted means false.
- Pricing class (agreed 2026-11-19): the supplied class if present, otherwise the suggested class from the current class table. Tests must cover both cases, and a case where the two disagree.
- The zone gap uses the first digit of each postal code, so ZIP+4 values work the same as 5-digit ZIPs.
- Weights (agreed 2026-11-19): a handling unit's weight counts as unit weight x quantity (weight in Slice 1 is for ONE unit and quantity is the number of identical units). The weight break comes from the total pounds of the whole shipment, which is the sum of unit weight x quantity over all handling units (not the sum of the quantities). The line-haul weight for a class is the same sum over the handling units of that class. Units of the same class are combined into one line-haul line item. Worked example 5 tests this.
- Transit days are counted in business days starting from the pickup date (the pickup date is day 0). The delivery date is an estimate. Weekends are skipped; holidays are ignored, using the same `is_business_day` function as Slice 1.
- Each line item is rounded half up to cents when it is created, and the total is the sum of the rounded lines.
- A quote can be booked only if all of these hold: the current time is before `expires_at`; its `class_table_version` equals the current `CLASS_TABLE_VERSION`; the `TariffVersion` that priced it is the current tariff version; and the request's pickup date is still a business day strictly after today (agreed 2026-11-19). Otherwise booking is rejected with a message saying which check failed, and the shipper must request a new quote.
- Where the check lives (agreed 2026-11-21): Slice 2 builds and tests it as a function on the quote (proposed name `check_bookable(now)`) that returns OK or the reason it fails; Slice 3 calls it before creating a booking. It covers the four conditions above.
- The current time is passed into the quote and booking-check functions, as `today` is in Slice 1, so tests never depend on the real clock.

## Worked examples (hand-calculated by Graham; used verbatim as test expectations)

Source: Graham's spreadsheet `worked_examples_for_Freightquote.xlsx`, sheet "slice 2". Amounts were checked by the agent. Example 1's estimated delivery date (Thursday 2026-12-03) was added by the agent and confirmed by Graham on 2026-11-21.

### Example 1: mid carrier, two classes, one automatic fee, one requested fee

Request: origin 75002 (Allen, TX), business dock; destination 30301 (Atlanta, GA), residential; pickup Monday 2026-11-30; a pallet of 1,200 lb at class 55 and a crate of 400 lb at class 125; liftgate requested; appointment not requested.

| Step | Result |
|---|---|
| Zone gap and factor | gap 7 - 3 = 4; factor 1.00 + 0.10 x 4 = 1.40 |
| Total weight and break | 1,200 + 400 = 1,600 lb; the 1,000 to 1,999 lb tier, $34 per cwt for the mid carrier |
| Minimum | $552.16 is above the $90 minimum, so it does not apply |
| Transit | 1 + ceil(4 / 2) + 0 = 3 business days; estimated delivery Thursday 2026-12-03 |

| Quote line item | Source | Calculation | Amount |
|---|---|---|---|
| Line-haul, class 55 | | 12 cwt x $34 x 0.55 x 1.40 | $314.16 |
| Line-haul, class 125 | | 4 cwt x $34 x 1.25 x 1.40 | $238.00 |
| Fuel (32%) | | 0.32 x ($314.16 + $238.00 = $552.16) = 176.6912 | $176.69 |
| Residential delivery | auto (residential delivery address) | mid carrier fee | $100.00 |
| Liftgate | requested | mid carrier fee | $85.00 |
| **Total** | | $552.16 + $176.69 + $100.00 + $85.00 | **$913.85** |

### Example 2: cheap and slow carrier, minimum charge applies, no accessorials

Request: origin 75002 (Allen, TX), business dock; destination 75201 (Dallas, TX), business dock; pickup Monday 2026-11-23; one pallet of 150 lb at class 100; no liftgate, no appointment.

| Step | Result |
|---|---|
| Zone gap and factor | gap 7 - 7 = 0; factor 1.00 + 0.10 x 0 = 1.00 |
| Total weight and break | 150 lb; the under 500 lb tier, $42 per cwt for the cheap and slow carrier |
| Minimum | $63.00 is below the $75 minimum, so the minimum applies and the line-haul becomes $75.00 |
| Transit | 1 + ceil(0 / 2) + 1 = 2 business days; estimated delivery Wednesday 2026-11-25 |

| Quote line item | Source | Calculation | Amount |
|---|---|---|---|
| Line-haul (minimum applied) | | 1.5 cwt x $42 x 1.00 x 1.00 = $63.00, raised to the $75 minimum | $75.00 |
| Fuel (28%) | | 0.28 x $75.00 (fuel applies after the minimum) | $21.00 |
| **Total** | | $75.00 + $21.00 | **$96.00** |

### Example 3: fast and pricey carrier, large zone gap, two classes, one automatic fee, one requested fee

Request: origin 75002 (Allen, TX), business dock; destination 04101 (Portland, ME), construction site; pickup Tuesday 2026-12-01; one pallet of 1,500 lb at class 70 and one pallet of 1,000 lb at class 85; liftgate not requested; appointment requested.

| Step | Result |
|---|---|
| Zone gap and factor | gap 7 - 0 = 7; factor 1.00 + 0.10 x 7 = 1.70 |
| Total weight and break | 1,500 + 1,000 = 2,500 lb; the 2,000 to 4,999 lb tier, $32 per cwt for the fast and pricey carrier |
| Minimum | $1,033.60 is above the $110 minimum, so it does not apply |
| Transit | 1 + ceil(7 / 2) - 1 = 4 business days; estimated delivery Monday 2026-12-07 (weekends skipped) |

| Quote line item | Source | Calculation | Amount |
|---|---|---|---|
| Line-haul, class 70 | | 15 cwt x $32 x 0.70 x 1.70 | $571.20 |
| Line-haul, class 85 | | 10 cwt x $32 x 0.85 x 1.70 | $462.40 |
| Fuel (35%) | | 0.35 x ($571.20 + $462.40 = $1,033.60) = 361.76 | $361.76 |
| Limited access | auto (construction site at destination) | fast carrier fee | $150.00 |
| Appointment | requested | fast carrier fee | $60.00 |
| **Total** | | $1,033.60 + $361.76 + $150.00 + $60.00 | **$1,605.36** |

### Example 4: mid carrier, weight-break edge at exactly 1,000 lb, no accessorials

Request: origin 75002 (Allen, TX), business dock; destination 85001 (Phoenix, AZ), business dock; pickup Thursday 2026-12-03; one pallet of 1,000 lb at class 100; no liftgate, no appointment.

This example pins down the tier boundary: exactly 1,000 lb belongs to the 1,000 to 1,999 lb tier, and 999 lb belongs to the 500 to 999 lb tier. Tests must cover both sides of each tier boundary.

| Step | Result |
|---|---|
| Zone gap and factor | gap |7 - 8| = 1; factor 1.00 + 0.10 x 1 = 1.10 |
| Total weight and break | 1,000 lb; the 1,000 to 1,999 lb tier, $34 per cwt for the mid carrier |
| Minimum | $374.00 is above the $90 minimum, so it does not apply |
| Transit | 1 + ceil(1 / 2) + 0 = 2 business days; estimated delivery Monday 2026-12-07 |

| Quote line item | Source | Calculation | Amount |
|---|---|---|---|
| Line-haul, class 100 | | 10 cwt x $34 x 1.00 x 1.10 | $374.00 |
| Fuel (32%) | | 0.32 x $374.00 | $119.68 |
| **Total** | | $374.00 + $119.68 | **$493.68** |

### Example 5: cheap and slow carrier, quantities above 1, three handling-unit lines, two classes

Request: origin 75002 (Allen, TX), business dock; destination 90001 (Los Angeles, CA), business dock; pickup Monday 2026-12-07; line 1: 3 pallets of 400 lb each at class 70; line 2: 2 crates of 250 lb each at class 70; line 3: 2 drums of 150 lb each at class 150; no liftgate, no appointment.

This example tests that weight counts as unit weight x quantity, and that lines of the same class are combined into one line-haul line item. If quantities were ignored, the total would be 400 + 250 + 150 = 800 lb, which is a different weight break.

| Step | Result |
|---|---|
| Zone gap and factor | gap |9 - 7| = 2; factor 1.00 + 0.10 x 2 = 1.20 |
| Total weight and break | 3 x 400 + 2 x 250 + 2 x 150 = 1,200 + 500 + 300 = 2,000 lb; the 2,000 to 4,999 lb tier, $25 per cwt for the cheap and slow carrier |
| Class weights | class 70: 1,200 + 500 = 1,700 lb (17 cwt); class 150: 300 lb (3 cwt) |
| Minimum | $492.00 is above the $75 minimum, so it does not apply |
| Transit | 1 + ceil(2 / 2) + 1 = 3 business days; estimated delivery Thursday 2026-12-10 |

| Quote line item | Source | Calculation | Amount |
|---|---|---|---|
| Line-haul, class 70 | | 17 cwt x $25 x 0.70 x 1.20 | $357.00 |
| Line-haul, class 150 | | 3 cwt x $25 x 1.50 x 1.20 | $135.00 |
| Fuel (28%) | | 0.28 x ($357.00 + $135.00 = $492.00) | $137.76 |
| **Total** | | $492.00 + $137.76 | **$629.76** |

## API

Paths and shapes agreed 2026-11-21; the one-call, one-quote-per-carrier behaviour was decided 2026-11-12. No authentication in Slice 2 (accounts are a Slice 5 stretch item).

| Method and path | Purpose |
|---|---|
| `POST /api/quote-requests/{id}/quotes/` | Create the three quotes for this request in one transaction. Returns 201 with a `quotes` list of three quotes. No body is needed. |
| `GET /api/quote-requests/{id}/quotes/` | List every quote ever made for this request, newest first (history, including expired quotes). |
| `GET /api/quotes/{id}/` | One quote with its line items. |

- No update or delete on quotes (405). Calling the POST again creates three new quotes; the earlier ones are kept.
- If any carrier calculation fails, nothing is saved and the call returns an error (one transaction).
- If the request's pickup date is today or earlier, the call returns 400 and nothing is saved.
- The three quotes come back in a fixed order (cheap and slow, mid, fast and pricey); the front end sorts and compares.
- A quote in JSON includes: `id`, `quote_request`, `carrier` (code and name), `total`, `line_items` (kind, description, source and reason, amount), `transit_days`, `estimated_delivery_date`, `created_at`, `expires_at`, `class_table_version`, `rate_table_version`, the class used for each handling unit, and `bookable` and `not_bookable_reason`. The last two are computed on each read by `check_bookable(now)` and are never stored; they are for the front end only (to disable the Book button and explain why). The booking endpoint in Slice 3 calls the same check and is the real enforcement. The front end must show `expires_at` visibly, and must show the reason for each `auto` line before the shipper books.
- The Slice 1 QuoteRequest endpoints gain the two new boolean fields in requests and responses.

## Definition of done

Slice 2 is done when `python manage.py test`, `ruff check .` and `ruff format --check .` all pass, the migration is applied, and these tests exist and pass:

- Each of the five worked examples above, used verbatim: every line item, the total, the transit days, the delivery date, and the weight break and minimum steps. Together they cover all three carriers.
- The lines of every quote add up exactly to its total.
- Adding a liftgate raises the total by exactly the carrier's liftgate fee; the same for appointment. Fuel does not change.
- The 1,000 lb and 999 lb boundary: 1,000 lb uses the 1,000 to 1,999 lb rate and 999 lb uses the 500 to 999 lb rate; also the 1,999 and 2,000 lb and the 499 and 500 lb boundaries.
- A denser shipment gets a lower class and a lower line-haul than a bulky shipment of the same weight (build plan test).
- Automatic fees: residential, limited access, construction site (charged as limited access) and business dock (no fee), at each end, with the correct `auto` source and reason.
- One POST creates exactly three quotes; if one carrier calculation is forced to fail, no quote is saved.
- A second POST creates three new quotes and leaves the first three unchanged.
- Quotes cannot be updated or deleted through the API, and the model refuses to change a saved quote.
- `bookable` and `not_bookable_reason` in a quote response match `check_bookable(now)`: a fresh quote reads as bookable; an expired quote reads as not bookable with the reason.
- Booking check: an expired quote is rejected; a quote whose class table version differs is rejected; a quote whose rate table version differs is rejected; a fresh quote passes. The tests supply the clock.
- Pickup date: creating quotes for a request whose pickup date is today, in the past or on a weekend returns 400 and saves nothing; booking a quote whose pickup date has since become today or earlier is rejected even though the quote has not expired and the versions match. The tests supply the clock.
- `apply_markup` and the tariff calculation are tested separately, and `accessorial_fee` is tested with both ends giving the same amount.
- The seeded RATES-2026-1 matches the approved tariff table exactly (every rate, minimum, fuel percentage, fee and transit adjustment, for all three carriers).
- Rows of a published tariff version cannot be changed; the `create_tariff_version` command copies every row (31 rows for the seeded tariff), applies only the named changes, and leaves the old version untouched. If the change file names a value that does not exist, nothing is created.
- After a new tariff version is created, a quote made under the old version is rejected by the booking check, and new quotes use the new rates.
- Every decision made while building is logged in `docs/decisions.md`.
- The README lists the simplifications: invented tariffs, the zone factor, the transit formula, one minimum per carrier, the weight-break rating-up rule not built, and no broker markup.

## Out of scope

- The weight-break rating-up rule (see Pricing rules). The README must list it as a known simplification and say it can be added later.
- Broker markup (only the seam is built), per-end accessorial pricing, real carriers or real tariffs, booking and the bill of lading (Slice 3), and accounts.

## Open questions

All questions below are resolved (2026-11-21).

1. RESOLVED 2026-11-19 (Graham chose option A): a handling unit is priced with the supplied class if there is one, otherwise the suggested class, and the class used is snapshotted on the quote. See `docs/decisions.md`. Alternatives rejected: always use the suggested class; reject the request when the two classes disagree. Reclassification by the carrier after the fact is not built (README must say so).
2. RESOLVED 2026-11-19 (Graham chose option A): weight counts as unit weight x quantity, the weight break uses the total pounds, and a fifth worked example with quantities above 1 is added. See `docs/decisions.md`.
3. RESOLVED 2026-11-19 (Graham chose to re-check at quote time and also at booking): see Validation rules and `docs/decisions.md`.
4. RESOLVED 2026-11-19 (Graham chose the database): see Models and `docs/decisions.md`. The agent had recommended code for schedule reasons.
5. RESOLVED 2026-11-21 (Graham chose option A): Slice 2 builds and tests the booking check; Slice 3 calls it. See Validation rules and `docs/decisions.md`.
6. RESOLVED 2026-11-21 (Graham accepted the nested paths and the `bookable` fields): see API and `docs/decisions.md`.
7. RESOLVED 2026-11-21: Graham confirmed Thursday 2026-12-03 for Example 1.
8. RESOLVED 2026-11-20 (Graham chose the latest `created_at`, no draft state): see Models and `docs/decisions.md`.
9. RESOLVED 2026-11-21 (Graham chose the management command with a change file): see Models and `docs/decisions.md`.
10. RESOLVED 2026-11-21 (Graham chose option A: numbers are data, formulas are code): see Versioning and `docs/decisions.md`.
