# Connect your tools

Every connection is optional. The demo needs none. Settings are environment variables on the server (see [environment variables](04-ENVIRONMENT-VARIABLES.md)). Run `python3 tools/doctor.py` after each change. Every adapter below was written from the vendor's public docs and run only against a local stand in, so each is marked UNVERIFIED live. Keep `MODE=draft` while you test.

## Applicants in
- **CSV or a pasted resume:** nothing to connect. Use the Add applicants button.
- **Application email (IMAP):** set `MAILBOX_ADAPTER=imap` and the four IMAP variables. Slatehire reads unread messages whose subject says "Application for <role title>", adds the sender as the applicant and marks a message read only after it was added. It never sends mail.
- **Ashby, Workable, Greenhouse (read only):** set `ATS_ADAPTER` to the name and add the token. Use Add applicants, or `POST /api/intake/ats?role=<key>`. Nothing is written back to your ATS. Greenhouse Harvest v1 and v2 is announced for removal on 2026-08-31, so check before relying on it.
- **Signed webhook:** set `APPLICATION_WEBHOOK_SECRET`, then post JSON (`name`, `email`, `role`, `resume_text`) to `/api/webhooks/application` with the header `x-signature` set to the hex HMAC SHA256 of the raw body.

## Interview invites
`CALENDAR_ADAPTER=seed` keeps invites inside the app (the default). `calcom` or `google` sends a real invite, and only in live mode, with the kill switch off, after a confirm.

## Offers
`HANDOFF_ADAPTER=package` writes the approved offer as a text file in `EXPORT_DIR`. Open it in Breezedoc, DocuSign or any signing tool. No live call to a signing tool is built (Breezedoc's API could not be confirmed).

## Another tool
`prompts/04-recipes.md` has a prompt that has Claude Code write an adapter for a tool that is not built here.
