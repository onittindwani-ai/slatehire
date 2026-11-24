# Updating

1. Read `CHANGELOG.md`.
2. Back up the database.
3. Pull the new version, then `make install`.
4. Run `alembic upgrade head` from `apps/api` on Postgres. SQLite demo databases are created on start.
5. Run `make test` and `python3 tools/doctor.py`.
6. Rebuild and restart the API, the worker and the web app.
7. Check the audit chain on the Audit log page.

The `packages/` folder is a copy of the shared base and is never edited here. Roll back by restoring the database backup and checking out the previous version.
