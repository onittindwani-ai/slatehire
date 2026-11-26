# Deploy the web app on Vercel

Vercel hosts only the web app. The API and database must run elsewhere ([Railway](07-DEPLOY-RAILWAY.md) or [Hetzner](08-DEPLOY-HETZNER.md)). This guide was written from the vendor's docs and was not run against a real Vercel account (UNVERIFIED).

1. Put the API online first and note its public https address.
2. In Vercel choose Add New, Project, and import the repository.
3. Set **Root Directory** to `apps/web`. Turn on the option to include source files outside the root directory, because the UI kit lives in `packages/ui-kit`.
4. Framework preset: Next.js. Leave the build command as it is.
5. Open Settings, Environment Variables and add `API_BASE_URL` (the API address, https, no trailing slash) (the web app reads no secret, so do not put `SESSION_SECRET` here: it belongs to the API). Do not set `INSECURE_COOKIES`.
6. Deploy. Open the address and sign in.
7. On the API, make sure it accepts requests only from the web app's server (keep the API address private where you can).
8. Tell the API who may say which address a visitor has. The web app on Vercel reaches your API from addresses you do not control, so keep the API private (behind the Hetzner Caddy or on a private network) and set `FORWARDED_ALLOW_IPS` on the API to the address range of whatever sits directly in front of it (the Docker image starts with `127.0.0.1` only; the Dockerfile runs uvicorn with `--proxy-headers`). If you leave this out, every visitor looks like the same address and the sign in limits are shared by everyone, so one bad try from a stranger can hold up the owner from a new browser for a while. A browser that signed in before carries a signed note and is not held up, and the settings page warns when the API sees an address it does not trust. If a CDN such as Cloudflare sits in front of your proxy, tell the proxy to trust it so the real visitor is the last address in `x-forwarded-for`.

Check: the sign in page loads and the pipeline page shows data after you sign in. If you see "The server is not reachable", `API_BASE_URL` is wrong or the API is down ([troubleshooting](15-TROUBLESHOOTING.md)).
