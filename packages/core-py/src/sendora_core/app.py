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


MAX_OPEN_STREAMS = 50  # live event streams one process serves at the same time


class BodyTooLarge(Exception):
    pass


class LimitBodySize:
    """Refuses a request body larger than `limit` bytes before the app reads it: by Content-Length when the client states one,
    and by counting bytes while they arrive when it does not (chunked). A client cannot make the process hold more than `limit`."""

    def __init__(self, app, limit: int):
        self.app, self.limit = app, limit

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        declared = next((v for k, v in scope["headers"] if k == b"content-length"), None)
        try:
            if declared is not None and int(declared) > self.limit:
                return await self._refuse(send)
        except ValueError:
            return await self._refuse(send)
        seen = 0

        async def counted():
            nonlocal seen
            message = await receive()
            if message["type"] == "http.request":
                seen += len(message.get("body", b""))
                if seen > self.limit:
                    raise BodyTooLarge()
            return message

        started = False

        async def tracked_send(message):
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, counted, tracked_send)
        except BodyTooLarge:
            if not started:
                await self._refuse(send)

    async def _refuse(self, send):
        body = b'{"error":{"code":"http_413","message":"The request is too large."}}'
        await send({"type": "http.response.start", "status": 413, "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())]})
        await send({"type": "http.response.body", "body": body})


def create_base_app(settings: BaseAppSettings, factory: sessionmaker[Session] | None = None) -> FastAPI:
    settings.check_runtime()  # refuses to start on an unsafe configuration (example session secret, a demo on a server database)
    # The interactive docs and the schema list every route, so they are on for a demo and off for a real deployment.
    app = FastAPI(title=settings.app_name, docs_url="/docs" if settings.demo_mode else None, openapi_url="/openapi.json" if settings.demo_mode else None, redoc_url=None)
    app.add_middleware(LimitBodySize, limit=settings.max_body_bytes)
    app.state.open_streams = 0
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
        if app.state.open_streams >= MAX_OPEN_STREAMS:
            raise HTTPException(429, "Too many live streams are open. Close another tab and try again.")

        async def counted():
            app.state.open_streams += 1
            try:
                async for frame in event_stream(factory, after, prefix, is_disconnected=request.is_disconnected, max_idle_polls=None):
                    yield frame
            finally:
                app.state.open_streams -= 1

        return StreamingResponse(counted(), media_type="text/event-stream", headers={"cache-control": "no-cache", "x-accel-buffering": "no"})

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
