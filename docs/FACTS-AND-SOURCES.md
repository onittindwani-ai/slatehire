# Facts and sources

Every outside fact has a file in [facts](facts/) with the source address, the date checked and VERIFIED or UNVERIFIED. VERIFIED means the vendor's own public page said it. Nothing was run against a real vendor.

| Topic | File | Checked | Status |
|---|---|---|---|
| Ashby | [ashby](facts/ashby.md) | 2026-11-23 | Auth and permission VERIFIED, dashboard path and paging fields UNVERIFIED |
| Workable | [workable](facts/workable.md) | 2026-11-23 | Token steps VERIFIED earlier; the public reference pages returned 404 on a re check, resume download UNVERIFIED |
| Greenhouse | [greenhouse](facts/greenhouse.md) | 2026-11-23 | Auth and paging VERIFIED, removal on 2026-08-31, candidate fields and attachments UNVERIFIED |
| Breezedoc | [breezedoc](facts/breezedoc.md) | 2026-11-23 | UNVERIFIED (only a sign in page) |
| Cal.com | [calcom](facts/calcom.md) | 2026-11-22 | Booking call VERIFIED |
| Google Calendar | [google-calendar](facts/google-calendar.md) | 2026-11-22 | Event call VERIFIED |
| Mailbox over IMAP | [gmail](facts/gmail.md) | 2026-11-22 | App password steps VERIFIED |
| Hosting | [hosting](facts/hosting.md) | 2026-11-22 | Mixed, Docker UNVERIFIED |
| Libraries | [libraries](facts/libraries.md) | 2026-11-23 | From lock files |
| Four fifths rule | [four-fifths-rule](facts/four-fifths-rule.md) | 2026-11-23 | VERIFIED |

The model path is not an outside fact but is UNVERIFIED live in the same way: the request to the Anthropic Messages API (path, headers, structured output) follows the vendor docs as the hub base read them on 2026-11-23 and was run only against a local fake server. The vendor contract excerpts used by the adapter tests are under `mock/contracts/` (Cal.com, Google Calendar, Ashby, Greenhouse; Workable's public pages could not be read), with the URL and date of each.

Tool scoring evidence is in [tools and alternatives](TOOLS-AND-ALTERNATIVES.md). Re check a fact before you rely on it: vendor pages change.
