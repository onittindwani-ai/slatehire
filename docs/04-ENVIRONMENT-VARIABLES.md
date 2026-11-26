# Environment variables

Every variable Slatehire reads, in plain words. Copy `.env.example` to `.env` and fill in only what you use. `python3 tools/check_env.py` (or `make check-env`) compares your file with the example and prints names only. `tools/doctor.py` tests each connection and never prints a secret. Vendor steps were read from the vendors' public docs on 2026-11-23 and are marked VERIFIED only when the page said so. Anything not run against the real vendor is UNVERIFIED. No prices are quoted: read each vendor's price page.

## Core

### `SESSION_SECRET`
- **Required:** Yes (always)
- **What it does:** Signs the session cookie. Anyone who knows it can sign in as anyone. It must be 32 or more characters. Outside demo mode the API and the worker refuse to start on the example value from `.env.example` or on a short one.
- **How to get it:**
1. Run `python3 -c "import secrets; print(secrets.token_urlsafe(48))"`.
2. Paste the result as the value. Use a different one for every install.
- **Cost:** Free.
- **Where to put it:** Local: your `.env` file. Vercel: Project, Settings, Environment Variables (web variables only). Railway: the service, Variables tab. Hetzner: the `.env` file next to `docker-compose.yml` on the server.
- **Check it:** `make check-env`
- **If it is wrong you see:** The API refuses to start outside demo mode, or `make check-env` says the placeholder is still in place.


### `SUPPRESSION_KEY`
- **Required:** Yes outside the demo (the API and the worker refuse to start without it as soon as an owner password is set or MODE is live)
- **What it does:** The key of the one way hashes that stop a deleted person being added again. It is kept only in the environment, never in the database or in a backup of it, so someone who holds a copy of the data cannot use the hashes to test whether a known address was erased. Keep the same value for as long as you keep the data: hashes made under another key match nobody. After a restore, `docker compose exec -T api python -m slatehire.reapply -` (see [operating](11-OPERATING-AND-BACKUPS.md)) needs the same key.
- **How to get it:**
1. Run `python3 -c "import secrets; print(secrets.token_urlsafe(48))"` and paste the result as the value (32 or more characters). Use a different one for every install, and keep a copy where you keep your other secrets.
- **Cost:** Free.
- **Where to put it:** Local: your `.env` file. Railway: the service, Variables tab (on both the `api` and the `worker` service). Hetzner: the `.env` file next to `docker-compose.yml` on the server.
- **Check it:** `python3 tools/doctor.py`
- **If it is wrong you see:** The API refuses to start and names `SUPPRESSION_KEY`. In the demo it may stay empty: the hashes then use a salt kept in the database, which is weaker.


### `DATABASE_URL`
- **Required:** Yes
- **What it does:** Where the data lives. `sqlite:///./slatehire.sqlite3` for one machine, `postgresql+psycopg://user:password@host:5432/dbname` for a deploy.
- **How to get it:**
1. Local: leave the default.
2. Railway: add the Postgres plugin and reference its URL variable, changing the scheme to `postgresql+psycopg://`.
3. Hetzner: the compose file builds it from `POSTGRES_PASSWORD`.
- **Cost:** SQLite is free. Postgres is free software and your host bills for the server.
- **Where to put it:** Local: your `.env` file. Vercel: Project, Settings, Environment Variables (web variables only). Railway: the service, Variables tab. Hetzner: the `.env` file next to `docker-compose.yml` on the server.
- **Check it:** `python3 tools/doctor.py` (it prints the variable name, never the value)
- **If it is wrong you see:** `FAIL database: OperationalError. Check DATABASE_URL.`


