# Slice 1: Foundations and Quote Request

Status: READY FOR PLAN REVIEW (all HUMAN inputs resolved 2026-11-10; some are defaults applied because Graham had no preference, see docs/decisions.md).

## Goal
A DRF project with a QuoteRequest that can be created and read through the API, with validation and a
density-based suggested freight class. No pricing, carriers or bookings yet (Slices 2+).

## Models (from the build plan)
**QuoteRequest**
- origin address, destination address (street, city, state, postal code)
- origin location type and destination location type: business dock, residential, limited access, construction site
- requested pickup date
- one or more handling units

**HandlingUnit** (belongs to one QuoteRequest)
- unit type: pallet, crate, drum or carton
- quantity
- length, width, height (inches)
- weight (pounds)
- stackable (yes/no)
- commodity description
- NMFC code (optional) and/or freight class (optional)
- computed: density (lb per cubic foot) and suggested class

## Validation rules
- Pickup date must be a business day AFTER today (the real product recommends at least a day's notice). Today, past
  dates and weekends (Saturday, Sunday) are rejected. "Today" is the server's current date in America/Chicago.
- Holidays are NOT considered in Slice 1 (weekdays only). The business-day test must live in ONE small function
  (e.g. is_business_day(date)) used by validation, so US holidays can be added later (for example with the `holidays`
  package) by changing that function, its tests, requirements.txt, this spec and the decision log. The check runs
  only when a request is created; stored requests are not re-validated.
- Weight, dimensions and quantity must be positive WHOLE numbers (ACCEPTED by Graham 2026-11-11). Dimensions are whole
  inches and weight is whole pounds; the API rejects fractional values (for example 41.5) with a clear error message.
  Shippers are expected to round measurements up to the next whole inch and pound before submitting. The density
  result is still a Decimal and is still not rounded before the class lookup.
- A QuoteRequest must have at least one handling unit.
- Location type must be one of the four allowed values.
- A user-supplied freight class (optional) must be one of the 18 standard NMFC classes: 50, 55, 60, 65, 70, 77.5, 85,
  92.5, 100, 110, 125, 150, 175, 200, 250, 300, 400, 500 (ACCEPTED by Graham 2026-11-11). Anything else is rejected. The 18
  classes are kept in one constant, separate from the 13-tier density table, and are used ONLY to validate a supplied class,
  never to suggest one. The check proves a class is a real NMFC class, not that it is the right class for the commodity.
  Classes 77.5 and 92.5 are decimals, so a supplied class is stored and returned in the same representation as the suggested
  class (the agent proposes the type in its plan).
- A user-supplied NMFC code (optional) is checked for format only (ACCEPTED by Graham 2026-11-11): 4 to 6 digits, with an
  optional hyphen and a 1- or 2-digit sub-number. Leading and trailing spaces are trimmed. Valid: 153760, 61780, 153760-03,
  153760-3. Invalid: abc, 12, 1234567, 153760-, 153760 sub 3. The check does NOT confirm the code exists or fits the
  commodity (that needs the paid NMFC database). Keep the pattern in one place so it is easy to change.
- Size and weight limits per handling unit (ACCEPTED by Graham 2026-11-10). Dimensions in inches, weight in
  pounds. "Hard limit" = rejected by validation. "Typical" = realistic range for test data and worked examples.
  The typical ranges are my synthesis of commercial sources, not an official standard; carriers set their own limits.

  | Value  | Hard limit (reject above) | Typical range for realistic data |
  |--------|---------------------------|----------------------------------|
  | Length | 144 (12 ft)               | 40 to 96                         |
  | Width  | 96 (8 ft)                 | 36 to 48                         |
  | Height | 96                        | 24 to 72 (loaded, incl. pallet)  |
  | Weight | 4,000                     | 150 to 2,500                     |

  All values must also be greater than zero. No minimum size was found in sources; hard lower bound is just > 0.
  Reference points: standard US pallet 48 x 40; loaded height commonly 48 to 60, some receivers cap at 72; parcel
  limit 108 in length / 150 lb (UPS); LTL commonly up to about 12 ft long and 8 ft wide.
- Addresses (default applied 2026-11-10, Graham had no preference): US only. Street, city, state, postal code are
  required. State must be a valid 2-letter US state or DC code. Postal code is 5 digits, with optional ZIP+4
  (12345 or 12345-6789). No check that the address really exists.
  Addresses are stored as flat fields on QuoteRequest (origin_street, origin_city, origin_state, origin_postal_code and the
  same four with a destination_ prefix), not in a separate Address model (ACCEPTED by Graham 2026-11-11). The state and ZIP
  rules are written once, as shared validators used by both the origin and destination fields.
  A saved-address book may be added later as a separate SavedAddress model whose values are COPIED into a request;
  a request never links to an editable shared address row, so old requests and quotes cannot change.
- Handling unit type must be one of: pallet, crate, drum, carton (default applied 2026-11-10, Graham had no
  preference). Keep the allowed values in one place so they are easy to extend.

## Density and class
- Density is calculated per handling unit. Weight and dimensions are for ONE handling unit (e.g. a whole loaded pallet,
  including the pallet). Quantity is the number of identical units and does not change density.
- Formula (inches and pounds in), computed with a SINGLE division:
  - density = (weight_lb x 1728) / (length_in x width_in x height_in)   (lb per cubic foot)
  - class = lookup of density in the accepted table below
  - 1728 = cubic inches in one cubic foot. This is the same as weight / (L x W x H / 1728), but multiplies first and
    divides last, so no rounded intermediate volume is ever divided into the weight.
- Use Decimal throughout. Do NOT compute a separate volume_ft3 value and divide by it, and do NOT round the density
  before the class lookup. Round density only for display (default: 2 decimals; Graham may change).
  Example: 34.96 is class 60 even if displayed as 35.0.
- A density that is exactly on a boundary must land in the upper class (35 exactly is class 55). Tests must include
  such a case computed from whole-number inputs.
- The density-to-class table lives in ONE replaceable module, separate from models and views.
- That module also exposes a version identifier, `CLASS_TABLE_VERSION = "NMFTA-2025-1"` (NMFTA Docket 2025-1).
  It must change whenever any boundary or class in the table changes. Slice 1 does not store it anywhere; Slice 2 quotes
  will record it (see `docs/slices/slice_02_notes.md`). Tests assert that the constant exists and is a non-empty string.
- The suggested class is computed each time a request is read; it is NOT stored on HandlingUnit (see `docs/decisions.md`, 2026-11-10).
- The table below is accepted. The agent must not alter it.

- If the user supplies a class, store it; the suggested class is returned alongside it, never overwriting it.

### Density-to-class table (checked against NMFTA 2026-11-06; ACCEPTED by Graham 2026-11-06)
Density in lb per cubic foot. Lower bound inclusive, upper bound exclusive.

| Density (lb/ft3)        | Class |
|-------------------------|-------|
| less than 1             | 400   |
| 1 to less than 2        | 300   |
| 2 to less than 4        | 250   |
| 4 to less than 6        | 175   |
| 6 to less than 8        | 125   |
| 8 to less than 10       | 100   |
| 10 to less than 12      | 92.5  |
| 12 to less than 15      | 85    |
| 15 to less than 22.5    | 70    |
| 22.5 to less than 30    | 65    |
| 30 to less than 35      | 60    |
| 35 to less than 50      | 55    |
| 50 or greater           | 50    |

Caveats:
- This is the 13-tier density scale NMFTA introduced with Docket 2025-1, effective July 19, 2025. It applies to
  freight with no special handling, stowability or liability concerns. Freight with such concerns, or with a
  fixed commodity class, can have a different class; the suggested class in this slice is only a density-based
  suggestion.
- All 13 rows match NMFTA's own publications: the FCDC Procedures 2025 (full density scale) and Disposition
  Bulletin 1371 (Docket 2025-1, "approved as docketed"). Secondary sources (Freight Sidekick, PNG Worldwide) agree.
  A carrier tariff (FedEx Freight 100 Series) shows the same thresholds from 15 pcf up.
- Many web pages still show an older 18-class commodity chart (with classes such as 77.5, 110, 150, 200, 500).
  That is not this density scale. Do not mix them.
- This is a simplified density-only suggestion, not an official NMFC implementation. Do not copy NMFC item listings
  or the commodity database. State this in the README.
- Boundary rule: NMFTA words each tier as "X but less than Y" and the top tier as "50 or greater", so the lower bound
  is inclusive and the upper bound exclusive (35.0 is class 55, 34.99 is class 60).

Sources:
- National Motor Freight Traffic Association. (2025). *FCDC procedures 2025*. https://nmfta.org/wp-content/media/2025/01/FCDC-Procedures-2025.pdf
- National Motor Freight Traffic Association. (2025, March). *Notice of disposition, Bulletin 1371 (Docket 2025-1)*. https://nmfta.org/wp-content/media/2025/03/Disposition-Bulletin-1371-1.pdf
- National Motor Freight Traffic Association. (n.d.). *2025 NMFC changes*. https://info.nmfta.org/2025-nmfc-changes
- Freight Sidekick. (2025, March 27). *Navigating the 2025 NMFTA changes*. https://freightsidekick.com/resources/articles/navigating-the-2025-nmfta-changes
- PNG Worldwide. (n.d.). *2025 NMFC class changes: What shippers need to know*. https://pngworldwide.com/?p=6560
- Old Dominion Freight Line. (n.d.). *NMFTA resource page: Navigating the ongoing NMFC changes*. https://www.odfl.com/us/en/resources/freight-knowledge/odfl-blog/nmfc-class-changes.html

## Worked examples (hand-calculated by Graham 2026-11-08; independently re-checked; used verbatim as test expectations)
Density = (weight x 1728) / (L x W x H), lb per cubic foot, exact. Quantity is 1 in every case.

| # | Case | Weight (lb) | L x W x H (in) | Qty | Density (lb/ft3) exact | Expected class |
|---|------|-------------|----------------|-----|------------------------|----------------|
| 1 | Ordinary mid-density pallet | 400  | 60 x 40 x 30 | 1 | 48/5 = 9.6                  | 100 |
| 2 | Very dense unit             | 1500 | 52 x 36 x 28 | 1 | 4500/91 = 49.4505494...     | 55  |
| 3 | Light, bulky unit           | 250  | 41 x 36 x 72 | 1 | 500/123 = 4.0650406...      | 175 |
| 4 | Exact boundary (35.0)       | 2240 | 48 x 48 x 48 | 1 | 35 exactly                  | 55  |
| 5 | Just under boundary         | 2239 | 48 x 48 x 48 | 1 | 2239/64 = 34.984375         | 60  |

Notes:
- Cases 4 and 5 use whole-number inputs so the boundary is exact. Case 4 must be class 55 (35 is in the 35-to-under-50
  range) and case 5 class 60. Together they catch off-by-one errors in either direction.
- Case 2 is close to the 50 boundary (49.45) on purpose.
- Tests must compare the class using the unrounded density (see Density and class). Rows 2 and 3 have repeating
  decimals, so tests should assert the class, and assert density with a stated tolerance or as an exact fraction.

## API (approved by Graham 2026-11-10: create, retrieve and list only; no update or delete in Slice 1)
- POST /api/quote-requests/ — create with nested handling units; response includes density and suggested class per unit
- GET /api/quote-requests/{id}/ — read
- GET /api/quote-requests/ — list, PAGINATED (ACCEPTED by Graham 2026-11-11). Uses DRF's built-in page-number pagination;
  the response is an object with count, next, previous and results. Newest first, with the id as a tiebreaker so pages are
  stable. Page size is proposed by the agent in its plan (suggestion: 20). Tests cover the response shape, a second page
  and the ordering.
- Density in responses is a JSON STRING, rounded to 2 decimals for display (for example "9.60"), not a JSON number
  (ACCEPTED by Graham 2026-11-11). This keeps exact decimals exact for clients and matches DRF's default for Decimal fields.
  API tests assert the string value. The class is still chosen from the unrounded density.
- Authentication and per-account isolation come in Slice 5; not in this slice.

## Definition of done
- `python manage.py test` and `ruff check .` pass.
- Tests cover: valid request; each invalid case above; pickup date on weekend, today and past; zero and negative
  weight and dimensions; no handling units; the five worked examples (including the boundary case); `CLASS_TABLE_VERSION` exists; a valid and an invalid user-supplied class; a valid and an invalid NMFC code.
- A request can be created and fetched through the API.

## Out of scope
Pricing, carriers, quotes, bookings, documents, webhooks, accounts, front end.

## Open questions
None recorded by Graham as of 2026-11-10. The agent must raise any ambiguity it finds as a question in its plan, not guess.
