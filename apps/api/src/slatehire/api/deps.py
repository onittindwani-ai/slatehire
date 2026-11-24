from __future__ import annotations

from collections.abc import Iterator

from fastapi import HTTPException, Request
from sqlalchemy.orm import Session

from slatehire.context import Ctx
from slatehire.errors import RuleError
from sendora_core.auth import WRITE_ROLES


def get_ctx(request: Request) -> Ctx:
    return request.app.state.ctx


def db(request: Request) -> Iterator[Session]:
    s = request.app.state.ctx.factory()
    try:
        yield s
        s.commit()
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
    if not request.app.state.ctx.settings.demo_mode:
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