### `MODE and DEMO_MODE`
- **Required:** Yes
- **What it does:** `MODE=draft` sends nothing (no calendar invites). `live` allows a confirmed invite. `DEMO_MODE=true` loads sample data, offline adapters and the public demo sign ins (the demo password, the data reset button and the clock buttons). The moment `OWNER_PASSWORD_HASH` is set every one of those shortcuts is off, even if this stays `true`. The default in `.env.example` is `false`.
- **How to get it:**
1. Set `DEMO_MODE=true` (and leave `OWNER_PASSWORD_HASH` empty) only for the demo with sample people.
2. For a real install set `DEMO_MODE=false` first, then work through the go live checklist before `MODE=live`.
- **Cost:** Free.
- **Where to put it:** Local: your `.env` file. Vercel: Project, Settings, Environment Variables (web variables only). Railway: the service, Variables tab. Hetzner: the `.env` file next to `docker-compose.yml` on the server.
- **Check it:** `python3 tools/doctor.py` (it prints the variable name, never the value)
- **If it is wrong you see:** `MODE is live while DEMO_MODE is true` or a refusal to build a live adapter in demo mode.


### `OWNER_EMAIL, OWNER_PASSWORD_HASH`
- **Required:** Yes outside demo mode
- **What it does:** The owner sign in. The password is stored as an Argon2 hash. `OWNER_EMAIL` must be your own address: the example address is refused outside demo mode.
- **How to get it:**
1. Run `python3 tools/hash_password.py` and type a long password when asked.
2. Paste the hash as `OWNER_PASSWORD_HASH` (inside single quotes in a `.env` file) and your email as `OWNER_EMAIL`.
- **Cost:** Free.
- **Where to put it:** Local: your `.env` file. Vercel: Project, Settings, Environment Variables (web variables only). Railway: the service, Variables tab. Hetzner: the `.env` file next to `docker-compose.yml` on the server.
- **Check it:** Sign in on the login page.
- **If it is wrong you see:** `Email or password is wrong.` or `OWNER_PASSWORD_HASH is empty` from the doctor.


### `APPROVER_EMAIL, APPROVER_PASSWORD_HASH, VIEWER_EMAIL, VIEWER_PASSWORD_HASH, MEMBERS_JSON, LOGIN_BURST`
- **Required:** Yes if more than one person works in it
- **What it does:** A second person who can approve offers and send scorecards. `MEMBERS_JSON` is a list of extra approvers: `[{"email":"a@b.co","password_hash":"...","role":"approver"}]`. A second owner cannot be added. `VIEWER_EMAIL` and `VIEWER_PASSWORD_HASH` make a read only sign in (for example a hiring manager who only looks): it opens the pipeline, candidates, interviews, fairness and approvals pages (without the pay terms) and changes nothing, it cannot open the Offers page or the audit log, and it cannot show a hidden identity. In `MEMBERS_JSON` use `"role":"viewer"` for more of them. `LOGIN_BURST` (default 5) is how many sign in tries one address and email may make in a row before a short wait; the browser tests raise it, leave it at 5 in real use.
- **How to get it:**
1. Make a hash for each person with `tools/hash_password.py`.
2. Set the variables.
- **Cost:** Free.
- **Where to put it:** Local: your `.env` file. Vercel: Project, Settings, Environment Variables (web variables only). Railway: the service, Variables tab. Hetzner: the `.env` file next to `docker-compose.yml` on the server.
- **Check it:** Sign in as that person.
- **If it is wrong you see:** `Email or password is wrong.`


### `KILL_SWITCH`
- **Required:** No
- **What it does:** `true` starts the app paused: no calendar invites and no offer files. The owner can also pause from the top bar.
- **How to get it:** Set `true` or `false`.
- **Cost:** Free.
- **Where to put it:** Local `.env`, Railway Variables, Hetzner `.env`.
- **Check it:** The banner at the top of every page says paused.
- **If it is wrong you see:** An invite or offer file is refused with a message that the kill switch is on.

### `ALLOW_HTTP_LOCAL_TARGETS`
- **Required:** No (keep `false`)
- **What it does:** Lets the address guard accept plain http to local addresses. Only the offline tests need it.
- **How to get it:** Leave `false` everywhere except a test machine.
- **Cost:** Free.
- **Where to put it:** Test machine `.env` only.
- **Check it:** Open your `.env` and confirm it says `false` (or is missing).
- **If it is wrong you see:** Nothing visible, which is the risk: a true value weakens the guard against requests to private networks.

## Hiring rules (decided defaults, change them for your company)

