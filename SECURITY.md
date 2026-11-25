# Security

## Reporting a problem
Please do not post security problems in a public issue. Use the Security tab of the repository and choose Report a vulnerability, which opens a private advisory. We aim to acknowledge it within 5 working days. Include steps to reproduce. Never include real keys, passwords or applicant data.

## What was checked
- Sign in on every route except sign in, sign out and the signed application webhook. Role checks (owner only for deletes, group labels, running the fairness report, switching blind mode off, demo reset and the kill switch). Sign in is limited per visitor, per address and per account, the address is compared without spaces or capitals, an unknown address costs the same work as a wrong password, the session cookie is httpOnly, and a header the web app adds to every change keeps a page on another site from posting for a signed in person.
- The public demo logins (including the demo approvers) and the demo buttons switch off by themselves the moment `OWNER_PASSWORD_HASH` is set. The API and the worker refuse to start outside the demo on an example `SESSION_SECRET`, and a live start is refused while `COMPANY_NAME` or `OWNER_EMAIL` is still an example.
- Sign in behind a proxy: a browser that signed in before carries a signed note (httpOnly cookie, made only after a verified password, never a session) and its tries are counted on their own. Residual risk: if `FORWARDED_ALLOW_IPS` is not set on the API, every visitor looks like one address and a stranger failing at the owner's account can hold up a first sign in from a new browser for as long as it goes on; the settings page warns, and docs 06, 07 and 08 say how to set it.
- Erasure that lasts: the hashes of deleted people are made with `SUPPRESSION_KEY`, which lives only in the environment, so a copy of the database cannot be used to test whether a known address was erased. After a restore, `python -m slatehire.reapply` erases again whoever asked later (docs/11).
- Offers: the person who last wrote the terms cannot approve them, as well as the person who asked for approval. A line break or other control character in a name or title cannot reach an offer letter. The approval screen shows the whole letter that will be sent.
- Mail: applications are read with `BODY.PEEK[]`, so a message stays unread until its application is stored. One message that cannot be stored is skipped on its own and logged with a reason and no candidate text; the rest of the batch goes on. The mailbox connection checks the server certificate and name, and plain text is accepted only for a mail server on the same computer.
- Every application that arrives by email, ATS or form and is not added (a duplicate, a missing resume, a refused file) has a line in the intake log with the reason, shown on the Candidates page. A person with no resume still gets an application, marked "Resume missing". An application is matched on its source and its reference together, so a reference sent by one source can never suppress an applicant who arrives from another.
- Erasure and retention: deleting a person also removes the offer text and file, the notes, the intake log lines for their email, and the free text written about them. Declined and withdrawn people are removed after `RETENTION_DAYS`, applicants nobody decided on after `OPEN_RETENTION_DAYS`, and intake log lines by age.
- Fairness: only the owner runs the report, the smallest group can be raised but never lowered below `FAIRNESS_MIN_GROUP`, a group below the floor is saved with its counts blanked ("fewer than N"), and an older report that flagged a group stays visible after a clean one.
- Request bodies are read in small pieces and refused as soon as they pass `MAX_BODY_BYTES` (a resume file: `UPLOAD_MAX_BYTES`). The web proxy takes the visitor address from the last hop only, matches blocked paths by whole segment after normalising them, and keeps an applicant's name and email out of addresses (they travel in headers), so access logs never hold them.
- Address guard for every address the app fetches: the name is resolved once and the connection is pinned to the address that passed the check, every redirect hop is checked again, and the whole fetch has a 30 second deadline. `ALLOW_HTTP_LOCAL_TARGETS` removes that protection and is flagged as a problem outside a test machine.
- The webhook signature (HMAC SHA256 of the raw body), with tests for a wrong signature, a replay and an oversized body.
- Redaction uses linear patterns with bounded repeats, tested against a hostile 60,000 character text under a time limit. A name that is also an ordinary word is removed from a resume only where it is written as a name.
- Resume text is treated as untrusted: instructions inside it (also with look alike letters, zero width characters or spread over lines) are flagged and, when aimed at the reader, never scored and never quoted (a line that only has the words of an instruction is flagged for a person and still scored), and cannot trigger an action. With `SCORER=model` the model's quote must contain a term the rubric looks for, and a level that differs by two or more from the rules is flagged for a person.
- Blind mode is enforced by the server, not the page, and so is the source of an application while the identity is hidden. A rubric that looks for a word that stands in for a protected attribute is refused when it is locked.
- The database refuses edits to a locked rubric, a sent scorecard and the audit log, and a test edits one outside the app and sees the chain break.
- Group labels are read by one module only, and a test checks that.
- Secret scan of tracked files (`python tools/scan_secrets.py`): nothing found.
- Dependency audit on 2026-11-23: `pip-audit` over the 45 installed third party Python packages and `pnpm audit` over all JavaScript packages both reported no known vulnerabilities. This covers only known, published problems on that date and was not repeated for 1.0.1.

## What was not checked
- No outside penetration test, and no test against real vendor accounts. Treat this as a careful self review, not an audit.
- The CI workflow builds the Docker images and starts the stack on a GitHub machine, but the deploy files were never run on a real Hetzner, Railway or Vercel account.
- Postgres only: the fixes were tested on SQLite. The one migration and the savepoint per message were not run on a live Postgres.
- A scoring rule that leans on gendered or age coded wording, and PDF parsing without a process of its own (it is capped by size, pages, page content and a time limit), are known and not fixed (docs/14). The web pages have no Content Security Policy yet.
- Marking a mail message read after it is stored is not stopped by the kill switch (the switch stops everything that leaves the app, and reading is not that).

## Two risks to know before you use it
- **Demo mode is public on purpose.** With `DEMO_MODE=true` and no owner password anyone who can reach the app can sign in with the published demo password and press the demo buttons. Never expose a demo to the internet with real applicant data in it.
- **A secret pasted anywhere is lost.** If you paste a key into a chat, an issue, a screenshot or Git, make a new one and revoke the old one at once.

## Supported versions
Only the latest release.
