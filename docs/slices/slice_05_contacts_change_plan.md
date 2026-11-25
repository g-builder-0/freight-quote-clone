# Slice 5 backend change 2: stricter booking contacts, plan

Status: PROPOSED by the agent 2026-11-25; awaits Graham's approval. The spec (`slice_05_contacts_change.md`) wins if the plan and spec disagree. Names marked "proposed" are the agent's suggestions, not decisions. Nothing is built. The spec's definition of done was proposed by the agent; Graham has approved the worked examples but has not yet said whether he approves the definition of done. Budget: about half a day (agent's estimate, not measured), mostly updating the existing Slice 3 tests.

## Approach
Tests first, then the smallest code that passes them, as in earlier slices. The rule is the same for both contacts now, so the code gets simpler: the appointment special case goes away.

## Steps

### 1. Update the tests to the new rules (red first)
- `quotes/tests/test_contacts.py`: rewrite to the new rule (name, phone, email all required; the new messages; the 5a to 5i inputs at the unit level); remove the tests of the appointment rule and of the "phone or an email" message.
- `quotes/tests/test_booking_api.py`: give `DANA` and `MARCUS` their emails and update Cases 1 to 4 inputs; shrink Case 2 to the one success (Priya, phone and email); add Case 5 (5a to 5j and the 5j follow-up).
- `quotes/tests/test_booking_service.py`, `test_bill_of_lading.py` and `test_limits.py` (which reuse `DANA` and `MARCUS`): add emails wherever a contact is built, and expect the emails where a booking response or bill of lading shows a contact. Expected values change only by the emails, as agreed.
- `quotes/tests/test_booking_model.py`: Case 6, one test per field, that saving a booking with an empty phone or email fails with an integrity error and leaves nothing saved, and a booking with all four filled saves.
- Run them and show them failing before any code changes.

### 2. `quotes/contacts.py`
- `clean_contact` requires name, phone and email: "Enter a phone number." under `phone`, "Enter an email address." under `email`, reported separately; the existing messages for a bad phone, a bad email and a missing name are unchanged. Values are trimmed first, so spaces only count as missing.
- Delete the dead code: `APPOINTMENT_PHONE_MESSAGE`, the `phone_required_message` option, the "Enter a phone number or an email address." path and its `non_field_errors` entry.
- Proposed: the shipper and the receiver now follow one rule, so the two wrappers `clean_shipper` and `clean_receiver` are removed and the booking view calls `clean_contact` for both. (Their only difference was the appointment rule.)

### 3. `quotes/views.py`
- `_booking_input` calls `clean_contact` for both contacts and no longer needs the quote, so its `quote` argument goes too. The 400 body shape is unchanged: `{"shipper_contact": {...}}` and `{"receiver_contact": {...}}`.

### 4. `quotes/models.py` and one migration
- Add four check constraints to `Booking.Meta` that reject an empty `shipper_phone`, `shipper_email`, `receiver_phone` or `receiver_email` (proposed names such as `booking_shipper_phone_not_empty`). One per field, so a failure names the field.
- Generate the migration with `makemigrations` (proposed name `0006_booking_contacts_required`); I check that it is the only change, and that it applies to a database that already holds one valid booking.
- No data migration (spec).

### 5. Docs and finish
- Update `docs/slices/slice_03_booking.md` as listed in the spec (the contact rules, Cases 1 to 4 and the Case 2 table).
- Run `python manage.py test`, `ruff check .`, `ruff format --check .` and `makemigrations --check`; report the counts (369 tests now).
- Draft the `docs/decisions.md` rows; Graham commits.

## Not changed
- Phone and email formats, the name rule, booking numbers, labels, the quote and everything outside booking contacts.

## Risks
- The Slice 3 tests are the largest part of the work. Expected values change only by the emails and the removed or moved Case 2 sub-cases; any other change I find necessary I will stop and ask about.
- The new constraint fails on an existing development booking with an empty phone or email (spec: delete it).

## Questions for Graham
1. Approve the spec's definition of done?
2. Approve removing `clean_shipper` and `clean_receiver` in favor of one `clean_contact` (step 2)?
3. Approve this plan?
