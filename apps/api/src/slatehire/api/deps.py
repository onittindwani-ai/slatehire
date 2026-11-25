from __future__ import annotations

from collections.abc import Iterator

from fastapi import HTTPException, Request
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from slatehire.context import Ctx
from slatehire.errors import RuleError
from sendora_core.auth import WRITE_ROLES


def get_ctx(request: Request) -> Ctx:
    return request.app.state.ctx


def _writes(request: Request) -> bool:
    """Does this request change anything? A change, a reveal that is written to the audit log, and the download of the original file are written for sure. A page load is not."""
    return request.method not in ("GET", "HEAD", "OPTIONS") or request.query_params.get("reveal") in ("1", "true") or request.url.path.endswith("/original")


def db(request: Request) -> Iterator[Session]:
    """One session per request. A request that writes takes the write lock when it starts (BEGIN IMMEDIATE on SQLite), so it never reads first and then finds the lock taken. A page load reads on
    its own snapshot and is never held up by a writer; the cache it may save on the way (the quote check) is skipped, not an error, when a writer has the lock."""
    ctx = request.app.state.ctx
    writes = _writes(request)
    s = (ctx.write_factory if writes else ctx.factory)()
    try:
        yield s
        try:
            s.commit()
        except OperationalError as exc:
            if writes or "locked" not in str(exc).lower():
                raise
            s.rollback()  # a page load that could not save its cache while someone else was writing
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()


def user(request: Request) -> dict:
    u = getattr(request.state, "user", None)
    if not u:
        raise HTTPException(401, "Sign in to continue.")
    return u


def writer(request: Request) -> dict:
    """Owner and approver can write and edit. A viewer reads only. Deciding an approval has its own extra rule, kept by the base."""
    u = user(request)
    if u["role"] not in WRITE_ROLES:
        raise HTTPException(403, "This sign in can read but not change things.")
    return u


def owner(request: Request) -> dict:
    u = user(request)
    if u["role"] != "owner":
        raise HTTPException(403, "Only the owner can do this.")
    return u


def demo_only(request: Request) -> None:
    """The demo routes (clock, reset, tick, stress) exist only while demo shortcuts are on: DEMO_MODE and no owner password hash."""
    if not request.app.state.ctx.settings.demo_shortcuts:
        raise HTTPException(404, "Not found.")


def rule(fn, *a, **k):
    """Turn a business rule refusal into a plain 400 and a safety stop into a 409 (the base app already maps safety errors)."""
    try:
        return fn(*a, **k)
    except RuleError as exc:
        raise HTTPException(400, str(exc)) from exc


def get_or_404(s: Session, model, ident, what: str):
    row = s.get(model, ident)
    if row is None:
        raise HTTPException(404, f"No such {what}.")
    return row
