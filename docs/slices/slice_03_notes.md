# Slice 3 notes (requirements carried forward; not yet a spec)

Status: NOTES ONLY. Graham writes the Slice 3 spec later. Items agreed 2026-11-17.

- The booking stores the delivery contact (receiver name and phone or email). It is collected at booking, not on the quote request.
- If the quote has the appointment flag set, the delivery contact is required to book. Without the flag it is still needed for the bill of lading consignee details.
- The booking API accepts the receiver contact, the shipper contact and special instructions; these appear on the bill of lading.
- Booking is rejected if the quote has expired or if its `CLASS_TABLE_VERSION` or `RATE_TABLE_VERSION` differs from the current one (see the Slice 2 spec).