### `RETENTION_DAYS, OPEN_RETENTION_DAYS, FAIRNESS_MIN_GROUP, FAIRNESS_THRESHOLD, MIN_SCORECARDS, BLIND_DEFAULT, REDACT_INSTITUTIONS, REDACT_EXTRA_TERMS, PROXY_TERMS`
- **Required:** No (defaults exist)
- **What it does:** Days to keep a declined or withdrawn applicant (365), days after which the personal data of an applicant nobody ever decided on is deleted (`OPEN_RETENTION_DAYS`, 730, 0 means never), the smallest group the fairness page compares (10, never below 2; a smaller group is shown as "fewer than N" with no counts), the threshold as a fraction (4/5), scorecards needed before an offer (2), whether new rubrics start blind, whether schools are hidden, extra clubs, societies or words that are hidden from the scorer and the reviewer as personal details (`REDACT_EXTRA_TERMS`, comma separated, on top of a built in list of groups, family status, leave and native language lines; best effort, see docs/14), and extra words a rubric may not look for (`PROXY_TERMS`, comma separated: words that stand in for age, school or language; a built in list is always checked too). These are the decided defaults. The implementer can change any of them for the client's company and country with the client's adviser.
- **How to get it:**
1. Decide each with your adviser.
2. Set the values. `RETENTION_DAYS` under 30 triggers a warning.
- **Cost:** Free.
- **Where to put it:** Local: your `.env` file. Vercel: Project, Settings, Environment Variables (web variables only). Railway: the service, Variables tab. Hetzner: the `.env` file next to `docker-compose.yml` on the server.
- **Check it:** `python3 tools/doctor.py` (it prints the variable name, never the value)
- **If it is wrong you see:** A problem line such as `RETENTION_DAYS is under 30.`


### `EXPORT_DIR, UPLOAD_MAX_BYTES, KEEP_ORIGINAL_MAX_BYTES, SEED_DIR, MAX_BODY_BYTES`
- **Required:** No
- **What it does:** Where offer files are written, the largest resume upload (`UPLOAD_MAX_BYTES`, 5000000 bytes), the largest PDF resume that is kept as it arrived so a person can open it (`KEEP_ORIGINAL_MAX_BYTES`, 2000000 bytes, 0 keeps none; the file is erased with the person), where the data folder with the starting rubrics lives (`SEED_DIR`, set automatically when you run from the repository and by the Docker image) and the largest request of any kind the API reads (`MAX_BODY_BYTES`, 26214400 bytes). A request larger than the limit is refused before it is read.
- **How to get it:**
1. Make sure the folder exists and the app can write to it. On Railway and Hetzner attach a volume.
- **Cost:** Free; a volume may cost on your host.
- **Where to put it:** Local: your `.env` file. Vercel: Project, Settings, Environment Variables (web variables only). Railway: the service, Variables tab. Hetzner: the `.env` file next to `docker-compose.yml` on the server.
- **Check it:** `python3 tools/doctor.py` (it prints the variable name, never the value)
- **If it is wrong you see:** `Export folder ... is not writable.`


## Applicants in

### `APPLICATION_WEBHOOK_SECRET`
- **Required:** Only for the webhook
- **What it does:** The shared secret for `/api/webhooks/application`.
- **How to get it:**
1. Generate a long random string as for `SESSION_SECRET`.
2. Put the same string in the sending tool and compute `x-signature` as the hex HMAC SHA256 of the raw body.
- **Cost:** Free.
- **Where to put it:** Local: your `.env` file. Vercel: Project, Settings, Environment Variables (web variables only). Railway: the service, Variables tab. Hetzner: the `.env` file next to `docker-compose.yml` on the server.
- **Check it:** Post a test body with the right and a wrong signature: 200 and 401.
- **If it is wrong you see:** `The signature does not match.` (401)


### `ATS_ADAPTER`
- **Required:** No
- **What it does:** `seed` (default), `ashby`, `workable` or `greenhouse`. Read only.
- **How to get it:**
1. Pick the tool your client uses and set its variables below.
- **Cost:** Free.
- **Where to put it:** Local: your `.env` file. Vercel: Project, Settings, Environment Variables (web variables only). Railway: the service, Variables tab. Hetzner: the `.env` file next to `docker-compose.yml` on the server.
- **Check it:** `python3 tools/doctor.py` (it prints the variable name, never the value)
- **If it is wrong you see:** `ATS_ADAPTER is ashby but ASHBY_API_KEY is empty.`


