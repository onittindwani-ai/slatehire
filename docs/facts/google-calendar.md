# Google Calendar

Checked 2026-11-22. https://developers.google.com/calendar

- VERIFIED: POST /calendar/v3/calendars/primary/events with scope calendar.events. sendUpdates defaults to no emails.
- UNVERIFIED: how to get the OAuth token. The adapter takes a token you already have.
- In this project: creates events only, tested against a mock, not run live (Tier B).

## Contract excerpt (2026-11-23)
Read at https://developers.google.com/workspace/calendar/api/v3/reference/events/insert: POST path, scopes, required start and end, sendUpdates values (all, externalOnly, none), attendee fields. Excerpt and test: mock/contracts/google_calendar. The adapter sends sendUpdates=all, so guests are told (its docstring said none; corrected). No discovery document was fetched.
