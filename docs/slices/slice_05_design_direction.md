# Slice 5 design direction (front end)

Status: DRAFT proposed by the agent 2026-11-25 for Graham to approve or change. The direction itself is Graham's choice; the exact values below are the agent's proposal, taken from the Style A mockup shown to him, and are not approved. Nothing is built.

## Direction (Graham, 2026-11-25)
- Style A (the trade-desk look), with help pop-ups for customers who need them. His words: "option 3. Style A with help text pop ups for customers who need it".
- His reasons: ArcBest is his favorite of the sites compared; Style A is the closest to what would be wanted for an internal logistics site; and "I see how style b would appeal to the target customer", which the help pop-ups are meant to serve.

## Proposed values (agent's proposal)
- Colors: header and dark panels navy `#12284C`; primary button blue `#1B5FAA` with white text; body text `#14213D`; secondary text `#3B4A63`; borders `#C9D3E0` (outer) and `#E1E7EF` (between rows); table header and subtle panels `#EEF2F7` and `#F6F8FB`; tag background `#DDEBFA` with text `#0C3B73`; page background white.
- Contrast (agent's calculation, WCAG formula): white on blue 6.43:1, white on navy 14.65:1, body text on white 15.97:1, secondary text on white 8.95:1, tag text on tag background 9.18:1. All are above 4.5:1.
- Not yet chosen (no mockup shows them): error, warning and success colors. Proposal: pick them when the first error message is built, and check the contrast then.
- Type: the system sans-serif font; 14 px body, 12 px table headings, 13 px buttons, 18 to 20 px page headings; two weights only (400 and 500).
- Shape and spacing: 4 to 6 px corner radius; 14 px panel padding; 10 px row padding; rows separated by thin borders rather than separate cards.
- Buttons: one primary (blue) button per screen; other actions are outline buttons.
- Tags: small tinted labels such as "Lowest price" and "Fastest".
- Dark mode: not planned, unless Graham asks.

## Help pop-ups (Graham's choice; wording to be written per screen and approved by him)
- A small "?" icon beside a heading or field opens a pop-up with a plain-language explanation. It is optional: the page is complete without it. This is the same pattern as the "?" pop-up for line items (decision on results).
- Each pop-up opens with the mouse or the keyboard, closes with Escape or a close button, and returns focus to its icon.
- Pop-up text never hard-codes a limit or rule the API owns (decision 16, "prevent drift"); numbers come from `GET /api/limits/` or the API's own response.
- The wording of each pop-up is written when its screen is built and shown to Graham first; the agent does not invent policy statements.

## How this is used
- Referenced from `CLAUDE.md` so every session sees it (as the front-end guide recommends), once Graham approves it.
- Every screen is checked against it with screenshots at phone and desktop widths before Graham sees it.