### `ASHBY_API_KEY, ASHBY_BASE_URL`
- **Required:** Only if you use Ashby
- **What it does:** Basic auth key (the key as user name, an empty password) with permission to read candidates (`candidatesRead`).
- **How to get it:**
1. Sign in to Ashby as an admin and create an API key with candidate read access. The Ashby docs page we read named the permission but not the menu path, so look under the admin settings for API keys.
2. Paste the key. Leave `ASHBY_BASE_URL` as the default.
- **Cost:** Included with an Ashby plan as far as we know. Read the price page.
- **Where to put it:** Local: your `.env` file. Vercel: Project, Settings, Environment Variables (web variables only). Railway: the service, Variables tab. Hetzner: the `.env` file next to `docker-compose.yml` on the server.
- **Check it:** `python3 tools/doctor.py` (it prints the variable name, never the value) with `--live`
- **If it is wrong you see:** `The service refused the key.`
- **Status:** Permission name VERIFIED (developers.ashbyhq.com/reference/candidatelist, 2026-11-23). Menu path UNVERIFIED. Never run live.

### `WORKABLE_TOKEN, WORKABLE_SUBDOMAIN, WORKABLE_BASE_URL`
- **Required:** Only if you use Workable
- **What it does:** A bearer token and your account subdomain (the base is `https://<subdomain>.workable.com/spi/v3`).
- **How to get it:**
1. In Workable open the drop down at the top right and choose Integrations.
2. Click Generate new token, pick the read scopes and copy it. It is shown once.
3. Your subdomain is on the company profile settings page.
- **Cost:** Read the price page for API access.
- **Where to put it:** Local: your `.env` file. Vercel: Project, Settings, Environment Variables (web variables only). Railway: the service, Variables tab. Hetzner: the `.env` file next to `docker-compose.yml` on the server.
- **Check it:** `python3 tools/doctor.py` (it prints the variable name, never the value) with `--live`
- **If it is wrong you see:** `The service refused the key.`
- **Status:** Steps VERIFIED (workable.readme.io, 2026-11-23). Never run live. The resume download step is UNVERIFIED.

### `GREENHOUSE_TOKEN, GREENHOUSE_BASE_URL`
- **Required:** Only if you use Greenhouse
- **What it does:** A Harvest API key (basic auth, key as user name, empty password).
- **How to get it:**
1. In Greenhouse go to Configure, then Dev Center, then API Credential Management.
2. Create a Harvest key and tick the candidate read permissions. You need the permission to manage all API credentials.
3. Paste the key.
- **Cost:** Read the price page.
- **Where to put it:** Local: your `.env` file. Vercel: Project, Settings, Environment Variables (web variables only). Railway: the service, Variables tab. Hetzner: the `.env` file next to `docker-compose.yml` on the server.
- **Check it:** `python3 tools/doctor.py` (it prints the variable name, never the value) with `--live`
- **If it is wrong you see:** `The service refused the key.`
- **Status:** Steps VERIFIED (docs.greenhouse.io/harvest.html, 2026-11-23). Harvest v1 and v2 is deprecated and will be removed on 2026-08-31. Never run live.

