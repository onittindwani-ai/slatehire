# Quick demo (5 minutes, no accounts)

Everything in the demo is fictional: <!--n:seed.applicants-->90<!--/n--> applicants for <!--n:seed.roles-->3<!--/n--> roles, a locked rubric each, and a pipeline already moved by people.

## With Docker (not run here; the CI workflow builds the images and starts the stack on a GitHub machine)
1. Copy `.env.example` to `.env`, then set `DEMO_MODE=true` and `POSTGRES_PASSWORD` (any letters and digits: `openssl rand -hex 24`) in it. The example is not a demo on purpose, so a real install never starts with public passwords. The Docker demo also needs `ALLOW_DEMO_SERVER=true`, because the compose file uses Postgres.
2. Run `docker compose up`.
3. Open http://localhost:3000 and sign in with `owner@example.test` and the demo password shown on the sign in page.

## Without Docker
1. `make install` (needs uv or Python 3.12, and pnpm: run `corepack enable` or `npm i -g pnpm` if you do not have it).
2. In one terminal: `DEMO_MODE=true SESSION_SECRET=demo-secret-change-me-please make api`. (The demo needs `DEMO_MODE=true` in your shell or in `.env`: the example file is set up for a real install.)
3. In another: `pnpm build && pnpm --filter web start`.
4. Open http://localhost:3000.

## The path to try
1. **Pipeline.** Cards in Applied show "Candidate A0xx", not names. That is blind mode.
2. **Open a card.** The resume shows small tags where identity was. Point at a criterion on the right and its exact words light up on the left.
3. **Decline** needs a written reason. **Shortlist** another, then turn blind view off: the server only allows it after the shortlist and writes it to the audit log.
4. **Plan an interview** from the workspace. Interviewers send scorecards alone; the totals appear after.
5. **Approvals.** An offer waits. The person who drafted it cannot approve it. Sign out, sign in as `approver@example.test`, approve, then write the offer file from Offers.
6. **Run now** (top bar) brings in the next of <!--n:seed.inbox_emails-->4<!--/n--> fictional application emails and scores it, and tells you what it did (or that nothing new came). Nobody is moved. **Add applicants** also takes pasted text, a CSV, a resume file, your tracking system and the mailbox.
7. **Fairness** shows an indicator, with its warning that it is not legal advice.
8. **Audit log** shows the chain is intact (Check the chain). Mark someone hired from their workspace and **Onboarding** starts their 30, 60 and 90 day plan.
9. **Reset demo data** is in the command palette (Cmd+K or Ctrl+K), with a confirmation. A sign in as `viewer@example.test` can look at the pipeline, candidates, interviews and fairness and change nothing: its buttons are switched off and say why. The Offers page and the audit log are for the owner and the approver (the audit log for the owner only).
