# Slice 2 notes (requirements carried forward from Slice 1 decisions; not yet a spec)

Status: NOTES ONLY. Graham writes the Slice 2 spec later. These items come from decisions made on 2026-11-10.

- A quote is created by computing the class fresh from the current class table, then snapshotting the class, the price and
  `CLASS_TABLE_VERSION` on the quote. Do not copy a stored class from an old request.
- Quotes are never edited after creation. Old quotes are kept so anyone can see what was offered on a given date and under which table.
- A quote expires after a validity window (length to be decided in the Slice 2 spec). An expired quote cannot be booked.
- Booking check: a quote can be booked only if its recorded `CLASS_TABLE_VERSION` equals the current one. If it differs, reject
  the booking and require a new quote. Every quote that becomes a transaction must therefore reflect the current class table.
- Rates and fees will need the same version guard (rate table version); decide this in the Slice 2 spec.
- A re-quote after expiry or after a table change creates a NEW quote; the old one stays as history.
