# Connect your tools

Every connection is optional. The demo needs none. Settings are environment variables on the server (see [environment variables](04-ENVIRONMENT-VARIABLES.md)). Run `python3 tools/doctor.py` after each change. Every adapter below was written from the vendor's public docs and run only against a local stand in, so each is marked UNVERIFIED live. Keep `MODE=draft` while you test.

## Applicants in
- **CSV or a pasted resume:** nothing to connect. Use the Add applicants button.
- **Application email (IMAP):** set `MAILBOX_ADAPTER=imap` and the four IMAP variables. Slatehire asks the mail server for unread messages whose subject has the word "Application", so a shared inbox is safe: every other message is never fetched, stored or marked read. The role is read from a subject written as "Application for <role title>" (an exact title or key wins; a subject that fits two roles is not guessed, it goes to the "not added" list). The resume is the first attachment that can be one (PDF, text, markdown or RTF, in the order they arrive); pictures, vCards and calendar invites are skipped, and a Word or Pages file is not read, so that applicant enters flagged "Resume missing". With no such attachment the message body is the resume. A message is marked read after it was dealt with: added, a duplicate, or not added with a line on the Candidates page saying why. It never sends mail.
- **Ashby, Workable, Greenhouse (read only):** set `ATS_ADAPTER` to the name and add the token. Write the job id of the role in your ATS on the Roles page ("Your ATS", or `PUT /api/roles/<id>` with `ats_job_id`: the Greenhouse job id, the Workable job shortcode or the Ashby job id). Then use Add applicants, or `POST /api/intake/ats?role=<key>`. A pull brings in only the people who applied to that job, and it is refused for a role with no job id, because otherwise every candidate for every job in your ATS would be put into the role and scored. The job filter was written from the vendors' docs and is UNVERIFIED against the real services. Nothing is written back to your ATS. Greenhouse Harvest v1 and v2 is announced for removal on 2026-08-31, so check before relying on it.
- **Signed webhook:** set `APPLICATION_WEBHOOK_SECRET`, then post JSON (`name`, `email`, `role`, `resume_text`) to `/api/webhooks/application` with the header `x-signature` set to the hex HMAC SHA256 of the raw body.

## Interview invites
`CALENDAR_ADAPTER=seed` keeps invites inside the app (the default). `calcom` or `google` sends a real invite, and only in live mode, with the kill switch off, after a confirm.

## Offers
`HANDOFF_ADAPTER=package` writes the approved offer as a text file in `EXPORT_DIR`. Open it in Breezedoc, DocuSign or any signing tool. No live call to a signing tool is built (Breezedoc's API could not be confirmed).

## Another tool
`prompts/04-recipes.md` has a prompt that has Claude Code write an adapter for a tool that is not built here.
