# Architecture

```
Browser -> Next.js web app (apps/web) -> /api proxy (cookie, CSRF header) -> FastAPI (apps/api) -> SQLAlchemy -> SQLite or Postgres
                                                                              |-> adapters (ATS, mailbox, calendar, hand off)
Worker (python -m slatehire.worker) -> jobs: mailbox, scoring, retention, onboarding
```

## Layers
- **packages/** is the shared base (settings, app shell, auth, mode and kill switch, UI kit). It is a frozen copy and is never edited here.
- **apps/api/src/slatehire** holds the product: `redaction.py` (hides identity before anything reads the text), `scoring.py` and `scoring_service.py` (rule scorer, quote check), `rubrics.py` and `rubric_service.py` (lock and signature), `pipeline.py` (stages and who may move), `interviews.py`, `offers.py`, `onboarding.py`, `fairness_service.py` (the only reader of group labels), `retention.py`, `guards.py` (the database refuses edits to locked rubrics, scorecards and the audit log), `untrusted.py` (resume text is data).
- **adapters/** are small classes behind one interface per category. Each has a seed version that works offline.
- **api/** has the routes, split into read, write, admin, public (the signed webhook), demo and auth.

## One applicant, end to end
1. Intake stores the original text in a private field and a redacted copy.
2. The scorer sees only the redacted copy, with the locked rubric, and returns a level and quotes per criterion.
3. Code checks each quote is a word for word piece of the redacted text and flags any line that talks to the scorer (left out of scoring) or only looks like an instruction (flagged, still scored), and text hidden in a PDF (left out, flagged).
4. A person moves the application. Only a person can.
5. Scorecards are written independently and stay hidden until each person sends theirs.
6. An offer needs person written terms, enough scorecards and a second person's approval, then a file is written.

## Data
`<!--n:tables-->17<!--/n-->` tables, `<!--n:api_paths-->60<!--/n-->` API paths. The audit log is hash chained. Demographic labels live apart from everything else.

## What is not here
No outbound email, no automatic rejection, no model call in the default path.
