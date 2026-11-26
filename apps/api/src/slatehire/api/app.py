"""The Slatehire API. Every route under /api needs a signed in session, except sign in, the tracked link redirect and the signed lead webhook."""

from __future__ import annotations

import logging
import os

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from slatehire import guards
from slatehire.api import routes_admin, routes_auth, routes_demo, routes_public, routes_read, routes_write
from slatehire.config import Settings
from slatehire.context import Ctx
from slatehire.datadir import REPO_DATA, MARKER
from slatehire.dbsetup import make_private_engine
from slatehire.loginguard import LoginGuard
from slatehire.dbupgrade import add_missing_columns
from sendora_core.app import SESSION_COOKIE, create_base_app
from sendora_core.auth import read_session_token
from sendora_core.db import Base, make_session_factory
from sendora_core.ratelimit import TokenBucket

log = logging.getLogger("slatehire.app")


class QueryStringFilter(logging.Filter):
    """uvicorn's access log line holds the address of each request. The upload form of older callers carried the applicant's name and email in the query string, so the log keeps the path only."""

    def filter(self, record: logging.LogRecord) -> bool:
        args = record.args
        if isinstance(args, tuple) and len(args) >= 3 and isinstance(args[2], str) and "?" in args[2]:
            record.args = (*args[:2], args[2].split("?", 1)[0], *args[3:])
        return True


def _quiet_access_log() -> None:
    logger = logging.getLogger("uvicorn.access")
    if not any(isinstance(f, QueryStringFilter) for f in logger.filters):
        logger.addFilter(QueryStringFilter())


CSP_FREE = ("/docs", "/redoc", "/openapi.json")  # the interactive docs page loads its own scripts

PUBLIC = {"/api/auth/login", "/api/auth/logout", "/api/webhooks/application"}
PUBLIC_PREFIX: tuple[str, ...] = ()


def _seed_if_empty(ctx: Ctx) -> None:
    from sqlalchemy import select

    from slatehire import demo
    from slatehire.models import Role

    with ctx.factory() as s:
        if s.scalars(select(Role).limit(1)).first() is None:
            try:
                demo.reset(s, ctx)
            except FileNotFoundError as exc:  # an installed copy with no data folder still starts, with an empty demo
                log.warning("%s The demo starts empty.", exc)


def create_app(settings: Settings | None = None, ctx: Ctx | None = None) -> FastAPI:
    guards.install()  # the locked rubric and append only rules are switched on in this process, whoever imported what first
    settings = settings or Settings()
    if ctx is None:
        engine = make_private_engine(settings.database_url)
        from sendora_core import models as _c  # noqa: F401
        import slatehire.models  # noqa: F401

        if settings.database_url.startswith("sqlite"):
            Base.metadata.create_all(engine)  # SQLite zero setup path. Postgres uses `alembic upgrade head`.
            add_missing_columns(engine)  # a database file from an older version gets the columns added since
        ctx = Ctx(settings, make_session_factory(engine))
        if not settings.seed_dir and (REPO_DATA / MARKER).is_file():
            ctx.settings.seed_dir = str(REPO_DATA)  # a source checkout; an installed copy must be told with SEED_DIR
    ctx.settings.check_runtime()  # refuse an unsafe configuration before anything is written
    if ctx.settings.demo_shortcuts:
        _seed_if_empty(ctx)
    app = create_base_app(ctx.settings, ctx.factory)
    app.title, app.version = "Slatehire API", "1.0.2"
    app.state.ctx = ctx
    _quiet_access_log()
    app.state.limiter = TokenBucket(capacity=600, refill_per_sec=20.0)
    # Sign in limits: per address, per address and account, and per account (failed tries only), with a signed note for a browser that signed in before so that it is never held up by
    # strangers behind a shared address. See loginguard.py.
    app.state.login_guard = LoginGuard(ctx.settings.login_burst, watch_one_address=not ctx.settings.demo_shortcuts)

    @app.middleware("http")
    async def require_session(request: Request, call_next):
        p = request.url.path
        if p.startswith("/api/") and p not in PUBLIC and not p.startswith(PUBLIC_PREFIX):
            token = request.cookies.get(SESSION_COOKIE) or request.headers.get("x-session")
            data = read_session_token(ctx.settings.session_secret, token) if token else None
            if data is None:
                return JSONResponse({"error": {"code": "http_401", "message": "Sign in to continue."}}, 401)
            request.state.user = data
        return await call_next(request)

    @app.middleware("http")
    async def api_headers(request: Request, call_next):
        response = await call_next(request)
        if not request.url.path.startswith(CSP_FREE):  # the API answers data, never a page: nothing it sends may load or run anything
            response.headers.setdefault("content-security-policy", "default-src 'none'; frame-ancestors 'none'; base-uri 'none'")
        return response

    for r in (routes_auth, routes_read, routes_write, routes_admin, routes_public, routes_demo):
        app.include_router(r.router)
    return app


def app_from_env() -> FastAPI:  # uvicorn slatehire.api.app:app_from_env --factory
    return create_app(Settings(_env_file=os.environ.get("ENV_FILE", ".env")))
