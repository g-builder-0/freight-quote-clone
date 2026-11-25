# Slice 5 backend change 4: price preview

Status: APPROVED by Graham 2026-11-25 (rules; shape, worked examples and definition of done: "i approve all 3"). Plan in `slice_05_price_preview_plan.md` approved 2026-11-25 (Option A for the pickup date; "yes" to the shared lookup and the plan). Built; see the decisions rows.

## Goal
Graham's decision 5 (running totals while the shopper types): "I like the live updates feature because it gives the customer clarity about the total cost of their booking as soon as possible while they are in the process of making it". The class preview returns density and class only, so a live price needs a separate endpoint that prices a shipment without saving anything.

## Facts from the existing code (for reference, not decisions)
- Pricing is `price_quote(tariff, ...)` in `quotes/pricing.py`: a pure function. It takes the origin and destination ZIP, the two location types, the units (weight, quantity, pricing class), `liftgate_requested` and `appointment_requested`, and returns the price, line items, transit days and estimated delivery date.
- `create_quotes` in `quotes/services.py` prices the saved request once per carrier in the current tariff version, then saves a `Quote` per carrier. It raises `NoTariffError` (the API returns 503, "There is no current tariff version.") when no tariff exists.
- The pickup date does not change the price. It only drives the estimated delivery date and the business-day check.
- The class that prices a unit is the shipper's class if given, else the suggested class (`pricing_class`).
- Every price in the preview would come from the same function a real quote uses, so the preview and the quote cannot disagree on the same inputs.

