# Slice 3: Booking and Bill of Lading

Status: DRAFT for Graham's acceptance (drafted 2026-11-24). Graham made every decision recorded here and wrote the worked examples' inputs and expected results in conversation with the agent; the agent assembled this file. Items marked PROPOSED are the agent's suggestions and are not decisions until Graham accepts them (see Open questions). Carried-forward requirements from `slice_03_notes.md` are included here; that file is superseded by this one. The rows for `docs/decisions.md` are in `decisions_slice_03_rows.md`. Implementation starts only after Graham approves the Slice 3 plan.

## Goal
A shipper chooses one of the quotes from Slice 2, enters the shipper and receiver contacts and any special instructions, and books it. The booking is checked against the Slice 2 `check_bookable(now)` function, and on success produces a booking number, a bill of lading (the shipping document) and one pallet label for every physical handling unit. A booking can be cancelled while it is still `booked`.

Slice 3 builds only the statuses `booked` and `cancelled`. The later statuses (picked up, in transit, delivered) arrive in Slice 4.

## Rules

### Booking a quote
- A booking references exactly one quote. The quote is never changed by booking or cancelling.
- A quote can be booked once. A second attempt on the same quote is rejected (409). This also holds after a cancellation: a cancelled booking's quote cannot be booked again, and the shipper must create a new quote (which also guarantees current rates).
- A quote request can have only one active (`booked`) booking at a time, even though it has three quotes. Booking a second quote of a request that already has an active booking is rejected (409). PROPOSED detail: this is enforced in the booking service and the "one booking per quote" rule is also enforced by a unique constraint.
- Booking calls the Slice 2 function `check_bookable(now)`. A failed check is a 409 and the response carries the reason text from the function. The current time is passed in so tests supply the clock.
- Booking is the real enforcement of the rules; the `bookable` flag on a quote in Slice 2 is only for the front end.

### Contacts and instructions
- The shipper contact and the receiver contact are collected at booking, not on the quote request. Both appear on the bill of lading.
- Each contact has a name (required) and a phone, an email, or both. At least one of phone and email is required. The shipper contact is always required.
- The receiver contact is always required (it is needed for the consignee details on the bill of lading).
- If the quote's request has the appointment flag, the receiver's phone is required; an email alone is not accepted, because a carrier schedules a delivery appointment by calling the receiver. (Decided 2026-11-24, Option B.)
- Special instructions are optional text of at most 500 characters.
- PROPOSED: phone numbers are US numbers of 10 digits, with spaces, dashes, dots and parentheses allowed and an optional leading 1; emails use the standard email check.

### Booking number
- The booking number is `BK-` plus the booking's database id padded to six digits (the first booking in an empty database is `BK-000001`). The bill of lading number is the same string.

### Bill of lading
- The bill of lading is a JSON document built when the booking is created and stored on the booking as a snapshot. It never changes afterwards, even if the quote request is later edited. It is served at `GET /api/bookings/{id}/bill-of-lading/`. A PDF is a stretch item and is not part of this slice.
- It contains: the booking and bill of lading number; the booking date and the pickup date; the carrier; the shipper (contact, and the origin address and location type copied from the quote request); the consignee (contact, and the destination address and location type copied from the quote request); each handling unit (type, quantity, weight of one unit, dimensions, the class used for pricing, commodity description, NMFC code if given, stackable); the total weight; the requested accessorials (liftgate, appointment); and the special instructions.
- Addresses are copied from the quote request and cannot be edited at booking.
- It does not show the price or any fee, including the automatic location fees. The quoted total is shown on the booking confirmation instead.

### Pallet labels
- `GET /api/bookings/{id}/labels/` returns one label for every physical handling unit: a line with quantity 3 gives three labels. Labels are numbered across the whole booking ("3 of 7"), in the order the lines appear on the bill of lading, and the count does not restart for each line.
- A label contains: the booking number; "unit N of M"; the barcode string `BK-<six-digit id>-<NN>-<MM>` (for example `BK-000001-03-07`), which the front end draws as a barcode image; the weight, class, unit type and commodity description of that one unit; the shipper and consignee names with city and state; the destination ZIP code; the carrier; and the pickup date.
- Labels are built from the bill of lading snapshot, so they add no stored data.
- A cancelled booking has no labels (409).

