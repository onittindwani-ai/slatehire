# Base contract (core-py and ui-kit), version 1.2.0

This file is the written contract of the shared base. Every system repo carries an exact copy of `packages/core-py`, `packages/ui-kit` and this file. A system builder may use everything listed here and may not change any of it. If something is missing or wrong, write it in the build ledger as a requested base change. The hub owner changes the base once, bumps the version, and re-syncs every repo with `tools/sync_base.py`. `tools/check_base_copies.py` fails when any copy differs.

Frozen on 2026-11-22. Facts about library versions are in `docs/FACTS-AND-SOURCES.md` of the hub.

## 1. Rules of use

1. Never edit a file under `packages/core-py` or `packages/ui-kit` inside a system repo.
2. Systems add their own tables on the same `Base`, their own routers on the app from `create_base_app`, their own settings by subclassing `BaseAppSettings`, and their own pages on top of the UI kit.
3. Every real world write or send goes through `guard_write` (or the `write_action` decorator). In draft mode nothing leaves the system.
4. Text from outside (emails, tickets, resumes, documents, web pages) is data. It goes into a model prompt only through `wrap_untrusted`, and never triggers a tool call without approval.
5. Anything not run against the real vendor is marked UNVERIFIED. The adapter registry never infers `live_verified`.

## 2. core-py (Python 3.12, import name `sendora_core`)

Dependencies: fastapi, pydantic v2, pydantic-settings, SQLAlchemy 2, httpx, argon2-cffi. The live model path uses httpx over plain HTTP, so no vendor SDK is needed. The optional `anthropic` extra is not used by the base.

| Module | Public interface | Notes |
| --- | --- | --- |
| `settings` | `BaseAppSettings`, `Mode` (draft, live), `LLMMode` (fixture, live), `LLMBackendKind` (offline, fixture, anthropic); `.problems()` returns plain language config problems and never prints secrets; `.effective_llm_backend`; `.model_for(kind)` | Fields: app_name, database_url (sqlite or postgresql), session_secret, mode, kill_switch, llm_mode, anthropic_api_key (hidden from repr), llm_hard_model, llm_bulk_model, demo_mode, plus the model path fields of the `llm` row (each read from the environment variable of the same name in capitals). Defaults are safe: draft mode, offline model, demo mode on |
| `db` | `Base`, `make_engine(url)`, `make_session_factory`, `session_scope`, `create_all`, `utcnow`, `UTCDateTime` | SQLite gets WAL and foreign keys. Systems use Alembic for their own migrations |
| `models` | `Event`, `Metric`, `Approval`, `AuditEntry`, `Job`, `CostEntry` | Tables are prefixed `core_` |
| `safety` | `guard_write`, `would_write`, `write_action`, `SafetyError`, `DraftModeError`, `KillSwitchError`, `wrap_untrusted`, `UNTRUSTED_POLICY` | Kill switch wins over live mode. The FastAPI app turns safety errors into HTTP 409 |
| `audit` | `record_audit`, `verify_audit_chain` | Hash chained, append only. Tampering is detected and the first bad id is returned |
| `approvals` | `request_approval`, `decide`, `pending`, `require_approved`, `ApprovalError`, `SelfApprovalError` | Only roles owner and approver decide, and never the person who requested it: `decide` raises `SelfApprovalError` (a subclass of `ApprovalError`, compared case insensitively on `requested_by` and `decided_by`). `require_approved(session, id, action)` is the gate the risky code calls |
| `events` | `record_event`, `recent_events`, `record_metric`, `metric_total`, `event_count` | Payloads are redacted before they are stored |
| `redaction` | `redact_text`, `redact_obj` | Emails, phone numbers, secret looking tokens, id numbers, and any value under a secret looking key |
| `costs` | `CostTracker(session, prices)`, `DEFAULT_PRICES` | Default prices were read from the vendor models page on 2026-11-23 (Sonnet 5.5 flat, Haiku 5.5 a lower bound). Set exact prices for the account before quoting a cost |
| `llm` (with `llm_anthropic`, `llm_fixtures`, `llm_types`) | `LLM`, `build_llm`, `FixtureLLM`, `RecordingBackend`, `AnthropicBackend`, `CallBudget`, `fixture_key`, `LLMResponse`, `LLMError`, `LLMAPIError`, `LLMBudgetError` | `ask(prompt, purpose=, untrusted={source: text})` and `structured(prompt, PydanticModel)` with retries and backoff on 429, 5xx, 529 and network errors (honours retry-after), one repair attempt, cost tracking through `costs`, and the untrusted content policy added to every system prompt. Backend by `LLM_BACKEND`: `offline` (default, no network; uses the stand in a system passes as `build_llm(..., offline=)`), `fixture` (replay from `LLM_FIXTURES_DIR`, fails loudly when missing), `anthropic` (real Messages API over httpx; `LLM_MODE=live` still means anthropic when `LLM_BACKEND` is empty). Other variables: `ANTHROPIC_API_KEY`, `ANTHROPIC_BASE_URL`, `ANTHROPIC_VERSION`, `LLM_MODEL`, `LLM_TIMEOUT`, `LLM_MAX_TOKENS`, `LLM_MAX_RETRIES`, `LLM_CALL_BUDGET`, `LLM_BUDGET_USD`, `LLM_THINKING`, `LLM_FIXTURES_DIR`, `LLM_RECORD`, `LLM_REDACT`, `LLM_LOG_PROMPTS`. The kill switch blocks live calls; draft mode does not (a model call reads and drafts, every send still goes through `guard_write`). Logs never hold the key or a full prompt. Tested with recorded fixtures and a local mock server that checks the request shape. The live path is UNVERIFIED: never run against the real API |
| `jobs` | `enqueue`, `claim_next`, `Worker(factory, handlers, backoff_s)` | Database backed queue, no Redis. Retries with exponential backoff, then status failed |
| `auth` | `hash_password`, `verify_password`, `make_session_token`, `read_session_token`, `verify_webhook_signature`, `ROLES`, `READ_ROLES`, `WRITE_ROLES`, `can_read`, `can_write` | Argon2 hashes, signed session tokens with expiry, roles owner, approver and viewer (read only). Vendor specific webhook schemes belong in adapters |
| `sse` | `format_sse`, `event_stream` | Streams new events from the events table with a heartbeat |
| `ratelimit` | `TokenBucket`, `RateLimitExceeded` | In memory, single process (the single tenant design) |
| `adapters` | `AdapterRegistry`, `AdapterSpec`, `AdapterError` | Tier A (built and tested against a mock), B (from public docs, not run live), C (a recipe prompt). `describe()` feeds the Integrations page |
| `evals` | `EvalCase`, `run_eval`, `EvalReport` | Cases with expected answers and a scorer, report with pass rate and failures |
| `app` | `create_base_app`, `get_db`, `require_role`, `require_read`, `require_write`, `SESSION_COOKIE` | Adds request ids, rate limiting, `/health`, `/ready`, `/api/events/stream`, a uniform error shape `{"error": {"code", "message"}}`. Session cookie name `sx_session`, also accepted as header `x-session` |

