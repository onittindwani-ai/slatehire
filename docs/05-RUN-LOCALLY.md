# Run locally

You need Python 3.12 (or uv, which fetches it), Node 22 (a newer Node works but is not the target) and pnpm (`corepack enable` or `npm i -g pnpm`). `make install` picks uv or python3.12 for you.

1. `make install` makes a virtual environment and installs the API and the web app.
2. Copy `.env.example` to `.env`. For the demo leave it as it is.
3. Start the API: `make api` (port 8000). Tables are created on first start for SQLite.
4. Start the worker if you want background jobs: `make worker`.
5. Build and start the web app: `pnpm build && pnpm --filter web start` (port 3000). `pnpm --filter web dev` for development.
6. Open http://localhost:3000.

Useful commands: `make test` (Python tests), `make doctor`, `make check-env`, `make e2e` (browser tests, needs Chrome), `make seed-check` (the held out measurements), `make counts`, `make docs-check`.

On Postgres run `alembic upgrade head` from `apps/api` with `DATABASE_URL` set.
