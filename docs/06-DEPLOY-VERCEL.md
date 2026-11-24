# Deploy the web app on Vercel

Vercel hosts only the web app. The API and database must run elsewhere ([Railway](07-DEPLOY-RAILWAY.md) or [Hetzner](08-DEPLOY-HETZNER.md)). This guide was written from the vendor's docs and was not run against a real Vercel account (UNVERIFIED).

1. Put the API online first and note its public https address.
2. In Vercel choose Add New, Project, and import the repository.
3. Set **Root Directory** to `apps/web`. Turn on the option to include source files outside the root directory, because the UI kit lives in `packages/ui-kit`.
4. Framework preset: Next.js. Leave the build command as it is.
5. Open Settings, Environment Variables and add `API_BASE_URL` (the API address, https, no trailing slash) and `SESSION_SECRET` (same value as the API). Do not set `INSECURE_COOKIES`.
6. Deploy. Open the address and sign in.
7. On the API, make sure it accepts requests only from the web app's server (keep the API address private where you can).

Check: the sign in page loads and the pipeline page shows data after you sign in. If you see "The server is not reachable", `API_BASE_URL` is wrong or the API is down ([troubleshooting](15-TROUBLESHOOTING.md)).