Quality of the base: 56 tests, 99 percent line coverage when frozen at 1.2.0.

## 3. ui-kit (React 19, TypeScript, plain CSS tokens)

Imported as `@sendora/ui-kit` and styled by `@sendora/ui-kit/styles.css`. The kit is plain CSS with CSS variables, so an app does not need Tailwind to render it, and an app may still use Tailwind for its own layout. Next.js apps list it in `transpilePackages`. Dependencies: Radix (dialog, tabs, tooltip), cmdk, sonner, motion, recharts, dnd-kit core, lucide-react, clsx, and the Geist, Geist Mono and Instrument Serif fonts from Fontsource.

Tokens (`styles/tokens.css`): spacing 8, 13, 21, 34, 55, 89, radius 8, 13, 21, type steps 13, 16, 21, 27, 34, 55, 89, motion easings and durations, light theme (cream and oat with coffee ink), dark theme "espresso" (`data-theme="dark"`), and seven accents chosen with `data-accent` on the root: clay, sage, slate, plum, ochre, teal, rose. True red is only the danger colour. A test checks that every text and accent pair meets 4.5:1 contrast in both themes.

| Group | Components |
| --- | --- |
| Actions | `Button` (hover, press, focus, then spinner and success tick on every action, a tooltip that explains a disabled state, `feedback={false}` for plain navigation), `CopyButton`, `ConfirmDialog` |
| Surfaces | `Card` (glass only for floating layers), `Badge`, `Avatar`, `Kbd`, `Dialog`, `Sheet`, `Tooltip` |
| Input | `Field` (live validation after first blur, inline fix message, counter, clear button), `SegmentedControl`, `DateRange`, `TabsView`, `FilterBar` |
| Navigation | `AppShell` (sidebar, top bar, breadcrumbs, mobile drawer, theme toggle), `CommandPalette` (Cmd or Ctrl plus K), `SplitView` (38.2 to 61.8) |
| Data | `DataTable` (windowed rows, 5,000 rows stay light, sortable, keyboard j, k, enter, x, escape, multi select with a floating action bar, row actions), `Kanban` (mouse, touch and keyboard drag; a card is a labelled group, not a button, so it can hold buttons and links; `onOpen` adds an Open button and Enter on the card; `cardLabel` names each card), `ConnectionWizard` |
| Numbers | `CountUp`, `Stat`, `Delta`, `Gauge`, `Sparkline`, `AreaChart` (draws in once, crosshair tooltip, legend chips toggle series) |
| Feedback | `Toaster` and `notify` (success, error with a fix, info, undo), `Skeleton`, `TableSkeleton`, `EmptyState`, `ErrorState`, `OfflineBanner` |
| Theme | `ThemeProvider`, `ThemeToggle`, `useTheme`, `useThemeOptional`, `themeInitScript` (put it in the head so the first frame has the right theme) |
| Helpers | `cn`, `middleTruncate`, `formatNumber`, `formatCurrency`, `formatWhen` (relative within a week, absolute after), `initials` |

