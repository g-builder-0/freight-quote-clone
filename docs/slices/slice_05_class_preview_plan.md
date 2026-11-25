# Slice 5 backend change 1: class preview plan

Status: PROPOSED by the agent 2026-11-25; awaits Graham's approval. The spec (`slice_05_class_preview.md`) wins if the plan and spec disagree. Names marked "proposed" are the agent's suggestions, not decisions. Nothing is built. Budget: well under half a day (agent's estimate, not measured).

## Approach
Same as earlier slices: tests first, then the smallest code that passes them. The endpoint adds no new rule. It reuses the four field definitions on `HandlingUnit` (so the limits and messages cannot drift from the quote request) and the existing density and class code (so the class table and formula are not copied).

## Steps

### 1. Tests (proposed `quotes/tests/test_class_preview.py`)
- Cases 1 to 4 from the spec (200, `density` string, `suggested_class`).
- Case 5a to 5e: each returns 400 with the failing field named; message text copied from what the quote request returns for the same input (checked against the existing quote request tests, not invented). 5f: GET returns 405.
- The endpoint saves nothing: the counts of `QuoteRequest` and `HandlingUnit` are the same before and after, for a success and for a failure.
- The tests are run first and shown failing (the URL does not exist yet).

### 2. Input serializer (proposed `ClassPreviewSerializer` in `quotes/serializers.py`)
- A `ModelSerializer` on `HandlingUnit` with only `weight_lb`, `length_in`, `width_in`, `height_in`. Because the fields come from the model, the whole-number rule, the minimum of 1 and the limits (4,000 lb, 144 x 96 x 96 in) are the same ones the quote request enforces. All four are required.

### 3. View and URL (proposed `ClassPreviewView` in `quotes/views.py`, route in `quotes/urls.py`)
- A POST-only view (GET and the other methods return 405). It validates the body with the input serializer, builds an unsaved `HandlingUnit` from the validated values (never saved, no quote request attached), and returns its `density` and `suggested_class`.
- The response uses a small output serializer that subclasses `HandlingUnitSerializer` with `fields = ["density", "suggested_class"]`, so the 2-decimal string and the round-half-up rule are the existing ones, not a copy. The view reads `density` and `suggested_class` from the existing `HandlingUnit` properties, which call `calculate_density` and `suggest_class`.
- Route: `path("class-preview/", ClassPreviewView.as_view())` added to `urlpatterns`, giving `POST /api/class-preview/`.
- No authentication (spec).

### 4. Finish
- Run `python manage.py test`, `ruff check .` and `ruff format --check .`; report the counts (the suite had 340 tests after Slice 3).
- Add `POST /api/class-preview/` to the README endpoint list.
- Draft the `docs/decisions.md` rows for anything decided while building; Graham commits them.
- No migration: no model changes.

## Not changed
- No model, migration or change to existing endpoints. Existing serializers are only subclassed, not edited.

## Questions for Graham
1. Is it acceptable that the endpoint builds an unsaved `HandlingUnit` object in memory to reuse the model's `density` and `suggested_class`, rather than calling `calculate_density` and `suggest_class` directly? (Same code either way; the model route avoids repeating the class-name formatting such as "92.5".)
2. Approve this plan?