### Cancellation
- `POST /api/bookings/{id}/cancel/` with a required `reason` (at most 200 characters; missing is a 400).
- Allowed only while the status is `booked`. The booking records the time and the reason. Cancelling a cancelled booking is a 409.
- The quote is not changed and cannot be booked again (see above).

### Status changes
- Which status changes are allowed is decided in one place in the code: a lookup from each status to the statuses it may change to. In Slice 3 it holds `booked` to `cancelled` only. Every status change goes through it, so the cancellation rules above are consequences of the lookup, and Slice 4 adds the later statuses by adding rows (see `slice_04_notes.md`).

### Errors
| Status | When |
|---|---|
| 400 | The request body is invalid: a missing or malformed contact, a receiver with no phone when the appointment flag is set, instructions over 500 characters, a missing cancel reason. If a request fails both ways, the 400 is reported first. |
| 404 | The quote or booking does not exist. |
| 409 | The server's stored state blocks the request: `check_bookable` fails (reason text from the function); the quote is already booked, or its request already has an active booking; a cancelled booking is cancelled or asked for labels. |

- A 409 body is `{"detail": "<reason>"}`. A 400 body uses the usual field errors, for example `{"receiver_contact": {"phone": ["..."]}}`.
- Reason texts from `check_bookable` (Slice 2): "The quote has expired.", "The freight class table has changed since this quote.", "The rates have changed since this quote.", "The pickup date is no longer available." They are checked in that order and the first failure is reported.
- PROPOSED texts: "This quote has already been booked." (409); "This booking is already cancelled." (409); "Labels are not available for a cancelled booking." (409); "A phone number is required for the receiver when the quote includes a delivery appointment." (400, on `receiver_contact.phone`).
- PROPOSED order for 409 checks: already booked first, then `check_bookable`.
- A failed request saves nothing. The booking and its snapshot are created in one transaction.

## Models (PROPOSED names; Graham approves with the plan)
- `Booking`: one-to-one to `Quote` (protected), `status` (`booked` or `cancelled`), `booked_at`, `cancelled_at` and `cancel_reason` (blank until cancelled), the shipper contact (name, phone, email), the receiver contact (name, phone, email), `special_instructions`, and `bill_of_lading` (JSON snapshot). `booking_number` is derived from the id and is not stored.
- Only the status, `cancelled_at` and `cancel_reason` can change after creation, and only through the cancel function. The snapshot is never changed. Bookings are never deleted.

## Worked examples (inputs and expected results decided by Graham 2026-11-24; used verbatim as test expectations)
Every example runs against an empty database, so the first booking is `BK-000001`. Contacts use the reserved 555-01xx phone numbers and `example.com` emails. Street addresses are made up.

### Case 1: a normal booking of the Example 1 mid-carrier quote
Quote: Slice 2 Example 1 (mid carrier, $913.85, `RATES-2026-1`, `NMFTA-2025-1`, liftgate requested, no appointment, pickup Monday 2026-11-30, estimated delivery Thursday 2026-12-03), created Wednesday 2026-11-25 at 08:10 America/Chicago. Handling units: 1 pallet, 1,200 lb, class 55, "Ceramic floor tiles, boxed"; 1 crate, 400 lb, class 125, "Rack-mount network switches".

Booking request at 2026-11-25 09:30 America/Chicago:
- Shipper: Dana Whitfield, 972-555-0142; 2200 Commerce Park Way, Allen, TX 75002 (business dock).
- Receiver: Marcus Bell, 404-555-0178; 418 Magnolia Ridge Dr SE, Atlanta, GA 30301 (residential).
- Special instructions: "Carrier must provide a liftgate for delivery; the delivery address is a residence with no loading dock. Call receiver 30 minutes before delivery."

Expected: 201. Booking number and bill of lading number `BK-000001`; status `booked`; booked at 2026-11-25 09:30; confirmation total $913.85. Bill of lading: booking date 2026-11-25, pickup date 2026-11-30, carrier mid; the shipper and consignee above; the two units above; total weight 1,600 lb; accessorial liftgate (requested); the instructions above; no price. The quote is unchanged, there is one booking, and `check_bookable` returned OK.

