# Freight Quote Clone

LTL freight quote and booking API (Django REST Framework). Work in progress; the spec for each slice is in `docs/slices/`.

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
- No authentication yet.
