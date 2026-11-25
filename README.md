# Freight Quote Clone

LTL freight quote and booking API (Django REST Framework). Work in progress; the spec for each slice is in `docs/slices/`.

## Endpoints
Details, rules and worked examples are in the slice specs in `docs/slices/`.

| Method and path | Purpose |
|---|---|
| `POST /api/quote-requests/` | Create a quote request (route, items, pickup date). |
| `GET /api/quote-requests/` | List quote requests, newest first (paginated). |
| `GET /api/quote-requests/{id}/` | One quote request. |
| `POST /api/quote-requests/{id}/quotes/` | Create one quote per carrier for the request. |
| `GET /api/quote-requests/{id}/quotes/` | Every quote made for the request. |
| `GET /api/quotes/{id}/` | One quote with its line items. |
| `POST /api/quotes/{id}/bookings/` | Book a quote (shipper and receiver contacts, optional instructions). |
| `GET /api/bookings/{id}/` | One booking. |
| `GET /api/bookings/{id}/bill-of-lading/` | The bill of lading snapshot. |
| `GET /api/bookings/{id}/labels/` | Pallet labels, one per unit (409 if cancelled). |
| `POST /api/bookings/{id}/cancel/` | Cancel a booking with a reason. |
| `POST /api/class-preview/` | Density and suggested class for one unit; saves nothing. |
| `GET /api/limits/` | The size, weight and text-length limits the API enforces, for counters and messages. |

## Known simplifications (on purpose)
- Tariffs are invented and illustrative (3 carriers, 5 weight breaks), not real carrier rates.
- Zone factor is 1.00 + 0.10 per difference in the first ZIP digit.
- Transit days = max(1, 1 + ceil(gap/2) + carrier adjustment), business days from pickup, holidays ignored.
- One minimum charge per carrier.
- Weight-break rating-up rule is not built: 1,999 lb costs $679.66 but 2,000 lb costs $560.00 (mid carrier, class 100, same zone).
- No broker markup (the `apply_markup` seam returns the price unchanged).
- Accessorial fees ignore which end of the trip they apply to.
- No reweigh or reclassification adjustment after booking.
- Per-request quote history is unpaginated (3 quotes per click); pagination belongs on a future "all my quotes" list.
- Bookings: the bill of lading has no payment terms and no PDF form; a booking cannot be edited (only cancelled); no reweigh adjustment; no tracking statuses beyond `booked` and `cancelled` (Slice 4).
- No authentication yet.