### Case 2: appointment bookings of the Example 3 fast-carrier quote
Quote: Slice 2 Example 3 (fast carrier, $1,605.36, appointment requested, no liftgate, pickup Tuesday 2026-12-01, estimated delivery Monday 2026-12-07, destination a construction site), created Wednesday 2026-11-25 at 08:10. Units: 1 pallet, 1,500 lb, class 70, "Automotive brake parts, boxed"; 1 pallet, 1,000 lb, class 85, "Crated industrial pump assemblies". Total weight 2,500 lb.

Booking requests at 2026-11-25 09:30. Shared inputs:
- Shipper: Dana Whitfield, 972-555-0142; 2200 Commerce Park Way, Allen, TX 75002 (business dock).
- Consignee address: Lot 7, 300 Harbor Ridge Rd, Portland, ME 04101 (construction site).
- Special instructions: "Delivery appointment required; call receiver to schedule. Site gate code needed from receiver."

| Sub-case | Receiver sent | Expected |
|---|---|---|
| 2a | Priya Raman, 207-555-0163 | 201; `BK-000001`; `booked`; confirmation total $1,605.36 |
| 2b | Priya Raman, priya.raman@example.com (no phone) | 400; nothing saved and the quote unchanged; body `{"receiver_contact": {"phone": ["A phone number is required for the receiver when the quote includes a delivery appointment."]}}` |
| 2c | Priya Raman, 207-555-0163 and priya.raman@example.com | 201; `BK-000001`; phone and email both stored and both on the bill of lading |

- 2b follow-up: the same request with the phone added returns 201 with `BK-000001`, proving the failed attempt left no record and did not use up the booking number.
- Bill of lading (2a and 2c): booking date 2026-11-25, pickup date 2026-12-01, carrier fast; destination type construction site; accessorial appointment (requested); no price and no fees. 2c shows the receiver's email as well as the phone.

### Case 3: pallet labels for the Example 5 cheap-carrier quote
Quote: Slice 2 Example 5 (cheap carrier; origin 75002 business dock; destination 90001 Los Angeles business dock; pickup Monday 2026-12-07; no liftgate, no appointment), created Wednesday 2026-11-25 at 08:10. Lines: 3 pallets of 400 lb each, class 70, "Packaged hardware fasteners"; 2 crates of 250 lb each, class 70, "Replacement electric motor housings"; 2 drums of 150 lb each, class 150, "Food-grade vegetable oil, sealed drums".

Booking request at 2026-11-25 09:30:
- Shipper: Dana Whitfield, 972-555-0142; 2200 Commerce Park Way, Allen, TX 75002.
- Receiver: Elena Ortiz, 323-555-0119; 4500 Distribution Ave, Los Angeles, CA 90001 (business dock, made up).
- Special instructions: "Receiving dock hours 7:00 to 15:00."

Expected: 201, `BK-000001`. `GET /api/bookings/{id}/labels/` returns 7 labels:

| Label | Unit | Weight of that unit | Class | Barcode |
|---|---|---|---|---|
| 1 of 7 | pallet | 400 lb | 70 | `BK-000001-01-07` |
| 2 of 7 | pallet | 400 lb | 70 | `BK-000001-02-07` |
| 3 of 7 | pallet | 400 lb | 70 | `BK-000001-03-07` |
| 4 of 7 | crate | 250 lb | 70 | `BK-000001-04-07` |
| 5 of 7 | crate | 250 lb | 70 | `BK-000001-05-07` |
| 6 of 7 | drum | 150 lb | 150 | `BK-000001-06-07` |
| 7 of 7 | drum | 150 lb | 150 | `BK-000001-07-07` |

- The number of labels is the sum of the quantities (7), not the number of lines (3). Each label shows the weight of one unit, not of the line. Every label also shows the shipper and consignee names and cities, the destination ZIP 90001, the carrier, the pickup date and the commodity description of its unit.

### Case 4: rejections and cancellation
Test inputs for 4a and 4b (receiver and address) are PROPOSED and may be changed; the rest are fixed by the rules above. For 4a and 4b the shipper is Dana Whitfield as above, the receiver is Luis Herrera, 602-555-0126, 1200 Sonoran Business Pkwy, Phoenix, AZ 85001 (made up), and the instructions are blank.

