# Slice 4 Notes: Tracking Events

Status: NOTES ONLY and SHELVED (2026-11-24). Graham decided to build the Slice 5 front end first and add Slice 4 afterwards. Nothing here is a spec. Items under "Decided" are Graham's decisions from earlier in the project; everything under "Proposed" is the agent's suggestion and needs Graham's word. Budget when built: about 1 working day (webhooks are a stretch item on top of that).

## Decided
- Scope is tracking events only. The lifecycle is `booked`, `picked up`, `in transit`, `delivered`, with `cancelled` allowed; invalid transitions are rejected (CLAUDE.md domain rules).
- Cancelling is allowed only while the status is `booked` (Slice 3 spec). A later status never goes back to `cancelled`.
- Webhooks are a stretch item and the first thing cut. If built, version 1 is a signed payload sent synchronously on each event with every attempt logged (about half a day); retry with backoff and a background worker are deferred (decision 2026-11-12).
- The reweigh adjustment and invoice variance are deferred out of Slice 4 (decision 2026-11-12).
- Cut order if time runs short: webhooks first, then accounts and per-shipper isolation.

## What Slice 3 prepares (so this slice is purely additive)
- Status changes go through one lookup in the code with one function `can_transition(current, new)`. Slice 3 holds `booked` to `cancelled`.
- Slice 4 extends the lookup to:

| From | May change to |
|---|---|
| `booked` | `picked up`, `cancelled` |
| `picked up` | `in transit` |
| `in transit` | `delivered` |
| `delivered` | (nothing) |
| `cancelled` | (nothing) |

- The booking's `status` field already accepts the new values once its choices list is extended (a migration with no data change).
- The Slice 5 front end shows statuses through one label map with a fallback, and ignores an `events` field it does not know.

## Proposed (not decided)
- A `TrackingEvent` table, immutable like quotes: the booking (protected), the new status, when the event occurred, a short location text (for example "Dallas, TX terminal"), an optional note, and when it was recorded. Events are never edited or deleted; a correction is a new event.
- `POST /api/bookings/{id}/events/` records an event and changes the booking's status in one transaction, through `can_transition`. An invalid change is a 409 with the reason, in the Slice 3 error format. A missing or invalid body is a 400.
- `GET /api/bookings/{id}/events/` lists the history, oldest first. The booking response gains an `events` list.
- Who sends the events: in this project there are no real carriers, so events come from the API (for demos, from the admin or a small management command that "advances" a booking). Nothing is simulated automatically.
- Event times are passed in or read from the same `get_now()` seam used in Slices 2 and 3, so tests supply the clock.
- Booking labels and the bill of lading are unaffected by events.

## Worked examples Graham would write (placeholders)
- A booking moves booked, picked up, in transit, delivered, with the history in order.
- An invalid change is rejected (for example booked to delivered, delivered to in transit, a cancelled booking to picked up) and leaves the history and the status unchanged.
- A booking that is already `picked up` can no longer be cancelled.

## What the front end needs from this slice (Slice 5, tracking screen)
- A booking's status and its events list, oldest first, to draw a timeline.
- A friendly label and an icon for each status.
- Until this slice is built, the front end shows `booked` and `cancelled` only and no timeline.

## Open questions
1. How should demo events be created (admin, a management command, or a small "advance" endpoint)?
2. Does a `delivered` event record who signed, or a delivery time only?
3. Do events carry a location, and if so, free text or structured fields?
4. Is the webhook stretch still wanted if the front end uses the time?
