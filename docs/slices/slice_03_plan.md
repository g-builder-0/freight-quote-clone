# Slice 3 Plan: Booking and Bill of Lading

Status: DRAFT for Graham's approval (2026-11-24). Nothing is built until Graham approves this plan. The spec (`slice_03_booking.md`) wins if the plan and spec ever disagree. Names marked "proposed" are the agent's suggestions, not decisions. Budget: 2 working days for the booking, bill of lading and cancellation, plus about half a day for the labels.

## Approach
Same as Slices 1 and 2: small steps, rule modules first. The contact rules and the bill of lading and label builders take plain inputs (strings, numbers, dates, dictionaries), so Graham's four cases can be tested with no database and no web request. The booking model, service, serializers and views come after the rules are tested. Every expected value in a test is Graham's from the spec; the agent never invents one. The full test suite, `ruff check .` and `ruff format --check .` run after every step.

## Steps

### 1. Contact rules (plain-input module, proposed `quotes/contacts.py`)
- A function that checks one contact (name required; phone, email or both; phone format; email format) and a function that applies the appointment rule to the receiver (phone required).
- Tests: the Case 2 sub-cases (phone, email only, both), a missing name, neither phone nor email, instructions over 500 characters.
- Done when the new tests and the existing suite pass.

### 2. Bill of lading and label builders (plain-input module, proposed `quotes/bill_of_lading.py`)
- Builders that take the booking number, dates, contacts, the addresses and location types, the handling-unit lines (with the class used), the carrier and the requested accessorials, and return the bill of lading dictionary and the list of labels.
- Tests: Case 1 (contents, total weight 1,600 lb, no price), Case 2 (appointment, construction site, 2,500 lb), Case 3 (seven labels, count across lines, per-unit weight, barcodes `BK-000001-01-07` to `BK-000001-07-07`), a quantity-1 line, and labels for units that appear in line order.
- Done when Graham's Case 1 to 3 expected values pass verbatim.

### 3. Models and migration
- `Booking` (proposed name): one-to-one to `Quote` (protected), `status`, `booked_at`, `cancelled_at`, `cancel_reason`, shipper and receiver contacts, `special_instructions`, and the `bill_of_lading` JSON field. `booking_number` is a property built from the id. The model refuses any change except through the cancel function; bookings cannot be deleted. Read-only admin.
- Tests: the one-to-one constraint, a second booking of a quote fails at the database, the model refuses edits and deletes, the booking number format.
- Note for the tests: booking numbers come from the database id. The spec's `BK-000001` assumes an empty database, so the tests also assert the pattern against the booking's own id, because some databases do not reset ids between tests.

### 4. Booking service and cancellation
- A service function (proposed in `quotes/services.py`) `book_quote(quote, shipper_contact, receiver_contact, instructions, now)`: in one transaction it locks the quote, checks "already booked" (this quote, or another quote of the request with an active booking), runs `check_bookable(now)`, builds the bill of lading, saves the booking, and returns it. It returns the first failure as a clear error that the view maps to 409. A second function `cancel_booking(booking, reason, now)`.
- Status changes are decided in one place: a small lookup in code (proposed `quotes/booking_status.py`) that maps each status to the statuses it may change to, and one function `can_transition(current, new)`. Slice 3 holds `booked` to `cancelled` and nothing else (a cancelled booking changes to nothing). `cancel_booking` and the "cancel only while booked" and "cancelling twice is a 409" rules all go through it, not through separate checks. Slice 4 adds rows to the lookup (see `slice_04_notes.md`) and changes no existing code.
- Tests for the lookup: every allowed change passes and every other pair of statuses is refused.
- Tests: Case 4 in full (4a to 4i), the double-booking race backed by the unique constraint, a failure saving nothing, and the first-failure order (expired, class table, rates, pickup date; already booked first).
- Done when Graham's Case 4 expected values pass verbatim.

### 5. Serializers, views and URLs
- `POST /api/quotes/{id}/bookings/`, `GET /api/bookings/{id}/`, `GET /api/bookings/{id}/bill-of-lading/`, `GET /api/bookings/{id}/labels/` and `POST /api/bookings/{id}/cancel/`. Money as two-decimal strings. The 400, 404 and 409 mapping from the spec, with the 400 reported before any 409. 405 for update and delete. The current time comes from the same `get_now()` seam used in Slice 2, patched in the API tests.
- Tests: Cases 1 to 3 end to end through the API (including the exact 2b error body and the 2b retry), Case 4 end to end, 404s, 405s, and the status code and body of every error.

### 6. Finish
- Run `python manage.py test`, `ruff check .` and `ruff format --check .`.
- Write a short report: what was built, what was tested, what was decided or found ambiguous. Log each decision in `docs/decisions.md`. Do not edit `docs/intervention_log.md`.
- Update the README simplifications list (no payment terms on the bill of lading, no PDF, no editing a booking, no reweigh adjustment, no authentication).
- Mark the Slice 3 spec accepted and this plan implemented.

## Built so Slice 4 can be added later
Slice 4 (tracking events) may be built after the Slice 5 front end. It adds a table, new statuses and new endpoints, and does not change anything built in Slice 3, provided two things are true from the start. First, status changes go through the one lookup in step 4. Second, the booking response is allowed to gain an `events` list later, and the Slice 5 front end shows statuses through one label map with a fallback for any status it does not know. Both are small and are part of this plan and the Slice 5 notes.

## Time and cut line
Steps 1 and 2 are the pure-rule work and the highest value (about half a day). Steps 3 and 4 are the booking itself (about a day). Step 5 is about half a day. The labels are about half a day of the total and sit in steps 2 and 5, so they are built last and can be the first part to slip if time runs short. The next things to cut after labels are the Slice 4 webhooks and then accounts.

## Questions for Graham
1. Approve the order of steps and the time estimate?
2. Approve the proposed names (`quotes/contacts.py`, `quotes/bill_of_lading.py`, `Booking`) and the proposed items listed under Open questions in the spec?
3. What is the real deadline? This plan assumed 2026-11-25, which was never confirmed.
