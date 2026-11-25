# Run locally

You need Python 3.12 (or uv, which fetches it), Node 22 (a newer Node works but is not the target) and pnpm (`corepack enable` or `npm i -g pnpm`). `make install` picks uv or python3.12 for you. On Ubuntu or Debian also run `sudo apt install python3-venv` first. On Windows use WSL 2 (Ubuntu) and work inside it: the commands here are for a Unix shell.

1. `make install` makes a virtual environment and installs the API and the web app.
2. Copy `.env.example` to `.env`. For the demo set `DEMO_MODE=true` in it (the example is set up for a real install). For your own install set `SESSION_SECRET`, `OWNER_EMAIL`, `OWNER_PASSWORD_HASH`, `APPROVER_EMAIL`, `APPROVER_PASSWORD_HASH` and `COMPANY_NAME` and keep `DEMO_MODE=false`; see [the variables guide](04-ENVIRONMENT-VARIABLES.md). With `DEMO_MODE=false` the database starts empty: add your roles, write and lock a rubric for each, then add applicants. The settings file is `.env` in the folder you start from.
3. Start the API: `make api` (port 8000). Tables are created on first start for SQLite.
4. Start the worker if you want background jobs: `make worker`.
5. Build and start the web app: `pnpm build && pnpm --filter web start` (port 3000). `pnpm --filter web dev` for development.
6. Open http://localhost:3000.

Useful commands: `make test` (Python tests), `make doctor`, `make check-env`, `make e2e` (browser tests, needs Chrome), `make seed-check` (the held out measurements), `make counts`, `make docs-check`.

On Postgres run `alembic upgrade head` from `apps/api`. It reads the same settings as the app (`DATABASE_URL` from the environment or from `.env`) and stops with a message when there is none, instead of guessing a database.
