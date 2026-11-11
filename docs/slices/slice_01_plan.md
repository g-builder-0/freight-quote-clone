# Slice 1 Plan: Foundations and Quote Request

Status: DRAFT, AWAITING GRAHAM'S REVIEW. No code has been written. Do not start implementation until Graham approves
this plan in writing (Step 8: check the plan against `slice_01_quote_request.md`).

This plan was rewritten from the agent's earlier chat version after the 2026-11-10 decisions (class computed on read,
`CLASS_TABLE_VERSION` added). Where wording differs from the chat version, this file is the one to review. Names marked
"proposed" are the agent's suggestions, not decisions.

## Approach
Build in small steps, rule modules first. The rule functions take plain inputs (numbers, strings, dates), so they can be
tested with no database and no web request. Models, serializers and views come after the rules are tested.

## Steps

### 1. Scaffold the project
- Create the Django project (proposed package name `freight_quote_clone`) and one app (proposed name `quotes`).
- Settings: `rest_framework` installed; `USE_TZ = True`; `TIME_ZONE = "America/Chicago"`.
- `python-decouple` reads `SECRET_KEY`, `DEBUG` and `ALLOWED_HOSTS` (real environment variables first, then `.env`, then defaults).
- Add `.env.example` with placeholder values (committed). `.env` stays ignored by git.
- Done when `python manage.py check` and `ruff check .` pass.

### 2. Density and class rules (plain-input module, proposed `quotes/freight_class.py`)
- `CLASS_TABLE_VERSION = "NMFTA-2025-1"`.
- The accepted 13-tier table, copied exactly from the spec. The agent must not change it.
- `calculate_density(weight_lb, length_in, width_in, height_in)` returns a Decimal using one division:
  `(weight x 1728) / (L x W x H)`. No rounding.
- `suggest_class(density)` looks up the class; a density exactly on a boundary lands in the upper class.
- `STANDARD_NMFC_CLASSES`: the 18 standard classes (50 through 500), kept separate from the density table and used only to validate a user-supplied class.
- Tests: a valid and an invalid supplied class; the five worked examples (class, plus density as an exact fraction), the 35 boundary (2,240 lb) and the 34.984375 case
  (2,239 lb), and `CLASS_TABLE_VERSION` is a non-empty string.

### 3. Pickup-date rule (plain-input module, proposed `quotes/pickup.py`)
- `is_business_day(date)`: weekday only; the only place holidays could be added later.
- `validate_pickup_date(pickup_date, today)`: must be a business day and after `today`.
- `today` is passed in, so tests supply any date they like and never depend on the real clock.
- Tests: weekday after today passes; Saturday, Sunday, today and past dates fail.

### 4. Models and migration
- `QuoteRequest`: origin and destination addresses as FLAT fields (origin_street, origin_city, origin_state, origin_postal_code, and the same four with a destination_ prefix; no separate Address model), two location types, requested pickup date.
- The state and ZIP rules live in shared validators (one module) used by both address sets.
- `HandlingUnit`: foreign key to `QuoteRequest`; unit type, quantity, length, width, height, weight, stackable, commodity description,
  optional NMFC code, optional user-supplied class.
- Density and suggested class are NOT stored. They are computed properties that call the step 2 functions
  (decision 2026-11-10).
- Done when migrations are generated and applied and `manage.py check` passes.

### 5. Serializers and validation
- Nested `HandlingUnit` serializer inside `QuoteRequest` serializer; at least one handling unit required.
- NMFC code format check (4 to 6 digits, optional hyphen and 1- or 2-digit sub), with the pattern kept in one place; tests for valid and invalid codes.
- Validation per the spec: positive WHOLE-number weight, dimensions and quantity (fractions rejected); hard limits (144 x 96 x 96 in, 4,000 lb); US-only addresses
  (2-letter state or DC, 5-digit ZIP with optional +4); unit types pallet, crate, drum, carton.
- Pickup validation: the serializer works out "today" in America/Chicago and passes it to `validate_pickup_date`.
- Responses include density as a JSON string rounded to 2 decimals (for example "9.60") and suggested class per unit; a user-supplied class is returned alongside, never overwritten.

### 6. Views and URLs
- A viewset that supports create, retrieve and list only (no update, no delete), no authentication.
- Routes: `POST /api/quote-requests/`, `GET /api/quote-requests/{id}/`, `GET /api/quote-requests/`.
- The list is paginated with DRF's page-number pagination (suggested page size 20, to be confirmed in review), ordered newest first with id as a tiebreaker. The list response is an object: count, next, previous, results.

### 7. API tests
- A worked-example payload returns the class Graham calculated by hand (all five). Density is asserted as a string.
- Each invalid case from the spec returns a 400 with a clear error.
- Create then fetch returns the same request.
- The list returns the paginated shape, a second page works, and ordering is newest first.

### 8. Finish
- Run `python manage.py test`, `ruff check .` and `ruff format --check .`.
- Write a short report: what was built, what was tested, anything the agent had to ask or decide, and anything it found
  ambiguous. Log each decision in `docs/decisions.md`. Do not edit `docs/intervention_log.md`.

## Questions that still need Graham's answer
None. All questions answered.

## Resolved since the first draft
- Computed versus stored class: computed on read; Slice 2 snapshots on the quote (decisions.md, 2026-11-10).
- List endpoint: paginated, newest first (decisions.md, 2026-11-11).
- Addresses: flat fields on QuoteRequest with shared validators; a saved-address book (copied into requests) is a later addition (decisions.md, 2026-11-11).
- Density in responses: JSON string, 2 decimals (decisions.md, 2026-11-11).
- NMFC code: format check only, 4 to 6 digits with an optional 1- or 2-digit sub (decisions.md, 2026-11-11).
- Supplied class: validated against the 18 standard NMFC classes (decisions.md, 2026-11-11).
- Whole numbers only: weight, dimensions and quantity must be whole numbers; fractions are rejected (decisions.md, 2026-11-11).
- Class table version: `CLASS_TABLE_VERSION` added in step 2; booking check is a Slice 2 requirement (`slice_02_notes.md`).
- Spec said "four worked examples"; corrected to five.

## Review checklist for Graham (Step 8)
- Every rule in the spec's "Validation rules" and "Density and class" sections maps to a step above.
- The class table and worked examples are used verbatim, not re-derived.
- Nothing in this plan is out of scope (no pricing, carriers, quotes, bookings, accounts or front end).
- Each question above has an answer recorded in `docs/decisions.md` before implementation starts.
