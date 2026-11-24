# Workable (applicant tracking, read only)

Checked 2026-11-23. https://workable.readme.io

- VERIFIED: open the account menu at the top right, choose Integrations, then Generate new token and pick the scopes. The base is https://SUBDOMAIN.workable.com/spi/v3 and the token goes in an Authorization bearer header.
- UNVERIFIED: how a resume file is downloaded for a candidate. The adapter uses the candidate record fields we saw.
- In this project: tested against a mock. Never run against the real service. Read only.

## Contract excerpt (2026-11-23)
NONE. The public reference pages returned 404 and no machine readable spec was found, so the adapter's field names cannot be checked against a vendor page. See mock/contracts/workable/SOURCE.txt.