### `MAILBOX_ADAPTER, IMAP_HOST, IMAP_PORT, IMAP_USER, IMAP_PASSWORD, IMAP_USE_SSL, IMAP_MAX_MESSAGE_BYTES, IMAP_MAX_RUN_BYTES`
- **Required:** Only for an email inbox
- **What it does:** Reads application emails. Gmail: host `imap.gmail.com`, port 993. `IMAP_MAX_MESSAGE_BYTES` (10000000) is the largest message that is downloaded: a bigger one is never fetched, is listed under Not added with its sender and is marked read. `IMAP_MAX_RUN_BYTES` (60000000) is the most message bytes one run holds at a time; the rest waits for the next run.
- **How to get it:**
1. Turn on 2 step verification on the mailbox account.
2. Open myaccount.google.com/apppasswords and make an app password for Slatehire.
3. Use the full address as `IMAP_USER` and the app password as `IMAP_PASSWORD`.
- **Cost:** Free with a Google account.
- **Where to put it:** Local: your `.env` file. Vercel: Project, Settings, Environment Variables (web variables only). Railway: the service, Variables tab. Hetzner: the `.env` file next to `docker-compose.yml` on the server.
- **Check it:** `python3 tools/doctor.py` (it prints the variable name, never the value) with `--live`
- **If it is wrong you see:** `Could not sign in to the mailbox. Check the host, port, user and password.`
- **Status:** Gmail steps from a Gmail help page read on 2026-11-22 for another project. Run only against a local mock mail server here.

## Interview invites and offers

### `CALENDAR_ADAPTER`
- **Required:** No
- **What it does:** `seed` (default, invites stay in the app), `calcom` or `google`.
- **How to get it:**
1. Set the variables of the tool you pick.
- **Cost:** Free.
- **Where to put it:** Local: your `.env` file. Vercel: Project, Settings, Environment Variables (web variables only). Railway: the service, Variables tab. Hetzner: the `.env` file next to `docker-compose.yml` on the server.
- **Check it:** `python3 tools/doctor.py` (it prints the variable name, never the value)
- **If it is wrong you see:** `CALENDAR_ADAPTER is calcom but CALCOM_API_KEY is empty.`


### `CALCOM_API_KEY, CALCOM_EVENT_TYPE_ID, CALCOM_BASE_URL`
- **Required:** Only for Cal.com
- **What it does:** Books a slot with `POST /bookings` and the `cal-api-version` header.
- **How to get it:**
1. In Cal.com create an API key in your settings (where it lives was not confirmed from the docs).
2. Copy the numeric id of the event type you will use for interviews.
3. Paste both.
- **Cost:** Read the price page, or self host.
- **Where to put it:** Local: your `.env` file. Vercel: Project, Settings, Environment Variables (web variables only). Railway: the service, Variables tab. Hetzner: the `.env` file next to `docker-compose.yml` on the server.
- **Check it:** `python3 tools/doctor.py` (it prints the variable name, never the value) with `--live`
- **If it is wrong you see:** `Cal.com refused the key.`
- **Status:** Request shape VERIFIED (cal.com/docs/api-reference/v2, 2026-11-22). Dashboard path UNVERIFIED. Never run live.

### `GOOGLE_ACCESS_TOKEN, GOOGLE_CALENDAR_ID, GOOGLE_BASE_URL`
- **Required:** Only for Google Calendar
- **What it does:** Creates events with `events.insert`. The adapter takes an access token you already have; it does not run the sign in flow.
- **How to get it:**
1. Create an OAuth client in the Google Cloud console and authorise the `calendar.events` scope for the calendar owner.
2. Paste a current access token. Tokens expire, so this suits a test, not a long running install.
- **Cost:** Free for personal use. Read the price page for business plans.
- **Where to put it:** Local: your `.env` file. Vercel: Project, Settings, Environment Variables (web variables only). Railway: the service, Variables tab. Hetzner: the `.env` file next to `docker-compose.yml` on the server.
- **Check it:** `python3 tools/doctor.py` (it prints the variable name, never the value) with `--live`
- **If it is wrong you see:** `Google refused the access token.`
- **Status:** Endpoint and scope VERIFIED (developers.google.com/calendar, 2026-11-22). Token flow not built. Never run live.

### `HANDOFF_ADAPTER`
- **Required:** No
- **What it does:** `package` (default) writes the approved offer to a file. `seed` keeps it in the app.
- **How to get it:**
1. Leave the default.
- **Cost:** Free.
- **Where to put it:** Local: your `.env` file. Vercel: Project, Settings, Environment Variables (web variables only). Railway: the service, Variables tab. Hetzner: the `.env` file next to `docker-compose.yml` on the server.
- **Check it:** `python3 tools/doctor.py` (it prints the variable name, never the value)
- **If it is wrong you see:** `The export folder is not writable.`


