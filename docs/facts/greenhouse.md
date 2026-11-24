# Greenhouse (applicant tracking, read only)

Checked 2026-11-23. https://developers.greenhouse.io/harvest.html

- VERIFIED: create a Harvest key under Configure, Dev Center, API Credential Management. It uses basic auth (key as user name, empty password) and the Link header for paging.
- VERIFIED: Harvest v1 and v2 are deprecated and are due to be removed on 2026-08-31. Check the page before relying on them. The adapter reads candidates only.
- In this project: tested against a mock. Never run against the real service. Read only.

## Contract excerpt (2026-11-23)
Read at https://docs.greenhouse.io/harvest.html (the old address redirects): basic auth with a blank password, paging by the Link header, and Harvest v1 and v2 removal on 2026-08-31 (migrate to v3). The candidate section was not read. Found: attachments moved to the application level in 2020, so the adapter's reading of candidate attachments may be wrong. Excerpt and test: mock/contracts/greenhouse. No machine readable spec was fetched.
