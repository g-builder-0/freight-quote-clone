# Slice 5 backend change 1: class preview endpoint

Status: SPEC APPROVED by Graham 2026-11-25 (rules, worked examples and definition of done); plan in `slice_05_class_preview_plan.md` awaits his approval. Nothing is built.

## Goal
While the shipper types an item's weight and dimensions on the item page (decision 5), the front end shows the density and the suggested class, live, without saving a quote request. The endpoint calculates; it stores nothing.

## Facts from the existing code (for reference, not decisions)
- `calculate_density(weight_lb, length_in, width_in, height_in)` and `suggest_class(density)` live in `quotes/freight_class.py`; both are plain-input functions with no database. Density is for one handling unit; quantity does not change it (decision 2026-11-07).
- Existing field rules (Slice 1): weight, dimensions and quantity are positive whole numbers; limits 144 x 96 x 96 in and 4,000 lb per unit.
- The saved-request API returns density as a string rounded to 2 decimals ("9.60"), with the class chosen from the unrounded density.

## Rules
- Method: POST, because the input is a body and nothing is stored (Graham: "post is ok", 2026-11-25). URL: `/api/class-preview/` (Graham: "ok I accept this url with this name", 2026-11-25, after the agent explained what the URL is for and what "class-preview" refers to; the agent read this as the first name offered, `class-preview`, not the longer alternatives).
- Input: one unit per call: `weight_lb`, `length_in`, `width_in`, `height_in` (Graham: "i choose one unit per call", 2026-11-25; no reason stated). Quantity is not an input, because it does not change density.
- Output: `density` and `suggested_class` for that one unit. Running totals are not returned: with one unit per call the browser adds them up, and the price preview will return the server's total weight (Graham confirmed 2026-11-25: "yes i confirm", after the agent explained that totals add nothing with one unit per call; no further reason stated).
- Density format: the same 2-decimal string as the saved-request API (Graham: "density format is ok", 2026-11-25).
- Required fields: a missing or invalid required field (weight and the three dimensions; zero, negative, fractional or over the limits) returns a 400 with the same field messages as the quote request. Optional fields left empty are not an error and show as blank (Graham, 2026-11-25: "Forms that the customer is required to fill out can show a 400. Forms that the customer is not required to fill out can be shown as blank."). Consequence for the agent to check with Graham: the preview takes only weight and dimensions, which are all required, so an incomplete item would return a 400; the front end would then decide when to call (for example only once all four are filled) and show blank until then.
- Authentication: none for now (Graham: "authentication may be implemented at a later date but not today", 2026-11-25). Matches the rest of the API until accounts exist.

## Worked examples (PROPOSED by the agent 2026-11-25; APPROVED by Graham 2026-11-25: "i approve these examples"; expected values calculated by hand from the density formula and the class table in `quotes/freight_class.py`, and checked with a short calculation, not with the endpoint, which does not exist yet)
All requests are `POST /api/class-preview/` with `weight_lb`, `length_in`, `width_in`, `height_in`. A success is a 200 with `density` and `suggested_class`.

### Case 1: a normal unit, density rounds up for display
- 500 lb, 48 x 40 x 48 in. Density 864,000 / 92,160 = 9.375, shown as "9.38". Class 100 (8 up to 10).
- Shows that the class comes from the unrounded density and the display is rounded.

### Case 2: boundaries
- 2a: 35 lb, 12 x 12 x 12 in. Density exactly 35, shown "35.00". Class 55 (a boundary belongs to the upper tier).
- 2b: 34 lb, 12 x 12 x 12 in. Density 34, shown "34.00". Class 60.

### Case 3: very light unit
- 10 lb, 48 x 40 x 48 in. Density 0.1875, shown "0.19". Class 400 (below 1 lb per cubic foot).

### Case 4: the largest allowed unit
- 4,000 lb, 144 x 96 x 96 in. Density about 5.2083, shown "5.21". Class 175 (4 up to 6).

### Case 5: invalid input (each is a 400 naming the field; message text the same as the quote request's, to be copied from its existing tests)
- 5a: `weight_lb` 0. 5b: `weight_lb` 4,001. 5c: `length_in` 145. 5d: `width_in` 40.5 (fractional). 5e: `height_in` missing.
- 5f: a GET to the URL returns 405 (the endpoint accepts POST only).

## API
| Method and path | Purpose |
|---|---|
| `POST /api/class-preview/` | Body: `weight_lb`, `length_in`, `width_in`, `height_in` (one unit). Returns 200 with `density` (2-decimal string) and `suggested_class`. Stores nothing. |

No authentication for now. Any other method returns 405.

## Definition of done (DRAFT by the agent 2026-11-25; APPROVED by Graham 2026-11-25: "i approve the definition of done")
The class preview is done when `python manage.py test`, `ruff check .` and `ruff format --check .` all pass, and tests exist and pass for:
- Cases 1 to 5 above, used verbatim: status, `density` and `suggested_class` for each success; status and the field named for each failure.
- The endpoint saves nothing: the number of quote requests and handling units is the same after a call as before, for a success and for a failure.
- The class and density come from `calculate_density` and `suggest_class` in `quotes/freight_class.py`, with no second copy of the table or the formula.
- The field rules (positive whole numbers, 144 x 96 x 96 in and 4,000 lb limits) are the same rules the quote request uses, not a copy that can drift.
- Every decision made while building is logged in `docs/decisions.md`. The README endpoint list gains `POST /api/class-preview/`.

## Out of scope
- Price (that is the separate price preview).
- Saving anything.
