# CLAUDE.md — Freight Quote Clone

Django + Django REST Framework clone of the quoting/booking side of Freightquote (LTL freight).
All carriers, tariffs, fees and margins are SIMULATED and illustrative. No real carrier is called.

## Commands
Human runs these in the PyCharm venv on Windows. The agent's Linux workspace uses a separate venv at
`$HOME/venvs/freight` (Python 3.13, same pinned requirements); it is session-local and may need recreating with
`uv venv --python 3.13` + `uv pip install -r requirements.txt`. Never create a venv inside this folder from Linux.

- Install: `pip install -r requirements-dev.txt`
- Migrate: `python manage.py migrate`
- Run server: `python manage.py runserver`
- Tests: `python manage.py test`
- A slice is NOT finished until the full test suite passes.
- Lint: `ruff check .` and format check `ruff format --check .` (config in ruff.toml)
- Definition of done for any step: `python manage.py test` AND `ruff check .` both pass.

## Workflow rules
- Work in vertical slices; start each slice in plan mode and wait for approval before coding.
- Each slice has a spec in docs/slices/ and a definition of done (runnable tests).
- Never invent expected values. Worked examples in the spec are written by the human; tests must use them.
- Log decisions in docs/decisions.md. Do not edit docs/intervention_log.md (the human owns it).

## Domain rules (human to confirm/extend after writing the primer)
- Quotes are immutable once created.
- Money is `Decimal`, never float.
- A booking always references exactly one quote.
- An expired quote cannot be booked.
- Freight classification logic lives in one replaceable module.
- Booking lifecycle: booked -> picked up -> in transit -> delivered; cancelled allowed; invalid transitions rejected.
- Each shipper account sees only its own quotes and bookings.

## Conventions
- Follow patterns already used in shippo-clone and fishbowl-clone where they fit.
- Tests live beside each app in tests/ modules.
