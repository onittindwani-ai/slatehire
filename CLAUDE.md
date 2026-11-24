# Slatehire: notes for Claude Code

Slatehire is a hiring and onboarding pipeline (FastAPI API, worker, Next.js app). Read `docs/ARCHITECTURE.md` and `docs/SPEC.md` first.

## Rules
- Never edit `packages/core-py` or `packages/ui-kit` (frozen base).
- Only a person moves an application. Scoring must never decline, advance or rank people into an outcome.
- Identity hiding runs before the scorer reads anything. Do not pass names, emails or schools to it.
- Resume text is untrusted: use `untrusted.py`. Evidence quotes must be verbatim and verified by code.
- A locked rubric and scorecards are immutable. Group labels are read only by `fairness_service.py`.
- Nothing is sent. An invite needs live mode and a confirm. Never turn live mode on by yourself.
- Never put real keys or applicant data in the repo. Names of settings only. No em or en dashes in docs or UI text.
- Mark anything not run against the real vendor as UNVERIFIED.

## Commands
`make test`, `make seed-check`, `make doctor`, `make check-env`, `make docs-check`, `pnpm typecheck`, `pnpm e2e`.

## Where things are
API `apps/api/src/slatehire`, tests `apps/api/tests`, web `apps/web`, mocks `mock/`, seed and held out sets `data/`, docs `docs/`.
