"""FastAPI base app: request ids, health and ready, uniform error shape, auth dependency, SSE route."""

from __future__ import annotations

import uuid
from collections.abc import Callable

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from sendora_core.auth import WRITE_ROLES, can_write, read_session_token
from sendora_core.db import make_engine, make_session_factory
from sendora_core.ratelimit import RateLimitExceeded, TokenBucket
from sendora_core.safety import SafetyError
from sendora_core.settings import BaseAppSettings
from sendora_core.sse import event_stream

SESSION_COOKIE = "sx_session"


def create_base_app(settings: BaseAppSettings, factory: sessionmaker[Session] | None = None) -> FastAPI:
    app = FastAPI(title=settings.app_name, docs_url="/docs", openapi_url="/openapi.json")
    if factory is None:
        factory = make_session_factory(make_engine(settings.database_url))
    app.state.settings, app.state.factory = settings, factory
    app.state.limiter = TokenBucket(capacity=120, refill_per_sec=2.0)

    @app.middleware("http")
    async def request_id(request: Request, call_next):
        rid = request.headers.get("x-request-id") or uuid.uuid4().hex[:16]
        request.state.request_id = rid
        try:
            app.state.limiter.check(request.client.host if request.client else "local")
        except RateLimitExceeded as exc:
            return JSONResponse({"error": {"code": "rate_limited", "message": str(exc)}}, 429, {"retry-after": str(int(exc.retry_after) + 1), "x-request-id": rid})
        response = await call_next(request)
        response.headers["x-request-id"] = rid
        return response

    @app.exception_handler(SafetyError)
    async def safety_handler(_: Request, exc: SafetyError):
        return JSONResponse({"error": {"code": type(exc).__name__, "message": str(exc)}}, 409)

    @app.exception_handler(HTTPException)
    async def http_handler(_: Request, exc: HTTPException):
        return JSONResponse({"error": {"code": f"http_{exc.status_code}", "message": str(exc.detail)}}, exc.status_code)

    @app.get("/health")
    def health():
        return {"status": "ok", "app": settings.app_name, "mode": settings.mode.value, "kill_switch": settings.kill_switch}

    @app.get("/ready")
    def ready():
        try:
            with factory() as s:
                s.execute(text("SELECT 1"))
        except Exception as exc:
            return JSONResponse({"status": "not_ready", "reason": type(exc).__name__}, 503)
        return {"status": "ready"}

    @app.get("/api/events/stream")
    async def stream(request: Request, after: int = 0, prefix: str | None = None):
        gen = event_stream(factory, after, prefix, is_disconnected=lambda: False, max_idle_polls=None)
        return StreamingResponse(gen, media_type="text/event-stream", headers={"cache-control": "no-cache", "x-accel-buffering": "no"})

    return app


def get_session_factory(request: Request) -> sessionmaker[Session]:
    return request.app.state.factory


def get_db(request: Request):
    factory = request.app.state.factory
    s = factory()
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()


def require_role(*roles: str) -> Callable:
    def dep(request: Request) -> dict:
        settings: BaseAppSettings = request.app.state.settings
        token = request.cookies.get(SESSION_COOKIE) or request.headers.get("x-session")
        data = read_session_token(settings.session_secret, token) if token else None
        if data is None:
            raise HTTPException(401, "Sign in to continue.")
        if roles and data["role"] not in roles:
            raise HTTPException(403, f"This needs the role: {' or '.join(roles)}.")
        return data

    return dep


SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


def require_read() -> Callable:
    """Any signed in role may read (owner, approver, viewer). A viewer is refused on any method that changes data,
    so a route author who uses this on a POST still cannot let a read only person write."""
    inner = require_role()

    def dep(request: Request) -> dict:
        data = inner(request)
        if request.method not in SAFE_METHODS and not can_write(data["role"]):
            raise HTTPException(403, "This role is read only. Ask an owner or an approver to make this change.")
        return data

    return dep


def require_write() -> Callable:
    """Owner or approver only. A viewer gets 403."""
    return require_role(*WRITE_ROLES)


__all__ = ["create_base_app", "get_db", "require_role", "require_read", "require_write", "Depends", "SESSION_COOKIE"]
