# Updating

1. Read `CHANGELOG.md`.
2. Back up the database.
3. Pull the new version, then `make install`.
4. Run `alembic upgrade head` from `apps/api` on Postgres. It reads the same settings as the app (`DATABASE_URL` from the environment or `.env`). Docker compose runs it for you on start. SQLite demo databases are created on start. Compare your settings file with the example: `python3 tools/check_env.py` names the settings your file is missing.
5. Run `make test` and `python3 tools/doctor.py`.
6. Rebuild and restart the API, the worker and the web app.
7. Check the audit chain on the Audit log page.

The `packages/` folder is a copy of the shared base and is never edited here. Roll back by restoring the database backup and checking out the previous version.

## Pinned packages

`constraints.txt` pins every third party Python package to the version the tests ran against, so an install today gives the same set as the one that was tested (`make install`, the Docker image and CI all use it). After a deliberate upgrade of a package, install the new version, run the tests, then rewrite the file with `tools/make_constraints.py` from the hub repository (`sendora-ai-systems`).