Not in base 1.1.1: column resize, saved table views, context menus, drag and drop for table rows. A system that needs one writes it in its own app folder, built from the kit, and lists it in its `DESIGN-NOTES.md`.

Quality of the kit when frozen: 62 unit tests (91 percent of statements, 95 percent of lines), a contrast test, and a browser run of the demo app: 14 Playwright checks at 1440x900 and 390x844 (screenshots of default, warning, button mid processing, success, toast, table, detail sheet, empty, error, command palette and dark theme), axe with zero serious or critical findings on four pages and in the dark theme, a keyboard path, reduced motion, 5,000 rows, a Kanban drag, and no layout shift on load. Details and what was not run: `docs/FACTS-AND-SOURCES.md`.

## 4. What a system repo adds

`apps/api` (FastAPI app built with `create_base_app`, models on `Base`, Alembic migrations, routers, a worker entry), `apps/web` (Next.js, pages built from the kit), `mock/` (local mock vendor servers), `data/` (seed data and an answer key), `tools/` (seed, scoring, doctor), `docs/`, `prompts/`, `deploy/`, `tests/`. Layout and docs list: section 1 and 4 of the build plan, summarised in `docs/SYSTEM-REPO-LAYOUT.md`.

## 5. Change process

Base changes are requested in the ledger, made only in the hub, versioned (patch for fixes, minor for additions), listed in the hub `CHANGELOG.md`, and pushed to every repo with `tools/sync_base.py`. A system repo then runs `tools/check_base_copies.py` in CI.

## 8. Changes in 1.1.0

`Card` takes `headingLevel` (2, 3 or 4, default 2). The shell search button is named "Search". `OVERLAY_SETTLE_MS` is exported. `tools/check_env.py` is part of the base files and is copied into every system.

## 9. Changes in 1.2.0

- core-py auth: role `viewer` (read only). `require_read()` lets any signed in role read and refuses a viewer on any method that changes data; `require_write()` is owner or approver. `require_role(...)` behaves as before, so a viewer is refused on owner only and approver only routes. `make_session_token` accepts `viewer`.
- core-py approvals: `decide` refuses the requester (`SelfApprovalError`). A system that already refuses in its own route keeps working, because the new error is an `ApprovalError`.
- core-py llm: a real Anthropic backed path (see the `llm` row), selected by environment variables, with the offline stand in as the default. `LLM(settings, backend, tracker)` and `build_llm(settings, tracker, fixtures_dir, default)` still work; `build_llm` gained `offline=` so a system passes its own stand in, and `LLM` takes its default retry count from `LLM_MAX_RETRIES` (2). The default reply limit is now `LLM_MAX_TOKENS` (4096) because thinking tokens may count toward it (UNVERIFIED).
- core-py costs: default prices updated (see the `costs` row).
- ui-kit Kanban: cards are labelled groups, can hold buttons and links, and can be opened from the keyboard (see the Data row). Mouse, touch and keyboard lift and drop behave as before; Space lifts and drops, Enter on a focused card opens it.