## Model, web and hosting

### `ANTHROPIC_API_KEY, LLM_BACKEND, LLM_MODE, SCORER, LLM_HARD_MODEL, LLM_BULK_MODEL, LLM_MODEL, ANTHROPIC_BASE_URL, ANTHROPIC_VERSION`
- **Required:** No
- **What it does:** Not needed for the demo or for scoring by the built in rules. `LLM_BACKEND` is `offline` (default, the built in rules stand in, no account), `fixture` (recorded answers from `LLM_FIXTURES_DIR`) or `anthropic` (a real model, needs the key, UNVERIFIED live: it has only been run against a local mock server). `SCORER` is `rules` (default) or `model`: with `SCORER=model` and a model backend, each criterion is scored by the model one at a time, from the redacted resume only, and the code checks every quote against the redacted text and adds up the total. A model never moves, rejects or messages anyone. Turning it on is a choice to make with your lawyer's advice, see doc 14.
- **How to get it:**
1. Leave both empty for the demo.
2. To try the model path with no account, set `LLM_BACKEND=fixture`, `LLM_FIXTURES_DIR=data/llm_fixtures` and `SCORER=model` (recorded answers for the first 8 demo applications, made from a local mock server, not from a real model).
3. For a real model: in the Anthropic Console, API keys, create a key, and set `ANTHROPIC_API_KEY`, `LLM_BACKEND=anthropic` and `SCORER=model`. Set `LLM_CALL_BUDGET` and `LLM_BUDGET_USD` first so a mistake cannot run up a bill.
- **Cost:** Free when empty. A real model costs per call, one call per criterion per resume (a role with 5 criteria and 100 resumes is 500 calls).
- **Where to put it:** Local: your `.env` file. Vercel: Project, Settings, Environment Variables (web variables only). Railway: the service, Variables tab. Hetzner: the `.env` file next to `docker-compose.yml` on the server.
- **Check it:** `python3 tools/doctor.py` (it prints the variable name, never the value)
- **If it is wrong you see:** `The model backend is anthropic but ANTHROPIC_API_KEY is empty.` or `SCORER is model but LLM_BACKEND is offline, so the rules score.`


### `COMPANY_NAME, APP_NAME`
- **Required:** `COMPANY_NAME` is required for a live start
- **What it does:** `COMPANY_NAME` is the company every offer file and job post speaks for. `APP_NAME` is the name in logs. The example `Example Company` is a placeholder: `python3 tools/doctor.py` lists it as a PROBLEM and a live start (`MODE=live`, `DEMO_MODE=false`) is refused while it, or the example `OWNER_EMAIL`, is unchanged.
- **How to get it:**
1. Set `COMPANY_NAME` to your own company name.
2. Leave `APP_NAME` as it is.
- **Cost:** Free.
- **Where to put it:** Local: your `.env` file. Vercel: Project, Settings, Environment Variables (web variables only). Railway: the service, Variables tab. Hetzner: the `.env` file next to `docker-compose.yml` on the server.
- **Check it:** `python3 tools/doctor.py` (it prints the variable name, never the value)
- **If it is wrong you see:** An offer file would name the wrong company. The doctor names the placeholder.


### `ALLOW_DEMO_SERVER`
- **Required:** No (keep `false`)
- **What it does:** Lets a throw away demo run on a server database. Leave it `false`: a demo on a real database would load sample people into it, with public demo passwords.
- **How to get it:**
1. Leave `false`.
- **Cost:** Free.
- **Where to put it:** Local: your `.env` file. Vercel: Project, Settings, Environment Variables (web variables only). Railway: the service, Variables tab. Hetzner: the `.env` file next to `docker-compose.yml` on the server.
- **Check it:** `python3 tools/doctor.py` (it prints the variable name, never the value)
- **If it is wrong you see:** With `DEMO_MODE=true` on Postgres and this `false` the API refuses to start and says why.


