# Slice 5 backend change 2: stricter booking contacts

Status: RULES ANSWERED by Graham 2026-11-25; worked examples and definition of done are PROPOSED by the agent and await his approval. (Skeleton written 2026-11-25.) Graham writes the rules and the worked examples; every `GRAHAM:` line is his to fill in or change. Nothing is built. This changes Slice 3 (`docs/slices/slice_03_booking.md`, `quotes/contacts.py` and their tests).

## Goal
Graham, decision 8: each contact (shipper and receiver) must have a name, a phone and an email. His reasons: "it provides a backup contact method if one of them fails or is entered incorrectly"; "I want the database to contain all 3 in case a backup contact method is needed."

## Facts from the existing code (for reference, not decisions)
- Today a contact needs a name and a phone or an email (`clean_contact` in `quotes/contacts.py`); with an appointment the receiver's phone is also required (`APPOINTMENT_PHONE_MESSAGE`). With neither phone nor email the error is "Enter a phone number or an email address." under `non_field_errors`.
- Phone is checked as a 10-digit US number and stored as NNN-NNN-NNNN; email gets Django's email check; name is at most 100 characters.
- On the `Booking` model, `shipper_phone`, `shipper_email`, `receiver_phone` and `receiver_email` are `blank=True`, so the database accepts empty values today.
- Slice 3's worked examples (Case 2) include a receiver with a phone only (2a), an email only (2b, a 400 with the appointment message) and both (2c). Under the new rule 2a and 2b are both missing a contact method, so their expected results change. Other cases that send a contact with a phone only (for example Dana Whitfield, 972-555-0142, in Cases 1 and 3) would also now be rejected, so every booking example needs an email.

