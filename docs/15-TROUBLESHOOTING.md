# Troubleshooting

Run `python3 tools/doctor.py` first. It tests each connection and prints a plain line per problem.

| You see | Why | Fix |
|---|---|---|
| `The server is not reachable` on every page | The web app cannot reach the API | Start the API, or fix `API_BASE_URL` |
| Sign in fails with a right password | The hash was copied with a space or line break | Make it again with `tools/hash_password.py` and paste it on one line |
| `Email or password is wrong` after a redeploy | `SESSION_SECRET` changed | Sign in again |
| Names are hidden and you want them | Blind mode is on while the role is at applied | Move the person to the shortlist, then use the Blind view button to show identity (it is logged) |
| A score is missing | The scorer threw the score away because a quote did not match the resume | Open the candidate, the warning names the criterion. Re score after fixing the rubric |
| Rubric will not edit | It is locked | Make a new version and lock it |
| `A second person must approve` (409) | The approver is the same person who asked | Sign in as the approver |
| The fairness page is empty | No labels yet, or groups under 10 people | Import voluntary labels as owner (Fairness page, Voluntary labels card); wait for more data |
| Doctor says an adapter is not set | A required variable is empty | See [variables](04-ENVIRONMENT-VARIABLES.md) |
| Audit page says the chain is broken | A row was edited outside the app | Restore the last backup and investigate who has database access |
| Export file missing | The export folder is not writable | Fix `EXPORT_DIR` or attach a volume |
| Upload refused | File is over `UPLOAD_MAX_BYTES` or not a supported type | Split or convert it |
