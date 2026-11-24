# Security and data

- **Sign in** is required on every route except sign in and the signed application webhook. Sessions are httpOnly cookies set by the web app; the API stays private. Changes through the web app need a header a cross site page cannot send.
- **Roles:** owner (everything) and approver (decide approvals, send scorecards, plan and score). Only the owner can delete a candidate, import voluntary labels, run the demo reset and use the kill switch.
- **Identity hiding** runs before anything reads a resume. While blind mode is on the server refuses to return names, emails or schools, whatever the page asks for.
- **Untrusted text:** a resume is data. Lines that talk to the scorer are flagged, never scored and never quoted. Nothing in a resume can trigger an action.
- **Audit log:** hash chained and append only. The app refuses to edit or delete a row, and the chain check finds an edit made outside the app. The log holds the neutral candidate code, never a name or an email.
- **Fairness labels** sit in their own table and are read only by one module. A test checks this. Scores do not change when labels change.
- **Addresses people type** (a resume web address) go through a guard that refuses private networks, odd schemes and unsafe redirects.
- **Limits:** a sign in rate limit, a request rate limit, upload size caps.
- **Secrets** are only in the environment, never in the repository. `python3 tools/scan_secrets.py` scans the tree.
- **Personal data:** applicant text is stored. Delete on request or by retention. Deleting also takes the name out of the offer text and of any offer file already written. Backups keep it until they expire.
- **Someone who leaves:** declining or withdrawing a person closes their waiting offer (it shows as withdrawn, the approval is rejected, and nothing can be approved or written for it afterwards).
See `SECURITY.md` for reporting a problem.
