# Deploy everything on a Hetzner server

One small Linux server runs Postgres, the API, the worker and the web app with Docker Compose and Caddy for HTTPS. Written from the vendors' docs. The compose file passed a syntax check, but Docker was never started here, so the images are UNVERIFIED.

1. In the Hetzner console create a server (Ubuntu) and attach your SSH key. Read the price page for the size you pick.
2. Point two DNS names (for example `app.yourdomain` and `api.yourdomain`) at the server.
3. Optionally paste `deploy/hetzner/cloud-init.yaml` as user data when creating the server. It installs Docker, Caddy and a firewall that allows only ports 22, 80 and 443. It holds no secrets.
4. Copy the repository to the server and make `.env` from `.env.example`. Set `POSTGRES_PASSWORD`, `SESSION_SECRET`, `DEMO_MODE=false` and the owner sign in. `chmod 600 .env`.
5. Edit `deploy/hetzner/Caddyfile` and replace the two example names with yours, then install it as the Caddy config and reload Caddy.
6. Start: `docker compose up -d --build`.
7. Run the tables: `docker compose exec api alembic upgrade head` (in `apps/api`).
8. Check the firewall (`ufw status`) shows only ports 22, 80 and 443 (the cloud-init file sets this; set it yourself if you skipped it). The compose file binds the API and the web app to 127.0.0.1 only, so only Caddy is public.
9. Schedule `deploy/hetzner/backup.sh` with cron and test a restore ([operating](11-OPERATING-AND-BACKUPS.md)).

Check: `https://api.yourdomain/health` answers, and you can sign in on the app address.