## Rules
- Rule: name, phone and email are all required for the shipper and for the receiver (decision 8; Graham's reasons above).
- Messages: "Enter a phone number." under `phone` and "Enter an email address." under `email`, reported separately (agent's suggestion; Graham: "I agree", 2026-11-25).
- Appointment rule removed: the receiver's-phone-for-appointments rule and `APPOINTMENT_PHONE_MESSAGE` are deleted (Graham: "remove dead code and related dead rules as suggested", 2026-11-25). Appointment no longer changes any contact rule.
- The old "Enter a phone number or an email address." message and its `non_field_errors` path are removed as dead code (same answer).
- Enforcement: the request check in `quotes/contacts.py` plus a database check constraint on `Booking` that rejects an empty phone or email for the shipper and the receiver (Graham: "I approve A check constraint that rejects empty phone and email values", 2026-11-25). This needs one migration. Agent's note: `blank=False` alone would not guard the database, because Django applies `blank` only in forms and serializers, so the constraint is what carries Graham's reason. Open for the plan: the constraint's name, and whether a name must also be non-empty (not asked).
- No data migration (Graham: "i agree with those recommendations", 2026-11-25). Reason given by the agent and accepted: the only existing data is Graham's local development database, and a data migration would have to invent placeholder phone numbers or emails on real-looking bookings. If the constraint's migration fails on an existing development booking, Graham deletes that booking.

## Worked examples (PROPOSED by the agent 2026-11-25; APPROVED by Graham 2026-11-25: "i agree with the cases you presented"; Graham chose the example emails (option A1) and the Case 2 shape (option B2))
Everything not listed here stays exactly as in Slice 3 (`docs/slices/slice_03_booking.md`). The only change to Cases 1, 3 and 4 is that every contact now has an email, and the email appears wherever the contact is shown (the booking response and the bill of lading).

### Contacts used in the examples (emails added; names and phones are the Slice 3 ones)
- Dana Whitfield, 972-555-0142, dana.whitfield@example.com (shipper in Cases 1 to 4)
- Marcus Bell, 404-555-0178, marcus.bell@example.com (Case 1 receiver)
- Priya Raman, 207-555-0163, priya.raman@example.com (Case 2 receiver)
- Elena Ortiz, 323-555-0119, elena.ortiz@example.com (Case 3 receiver; email added by the agent in the same pattern, for Graham to confirm)
- Luis Herrera, 602-555-0126, luis.herrera@example.com (Case 4a and 4b receiver; email added by the agent in the same pattern, for Graham to confirm)

### Case 1, Case 3 and Case 4 (changed inputs only)
- Case 1: shipper Dana Whitfield and receiver Marcus Bell now each send their email as above. Expected: as before (201, `BK-000001`, `booked`, total $913.85), plus both emails in the booking response (`shipper_contact`, `receiver_contact`) and on the bill of lading.
- Case 3: receiver Elena Ortiz and the shipper now send emails. Expected: as before (201, `BK-000001`, 7 labels).
- Case 4: 4a and 4b send the shipper and Luis Herrera with emails; 4c to 4i use the Case 1 inputs with emails. Expected: as before.

### Case 2 (shrunk to one success): appointment booking of the Example 3 fast-carrier quote
Same quote, shared inputs, and instructions as Slice 3 Case 2. Receiver sent: Priya Raman, 207-555-0163, priya.raman@example.com (the old 2c). Expected: 201; `BK-000001`; `booked`; confirmation total $1,605.36; the receiver's phone and email both stored and both on the bill of lading. The old sub-cases 2a (phone only) and 2b (email only, with the appointment message) are removed; their inputs now belong to Case 5.

### Case 5: contact rejections (new)
All sub-cases book the Example 1 quote at 2026-11-25 09:30 with the Case 1 inputs, changing only the contact named, unless stated. Each returns 400, creates nothing, and leaves the quote unchanged.

| Sub-case | Contact sent | Expected body |
|---|---|---|
| 5a | shipper without a phone | `{"shipper_contact": {"phone": ["Enter a phone number."]}}` |
| 5b | shipper without an email | `{"shipper_contact": {"email": ["Enter an email address."]}}` |
| 5c | shipper with neither | `{"shipper_contact": {"phone": ["Enter a phone number."], "email": ["Enter an email address."]}}` |
| 5d | receiver without a phone | `{"receiver_contact": {"phone": ["Enter a phone number."]}}` |
| 5e | receiver without an email | `{"receiver_contact": {"email": ["Enter an email address."]}}` |
| 5f | receiver with neither | `{"receiver_contact": {"phone": ["Enter a phone number."], "email": ["Enter an email address."]}}` |
| 5g | shipper phone `972-555` | `{"shipper_contact": {"phone": ["Enter a 10-digit US phone number, for example 972-555-0142."]}}` |
| 5h | receiver email `not-an-email` | `{"receiver_contact": {"email": ["Enter a valid email address."]}}` |
| 5i | shipper without a name | `{"shipper_contact": {"name": ["Enter a name."]}}` |
| 5j | the Example 3 appointment quote, receiver Priya Raman with email only (the old 2b) | `{"receiver_contact": {"phone": ["Enter a phone number."]}}` (no appointment-specific message any more) |

- 5j follow-up: the same request with the phone added returns 201 with `BK-000001`, proving the failed attempt left no record and did not use up the booking number (moved from the old 2b).
- A phone or email of only spaces counts as missing (5a to 5f messages), because values are trimmed before they are checked.

### Case 6: the database constraint (new)
- Saving a `Booking` row directly (bypassing the request check) with an empty `shipper_phone`, `shipper_email`, `receiver_phone` or `receiver_email` fails with a database integrity error, one test per field, and leaves no booking saved. A booking with all four filled saves normally.

## Changes to the Slice 3 spec text (to be made when this is built)
- "Contacts and instructions": each contact needs a name, a phone and an email (replacing "a phone, an email, or both"); the receiver-phone-for-appointments rule is deleted.
- Cases 1 to 4 and the Case 2 table are replaced by the examples above.

## Definition of done (PROPOSED by the agent 2026-11-25 for Graham to edit and approve)
Done when `python manage.py test`, `ruff check .` and `ruff format --check .` pass, `makemigrations --check` shows the one new migration applied, and tests exist and pass for Cases 1 to 6 as above (every Slice 3 test that sent a contact without an email is updated to the new inputs; no expected value changes except the emails and the removed Case 2 sub-cases), `quotes/contacts.py` no longer contains the appointment message or the "phone or an email" message, `docs/slices/slice_03_booking.md` is updated as above, and the decisions are logged in `docs/decisions.md`.

## Out of scope
- Phone and email formats (unchanged), the name rule (unchanged), and the booking number.
