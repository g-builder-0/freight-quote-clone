# Slice 5 backend change 3: limits endpoint plan

Status: PROPOSED by the agent 2026-11-25; awaits Graham's approval. The spec (`slice_05_limits_endpoint.md`) wins if the plan and spec disagree. Names marked "proposed" are the agent's suggestions, not decisions. Nothing is built. Budget: well under half a day (agent's estimate, not measured).

## Approach
Same as the class preview: tests first, then the smallest code that passes them. The endpoint holds no numbers of its own. Every value is read, at the moment of each request, from the constant the validation uses.

## Steps

### 1. Tests (proposed `quotes/tests/test_limits.py`)
- Case 1: the exact body from the spec.
- Case 2: POST, PUT, PATCH and DELETE return 405.
- Case 3, boundary half: for each unit field, `max` is accepted and `max + 1` rejected, `min` accepted and `min - 1` rejected, using `POST /api/class-preview/` with the values read from the limits response. Instructions of exactly the limit are accepted at booking and one more character is rejected (400); the same for the cancel reason. (These reuse the existing booking and cancel set-up from the booking API tests.)
- Case 3, source half: with each constant patched to another value, the limits response changes to match, which shows the endpoint reads the constant and not a copied number.
- The endpoint stores nothing and needs no sign-in.
- Shown failing first (404, the URL does not exist yet).

### 2. One small change to `quotes/models.py` (needs Graham's approval)
- The minimum of 1 is currently a bare `1` inside each field's validators, so there is no constant to read. Proposed: add `MIN_UNIT_VALUE = 1` next to the `MAX_*` constants and use it in the four validators. The behaviour and error messages do not change; I will check `makemigrations --check` shows no migration, and the full suite must still pass.
- Alternative: read the minimum by looking inside the model field's validator list. It needs no models change, but it is fragile and harder to read.

### 3. View and URL (proposed `LimitsView` in `quotes/views.py`, route in `quotes/urls.py`)
- A GET-only `APIView` (other methods return 405) that builds the body from `models.MAX_WEIGHT_LB`, `MAX_LENGTH_IN`, `MAX_WIDTH_IN`, `MAX_HEIGHT_IN`, `MIN_UNIT_VALUE`, `contacts.INSTRUCTIONS_MAX_LENGTH` and `contacts.CANCEL_REASON_MAX_LENGTH`, reading each attribute from its module when the request arrives (so patching a constant in a test takes effect).
- Route: `path("limits/", LimitsView.as_view(), name="limits")`, giving `GET /api/limits/`. No authentication.

### 4. Finish
- Run `python manage.py test`, `ruff check .` and `ruff format --check .`; report the counts (the suite stands at 360 tests).
- Add `GET /api/limits/` to the README endpoint table.
- Draft the `docs/decisions.md` rows; Graham commits.
- No migration expected (checked in step 2).

## Not changed
- No existing endpoint, serializer or rule changes. The only edit to existing code is replacing the literal `1` with a named constant of the same value (step 2).

## Questions for Graham
1. Approve adding `MIN_UNIT_VALUE = 1` to `quotes/models.py` (step 2), or prefer reading the minimum from the validators?
2. Approve this plan?
