# Deploy the API and database on Railway

Written from the vendor's docs. Not run against a real Railway account (UNVERIFIED). The repository's CI workflow builds the Docker images on a GitHub machine, which shows they build, not that Railway accepts them.

1. In Railway create a new project from the GitHub repository.
2. Add a Postgres database to the project.
3. Open the API service, Settings: set the Dockerfile path to `apps/api/Dockerfile` and the health check path to `/health`. The repo also holds `deploy/railway/railway.json` with the same values. Railway has said config files are being phased out, so prefer the dashboard settings.
4. Open Variables and add the values from [the variables guide](04-ENVIRONMENT-VARIABLES.md): `SESSION_SECRET` (32 or more random characters), `DEMO_MODE=false`, `MODE=draft`, `COMPANY_NAME`, the owner sign in and the second person (`APPROVER_EMAIL`, `APPROVER_PASSWORD_HASH`; put a hash inside single quotes), and `DATABASE_URL` set to the Postgres address with the scheme `postgresql+psycopg://`.
5. Attach a volume and point `EXPORT_DIR` at it so offer files survive a restart.
6. Add a second service from the same repository for the worker, with the start command `python -m slatehire.worker` and the same variables.
7. Run the tables once: open a shell for the API service and run `alembic upgrade head` in `apps/api`.
8. Copy the public address to Vercel as `API_BASE_URL`, or add a web service the same way.

Check: open `/health` on the API address and expect a short ok answer. Then follow the [go live checklist](09-GO-LIVE-CHECKLIST.md).
