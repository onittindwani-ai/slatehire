# Cal.com (calendar)

Checked 2026-11-22. https://cal.com/docs/api-reference/v2

- VERIFIED: POST /v2/bookings with header cal-api-version 2026-02-25 and body start, attendee (name, timeZone, email), eventTypeId.
- UNVERIFIED: where the API key and the event type id live in the dashboard. The key is shown once.
- In this project: tested against a mock (mock/vendor_mocks.py). Never run against the real service. Slatehire only creates a booking, and only in live mode after a person confirms.

## Contract excerpt (2026-11-23)
Copied from the sibling repo Pipecairn (page text excerpts, no OpenAPI file fetched): mock/contracts/calcom. Test: mock/tests/test_contracts.py checks the header, the required body fields and the response parsing.