## Proposed rules (all open until Graham answers)
- URL and method: `POST /api/price-preview/` (proposal). Stores nothing, creates no quote request, no quote, no expiry.
- No authentication for now (same as the other Slice 5 endpoints; Graham: "no authentication for now").
- Shared code: pull the "price this shipment with each carrier" step out of `create_quotes` into one function that both `create_quotes` and the preview call, so the two cannot drift (proposal, in line with Graham's decision to prevent drift).

## Answers so far (Graham, 2026-11-25, in his words) and the agent's follow-ups
- **Q1 Inputs:** "only include the inputs that affect the price". Agent's reading: both ZIP codes, both location types, `liftgate_requested`, `appointment_requested`, and per unit: `quantity`, `weight_lb`, `length_in`, `width_in`, `height_in` and an optional `freight_class`. The dimensions count because they give the suggested class, which prices a unit when no class is chosen. Not included: addresses, pickup date, unit type, stackable, commodity description, NMFC code. Confirmed by Graham ("yes").
- **Q2 Output:** Graham asked: "I thought the plan was 'One price per carrier'. any reason to do it differently?" Agent: no reason. One price per carrier, each with the carrier's code and name. The "lowest" and "difference from the lowest" came from the agent's earlier summary, not from Graham's decision; they are left out. The front end can still tag the lowest by comparing the prices.
- **Q3 Detail:** Graham: "can we put the line hall in a '?' pop up?" Agent's reading: yes; the pop-up is front-end work and needs the line items in the response, so each carrier's entry carries its line items (the same fields a stored quote's line items have: kind, description, source, reason, amount). Today the markup is 0%, so the line items add up to the price; the pop-up shows all line items (line-haul, fuel and fees), not only the line-haul. Confirmed by Graham ("yes" to the three questions).
- **Q4 Delivery estimate:** "include transit days only" (no delivery date, since no pickup date is sent). Each carrier's entry carries `transit_days`.
- **Q5 Incomplete input:** "return a 400 naming the field". Same style as the class preview.
- **Q6 No tariff:** Graham asked: "is there any reason to change the message from the one quote creation uses?" Agent: no reason; use the same 503 and message ("There is no current tariff version."). The front end already turns technical messages into friendly ones (decision 16).
- **Q7 Estimate label:** "I would prefer endpoint unless there's a serious reason to do it in the front end." Agent: no serious reason. Proposed wording, for Graham to approve or change: "Estimate only. Your final price is set when you request quotes."

## Confirmed by Graham (2026-11-25)
- Q1 input list: "yes". Q7 wording: "i approve", so the endpoint's note reads "Estimate only. Your final price is set when you request quotes." Moving the pricing step into one shared function used by `create_quotes` and the preview: "yes".

## Shape (proposed by the agent, approved by Graham 2026-11-25)
- `POST /api/price-preview/`, JSON body:
  - Required: `origin_postal_code`, `origin_location_type`, `destination_postal_code`, `destination_location_type`, and `handling_units` (at least one). Each unit: `quantity`, `length_in`, `width_in`, `height_in`, `weight_lb`.
  - Optional: `liftgate_requested` and `appointment_requested` (false when left out); `freight_class` on a unit (blank or left out means the suggested class prices that unit, as in a real quote).
  - Every validation rule and message is the quote request's own (same ZIP check, location type choices, size and weight limits, whole numbers, minimums). Any other field sent is ignored.
- 200 response, in carrier order (cheap, mid, fast):
```
{
  "note": "Estimate only. Your final price is set when you request quotes.",
  "prices": [
    {"carrier": {"code": "cheap", "name": "Cheap and Slow"}, "total": "773.62", "transit_days": 4,
     "line_items": [{"kind": "line_haul", "description": "Line-haul, class 55", "source": "", "reason": "", "amount": "277.20"}, ...]},
    ...
  ]
}
```
- Money is a string with two decimals, line items have the same fields as a stored quote's line items, and the line items add up to `total`.

## Worked examples (proposed by the agent 2026-11-25; approved by Graham 2026-11-25)
Every amount below is either Graham's hand-calculated value from `docs/slices/slice_02_quote_engine.md` (marked G) or was worked out by the agent from the tariff table and the same formulas, then confirmed by running the existing pricing code (marked A, for Graham to check by hand). No new rules.

### Case 1: Slice 2 Example 1 inputs return three prices
Body: origin 75002, business dock; destination 30301, residential; liftgate requested; appointment not requested; unit 1: quantity 1, 48 x 40 x 40 in, 1,200 lb, class 55; unit 2: quantity 1, 48 x 40 x 40 in, 400 lb, class 125. (The dimensions are required by the endpoint; they do not change the price here because both classes are given.)

| Carrier | Total | Transit days | Line items (amounts) |
|---|---|---|---|
| Cheap and Slow (A) | 773.62 | 4 | line-haul class 55 277.20; line-haul class 125 210.00; fuel (28%) 136.42; residential delivery 85.00; liftgate 65.00 |
| Mid (G) | 913.85 | 3 | line-haul class 55 314.16; line-haul class 125 238.00; fuel (32%) 176.69; residential delivery 100.00; liftgate 85.00 |
| Fast and Pricey (A) | 1,085.04 | 2 | line-haul class 55 360.36; line-haul class 125 273.00; fuel (35%) 221.68; residential delivery 120.00; liftgate 110.00 |

The note is present and the response has no delivery date, no expiry and no quote id.

### Case 2: the minimum charge shows as one line
Body: Slice 2 Example 2 (origin 75002, business dock; destination 75201, business dock; one pallet, quantity 1, 48 x 40 x 40 in, 150 lb, class 100; no liftgate, no appointment).

| Carrier | Total | Transit days | Line items |
|---|---|---|---|
| Cheap and Slow (G) | 96.00 | 2 | line-haul (minimum applied) 75.00; fuel (28%) 21.00 |
| Mid (A) | 118.80 | 1 | line-haul (minimum applied) 90.00; fuel (32%) 28.80 |
| Fast and Pricey (A) | 148.50 | 1 | line-haul (minimum applied) 110.00; fuel (35%) 38.50 |

### Case 3: a blank class is priced with the suggested class
Body: origin 75002, business dock; destination 75201, business dock; one pallet, quantity 1, 48 x 40 x 40 in, 200 lb. The density is 4.5 and the suggested class is 175 (by the existing class rule). Expected totals: Cheap and Slow 188.16, Mid 221.76, Fast and Pricey 264.60 (A; line-haul class 175 147.00, 168.00 and 196.00; fuel 41.16, 53.76 and 68.60). The same body with `"freight_class": "175"` returns identical prices. The same body with `"freight_class": "100"` returns 107.52, 126.72 and 151.20 (the shipper's class wins over the suggested one, as in a real quote).

### Case 4: the preview cannot disagree with a real quote
For the inputs of Slice 2 Examples 1, 3 and 5, create the quote request and its quotes in the normal way, then send the same inputs to the preview. For every carrier the preview's `total`, `transit_days` and every line item (kind, description, source, reason, amount) equal the stored quote's. Graham's own values also hold: Example 3's fast carrier is 1,605.36 (G) and Example 5's cheap carrier is 629.76 (G).

### Case 5: nothing is saved
After any preview, the count of quote requests, handling units, quotes and bookings is unchanged.

### Case 6: bad input returns 400 and names the field (messages are the existing ones)
| Sub-case | Change to the Case 1 body | Expected 400 body |
|---|---|---|
| 6a | the second unit has no `weight_lb` | `{"handling_units": [{}, {"weight_lb": ["This field is required."]}]}` |
| 6b | `destination_postal_code` is `7520` | `{"destination_postal_code": ["Enter a 5-digit ZIP code, with an optional +4 (12345 or 12345-6789)."]}` |
| 6c | `destination_location_type` is `bogus` | `{"destination_location_type": ["\"bogus\" is not a valid choice."]}` |
| 6d | `handling_units` is an empty list | `{"handling_units": {"non_field_errors": ["This list may not be empty."]}}` |
| 6e | `origin_postal_code` is left out | `{"origin_postal_code": ["This field is required."]}` |
| 6f | a unit weighs 4,001 lb | 400 naming `weight_lb` (the quote request's limit and message) |

### Case 7: no current tariff
With no current tariff version the response is 503 with `{"detail": "There is no current tariff version."}`, the same as quote creation.

### Case 8: other rules
- Any method other than POST returns 405.
- No authentication is needed.
- Fields the endpoint does not use (for example `pickup_date`) may be sent and are ignored; the prices do not change.

## Definition of done (proposed by the agent; approved by Graham 2026-11-25)
Done when `python manage.py test`, `ruff check .` and `ruff format --check .` pass; tests exist and pass for Cases 1 to 8; `create_quotes` and the preview call one shared pricing function and the existing quote tests still pass unchanged; the endpoint stores nothing; the README endpoint table gains `POST /api/price-preview/`; the `limits` and `class-preview` endpoints are unchanged; and decisions are logged in `docs/decisions.md`.

## Out of scope
Pickup-date pricing, delivery dates, expiry, lowest-price and price-difference fields, accounts and authentication.