### `LLM_TIMEOUT, LLM_MAX_TOKENS, LLM_MAX_RETRIES, LLM_CALL_BUDGET, LLM_BUDGET_USD, LLM_THINKING, LLM_FIXTURES_DIR, LLM_RECORD, LLM_REDACT, LLM_LOG_PROMPTS`
- **Required:** No
- **What it does:** Used only when `LLM_BACKEND` is `anthropic` or `fixture`. `LLM_TIMEOUT` is seconds to wait for one answer, `LLM_MAX_TOKENS` the longest answer, `LLM_MAX_RETRIES` how often a failed call is tried again. `LLM_CALL_BUDGET` is the most live model calls one process makes and `LLM_BUDGET_USD` the most tracked spend; leave them empty for no limit. `LLM_THINKING=off` asks for the lowest thinking setting where the model allows it. `LLM_FIXTURES_DIR` is where recorded answers are read, `LLM_RECORD` saves every live answer there. `LLM_REDACT` (default `true`) keeps full prompts and keys out of logs and saved answers; `LLM_LOG_PROMPTS` (default `false`) logs a shortened, redacted prompt.
- **How to get it:**
1. Keep the defaults.
2. Set both budgets before you turn a real model on.
- **Cost:** Only calls to a real model cost anything.
- **Where to put it:** Local: your `.env` file. Vercel: Project, Settings, Environment Variables (web variables only). Railway: the service, Variables tab. Hetzner: the `.env` file next to `docker-compose.yml` on the server.
- **Check it:** `python3 tools/doctor.py` (it prints the variable name, never the value)
- **If it is wrong you see:** At the limit the app falls back to the built in rules. Turning `LLM_REDACT` off would put candidate text in logs.


### `API_BASE_URL, INSECURE_COOKIES`
- **Required:** Yes on the web host
- **What it does:** `API_BASE_URL` is the private address of the API the web app forwards to. `INSECURE_COOKIES=1` is only for plain http on localhost. In the compose file the web container receives only these two, not the rest of `.env`.
- **How to get it:**
1. Local: `http://127.0.0.1:8000`.
2. Vercel: the public https address of your Railway or Hetzner API.
3. Never set `INSECURE_COOKIES` in production.
- **Cost:** Free.
- **Where to put it:** Vercel: Project, Settings, Environment Variables. Railway or Hetzner: the web service variables.
- **Check it:** Open the sign in page and sign in.
- **If it is wrong you see:** `The server is not reachable. Check that the API is running.`


### `FORWARDED_ALLOW_IPS` (a setting of the API server, not of the app)
- **Required:** Yes on every hosted setup (Vercel with Railway, Railway, Hetzner)
- **What it does:** Which addresses may tell the API who the visitor is. The image trusts only `127.0.0.1`. If the web app reaches the API from an address that is not listed, every visitor looks like one address and the sign in limits are shared by everyone. The compose file sets it for Hetzner. On Railway and when the API sits behind another proxy set it to the address range of whatever sits directly in front of the API.
- **How to get it:** [Vercel](06-DEPLOY-VERCEL.md), [Railway](07-DEPLOY-RAILWAY.md) and [Hetzner](08-DEPLOY-HETZNER.md) say what to put.
- **Cost:** Free.
- **Where to put it:** The environment of the API service (not `.env` of the web app).
- **Check it:** The settings page of the app shows a warning while the API sees a visitor address it does not trust.
- **If it is wrong you see:** That warning, and sign in limits that hold up the owner when a stranger fails on purpose at the owner's account from a new browser.


### `POSTGRES_PASSWORD`
- **Required:** Yes with Docker Compose
- **What it does:** The password of the Postgres container in `docker-compose.yml`. The app itself does not read it: compose puts it into `DATABASE_URL`.
- **How to get it:**
1. Run `openssl rand -hex 24` and paste the result. Letters and digits only, so it is safe inside a URL.
2. Set it in `.env` next to the compose file.
- **Cost:** Free.
- **Where to put it:** Local: your `.env` file. Vercel: Project, Settings, Environment Variables (web variables only). Railway: the service, Variables tab. Hetzner: the `.env` file next to `docker-compose.yml` on the server.
- **Check it:** `docker compose up` starts the database.
- **If it is wrong you see:** The API cannot connect to the database.