| Sub-case | Quote | Action | Expected |
|---|---|---|---|
| 4a | Slice 2 Example 4 (mid, pickup Thursday 2026-12-03), created 2026-11-25 08:10, expires 2026-12-02 08:10 | book at 2026-12-02 08:09 | 201 |
| 4b | the same quote, in a separate test | book at 2026-12-02 08:10 | 409, "The quote has expired." |
| 4c | Example 1 quote (pickup Monday 2026-11-30) | book at 2026-11-30 10:00 | 409, "The pickup date is no longer available." |
| 4d | Example 1 quote | a new tariff version is created, then book at 09:30 | 409, "The rates have changed since this quote." |
| 4e | Example 1 quote | the class table version changes, then book at 09:30 | 409, "The freight class table has changed since this quote." |
| 4f | Example 1 quote | book at 09:30 (Case 1 inputs), then again at 09:31 | first 201; second 409, "This quote has already been booked."; the first booking is unchanged |
| 4g | a `booked` booking (Case 1) | cancel with reason "Shipper cancelled", at 10:00 | 200; status `cancelled`; cancelled at 10:00; reason recorded; labels return 409 |
| 4h | the cancelled booking | cancel again | 409, "This booking is already cancelled." |
| 4i | the cancelled booking's quote | book it again | 409, "This quote has already been booked." |

- 4b is the boundary pair of 4a: one minute either side of expiry. In every 409 case no booking is created, and the quote is unchanged.
- Also: cancelling without a reason is 400; booking an unknown quote is 404; an unknown booking is 404.

## API
| Method and path | Purpose |
|---|---|
| `POST /api/quotes/{id}/bookings/` | Book the quote. Body: `shipper_contact`, `receiver_contact`, optional `special_instructions`. Returns 201 with the booking. (PROPOSED path.) |
| `GET /api/bookings/{id}/` | One booking: number, status, quote, carrier, booked time, contacts, instructions, confirmation total, cancellation details. |
| `GET /api/bookings/{id}/bill-of-lading/` | The snapshot. |
| `GET /api/bookings/{id}/labels/` | The labels (409 if cancelled). |
| `POST /api/bookings/{id}/cancel/` | Cancel with a `reason`. |

No authentication in Slice 3 (accounts are the last item in the cut order). No update or delete on bookings except cancel (405).

## Definition of done
Slice 3 is done when `python manage.py test`, `ruff check .` and `ruff format --check .` all pass, the migration is applied, and tests exist and pass for:
- Cases 1 to 4 above, used verbatim: every response status, the booking number, the bill of lading contents, the labels and barcodes, the error bodies and the stored state after each failure.
- The bill of lading never shows a price or fee; it is unchanged after the quote request is edited.
- Contact rules: receiver and shipper required; phone or email required; an appointment quote requires the receiver's phone; instructions over 500 characters rejected.
- The booking and its snapshot are saved in one transaction; a failure part-way saves nothing. A concurrent double booking cannot create two bookings (the unique constraint backs up the service check).
- A request with an active booking rejects a booking of its other quotes; after cancellation, a new quote of the same request can be booked.
- Booking numbers follow the booking id; tests assert the id-based pattern as well as the empty-database values above.
- Every decision made while building is logged in `docs/decisions.md`. The README simplifications list gains: no payment terms on the bill of lading, no PDF, no editing a booking, no reweigh adjustment, no authentication.

## Out of scope
A PDF bill of lading; payment terms or invoices; editing a booking after it is made; carrier dispatch or real carrier APIs; statuses after `booked` (Slice 4); accounts and per-shipper isolation; notifications.

## Open questions
1. The real deadline. The plan assumes 2026-11-25, which was never confirmed.
2. PROPOSED items awaiting Graham's word: the booking path `POST /api/quotes/{id}/bookings/`; the phone format check; the order of 409 checks (already booked before `check_bookable`); the exact texts of the new 409 and 400 messages; the Case 4a and 4b receiver inputs; the model names.
3. The Slice 2 fixtures' descriptions for Example 1, 3 and 5 units should match the descriptions in Cases 1 to 3 (test data only).
