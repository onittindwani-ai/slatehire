# Deploy everything on a Hetzner server

One small Linux server runs Postgres, the API, the worker and the web app with Docker Compose and Caddy for HTTPS. Written from the vendors' docs. **Not tested on a real server: no Hetzner server was created for this project.** The repository's CI workflow builds the Docker images and starts the stack on a throwaway GitHub machine, which shows they build and start, not that your server, DNS names or certificates work.

1. In the Hetzner console create a server (Ubuntu) and attach your SSH key. Read the price page for the size you pick.
2. Point two DNS names (for example `app.yourdomain` and `api.yourdomain`) at the server.
3. Optionally paste `deploy/hetzner/cloud-init.yaml` as user data when creating the server. It installs Docker, Caddy and a firewall that allows only ports 22, 80 and 443. It holds no secrets.
4. Copy the repository to the server and make `.env` from `.env.example`. Set exactly these (the rest is explained in [the variables guide](04-ENVIRONMENT-VARIABLES.md)): `DEMO_MODE=false` (it already is in the example); `SESSION_SECRET`, 32 or more random characters (`python3 -c "import secrets; print(secrets.token_urlsafe(48))"`, the app refuses the placeholder); `OWNER_EMAIL` and `OWNER_PASSWORD_HASH` (from `python3 tools/hash_password.py`, inside single quotes); `APPROVER_EMAIL` and `APPROVER_PASSWORD_HASH` (a second person, because the one who writes an offer cannot approve it); `SUPPRESSION_KEY` (32 or more random characters, the same command as `SESSION_SECRET`; keep it as long as you keep the data); `POSTGRES_PASSWORD` (`openssl rand -hex 24`); `COMPANY_NAME`. `chmod 600 .env`.
5. Edit `deploy/hetzner/Caddyfile` and replace the two example names with yours, then install it as the Caddy config and reload Caddy.
6. Start: `docker compose up -d --build`.
7. The tables are made for you: the API runs the migrations itself when it starts. Check with `docker compose logs api`.
8. Check the firewall (`ufw status`) shows only ports 22, 80 and 443 (the cloud-init file sets this; set it yourself if you skipped it). The compose file binds the API and the web app to 127.0.0.1 only, so only Caddy is public.
9. Schedule `deploy/hetzner/backup.sh` with cron and test a restore ([operating](11-OPERATING-AND-BACKUPS.md)).

Check: `https://api.yourdomain/health` answers, and you can sign in on the app address.

## What the API host serves

The Caddyfile publishes the API host for two paths only: `/api/webhooks/application` (so your ATS or form tool can post a signed application) and `/health` (for an uptime check). Every other address on that host answers 404. The sign in and every other API call go through the app host, whose web server passes them on over the private compose network and hands the API the visitor's real address. Compose sets `FORWARDED_ALLOW_IPS` to the private network ranges so the API trusts that address only from the web container. The web container receives only `API_BASE_URL` and `INSECURE_COOKIES`, not the rest of `.env`.

## Backups

`deploy/hetzner/backup.sh` writes a compressed Postgres dump and a copy of the exports folder (offer files) to `/var/backups/slatehire` and keeps the newest 14 of each. It writes to a partial file first and stops with an error when the dump is empty, so a failed run never pushes a good backup out of the rotation. The files are readable by the owner only and hold candidate data: encrypt them before they leave the machine. Run it nightly with cron, from any folder: `0 3 * * * /opt/slatehire/deploy/hetzner/backup.sh`. A copy on the same disk is not a backup: set `BACKUP_COPY_TO` to a folder on another machine, used only for these backups, and the script mirrors there with `rsync --delete`, so a backup that rotates out here is removed there too (a person who asked to be deleted does not stay in an old copy for ever). Each run also saves the list of people erased so far (one way hashes only). To restore, run `sh deploy/hetzner/restore.sh <dump> [exports tar]`: it replaces the database and then erases again everyone who asked after that backup was made. Test a restore ([operating](11-OPERATING-AND-BACKUPS.md)) before you need it.
