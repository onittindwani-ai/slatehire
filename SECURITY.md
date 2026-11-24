# Security

## Reporting a problem
Please do not post security problems in a public issue. Use the repository's private security advisory feature, or contact the maintainers privately. Include steps to reproduce. Never include real keys, passwords or applicant data.

## What was checked
- Sign in on every route except sign in, sign out and the signed application webhook. Role checks (owner only for deletes, imports of group labels, demo reset and the kill switch). Rate limit on sign in. httpOnly session cookie. A header the web app adds to every change, so a page on another site cannot post for a signed in person.
- The webhook signature (HMAC SHA256 of the raw body), with tests for a wrong signature and an oversized body.
- A guard on addresses the app fetches (private networks, odd schemes, redirects), with tests.
- Resume text is treated as untrusted: instructions inside it are flagged, never scored, never quoted, and cannot trigger an action. Tests include resumes that try to give orders to the scorer.
- Blind mode is enforced by the server, not the page. A test asks for identity in blind mode and is refused.
- The database refuses edits to a locked rubric, a sent scorecard and the audit log, and a test edits one outside the app and sees the chain break.
- Group labels are read by one module only, and a test checks that.
- Secret scan of tracked files (`python tools/scan_secrets.py`): nothing found.
- Dependency audit on 2026-11-23: `pip-audit` over the 45 installed third party Python packages and `pnpm audit` over all JavaScript packages both reported no known vulnerabilities. This covers only known, published problems on that date.

## What was not checked
No outside penetration test. No test against real vendor accounts. Docker images were not built here. Treat this as a careful self review, not an audit.

## Supported versions
Only the latest release.
