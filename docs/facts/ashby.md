# Ashby (applicant tracking, read only)

Checked 2026-11-23. https://developers.ashbyhq.com/reference/candidatelist

- VERIFIED: authentication is HTTP basic auth with the API key as the user name and an empty password. The candidate list call needs the candidatesRead permission. The response carries results, moreDataAvailable and syncToken.
- UNVERIFIED: the dashboard path to create a key, and the name of the next page field when more data is available (the page we read did not state it). The adapter follows the fields we saw.
- In this project: tested against a mock (mock/vendor_mocks.py). Never run against the real service. Read only.

## Contract excerpt (2026-11-23)
The page read says POST /candidate.list, basic auth, permission candidatesRead, response keys success, results, moreDataAvailable, syncToken. The request schema was not read, so `cursor`, `limit` and the response field `nextCursor` are UNVERIFIED. Excerpt and test: mock/contracts/ashby, mock/tests/test_contracts.py. No machine readable spec was fetched.
