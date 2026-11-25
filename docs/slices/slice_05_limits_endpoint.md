# Slice 5 backend change 3: limits endpoint

Status: SPEC APPROVED by Graham 2026-11-25 (rules, worked examples and definition of done: "i agree with the worked exampled and DOD"); plan in `slice_05_limits_endpoint_plan.md` awaits his approval. Nothing is built.

## Goal
The front end's friendly error messages and its character counters must not hard-code values that the API owns (Graham, decision 16: "i agree with your decision to prevent drift"). This endpoint hands those values to the front end, so a change in the API's rules reaches the screen without editing the front end.

## Facts from the existing code (for reference, not decisions)
- Size and weight limits per unit are constants in `quotes/models.py`: `MAX_LENGTH_IN` 144, `MAX_WIDTH_IN` 96, `MAX_HEIGHT_IN` 96, `MAX_WEIGHT_LB` 4000. The minimum for each is 1, and quantity has a minimum of 1 and no maximum.
- Text limits: special instructions 500 and cancel reason 200 (`quotes/contacts.py`); contact name 100; commodity description 200; street 200; city 100; NMFC code 10.
- The standard freight classes a shipper may pick are `STANDARD_NMFC_CLASSES` in `quotes/freight_class.py`; the unit types and location types are model choices.
- The pickup rule (a weekday after today) is a function in `quotes/pickup.py`, not a number.

## Rules
- URL and method: `GET /api/limits/` (agent's suggestion; Graham: "url and shape look good", 2026-11-25).
- Values returned (Graham, 2026-11-25: "character counters and friendly messages are good"): (a) per-unit weight and the three dimension limits and minimums, for the friendly messages; (b) the instructions limit (500) and the cancel reason limit (200), for the character counters. **Extra values skipped (Graham: "skip extra values", 2026-11-25):** (c) the other text limits (name, description, street, city, NMFC) and (d) the lists of allowed unit types, location types and freight classes are not returned. The agent read "extra values" as covering both (c) and (d), including the lists it had recommended; the front end therefore keeps the lists itself for now, and either can be added later without breaking anything.
- Shape: grouped as `unit` and `text` (agent's suggestion, accepted: "url and shape look good"). The names inside each group are the agent's proposal in the worked examples, for Graham to approve.
- Source of values: each value is read from the same constant the validation uses, so the endpoint cannot disagree with the rules; Graham asked for a test of this ("create a test for source of values", 2026-11-25).
- Authentication: none for now (Graham: "no authentication for now", 2026-11-25).

## Worked examples (PROPOSED by the agent 2026-11-25; APPROVED by Graham 2026-11-25; every expected value is today's rule in `quotes/models.py` and `quotes/contacts.py`, not a new number)
### Case 1: `GET /api/limits/` returns 200 with exactly this body
```
{
  "unit": {
    "weight_lb": {"min": 1, "max": 4000},
    "length_in": {"min": 1, "max": 144},
    "width_in": {"min": 1, "max": 96},
    "height_in": {"min": 1, "max": 96}
  },
  "text": {
    "special_instructions_max": 500,
    "cancel_reason_max": 200
  }
}
```
### Case 2: any method other than GET returns 405.
### Case 3: the values cannot drift from the rules (the test Graham asked for)
- For each unit field, the value `max` is accepted by `POST /api/class-preview/` and `max + 1` is rejected (400); `min` is accepted and `min - 1` is rejected.
- A booking with instructions of exactly `special_instructions_max` characters is accepted and one more character is rejected (400); a cancel reason of exactly `cancel_reason_max` characters is accepted and one more is rejected (400).
- The endpoint reads from the constants the validation uses (`MAX_LENGTH_IN`, `MAX_WIDTH_IN`, `MAX_HEIGHT_IN`, `MAX_WEIGHT_LB`, `INSTRUCTIONS_MAX_LENGTH`, `CANCEL_REASON_MAX_LENGTH`), so a test that changes one of them (patching the constant) changes the endpoint's answer. (How the minimum of 1 is read is for the plan: the model validators hold it in the field definition.)

## Definition of done (PROPOSED by the agent 2026-11-25; APPROVED by Graham 2026-11-25)
Done when `python manage.py test`, `ruff check .` and `ruff format --check .` pass, and tests exist and pass for Cases 1 to 3, no authentication is required, the endpoint stores nothing, the README endpoint table gains `GET /api/limits/`, and decisions are logged in `docs/decisions.md`.

## Out of scope
- The extra text limits and the lists of types and classes (Graham: skipped for now); the pickup-date rule and the tariff (not plain numbers).
