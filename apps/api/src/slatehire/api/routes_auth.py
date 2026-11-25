from __future__ import annotations

import hmac
import json

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from slatehire.api.deps import get_ctx, user
from slatehire.context import Ctx
from sendora_core.auth import clean_email, make_session_token, verify_password_or_dummy
from sendora_core.ratelimit import RateLimitExceeded

router = APIRouter(prefix="/api/auth", tags=["auth"])
DEMO_PASSWORD = "demo-password-1"  # only accepted when settings.demo_shortcuts is true: DEMO_MODE on AND no OWNER_PASSWORD_HASH set
DEMO_APPROVERS = ("approver@example.test", "iris.wells@example.test", "jonas.okafor@example.test")


class Login(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(max_length=1024)


def _members(raw: str) -> list[tuple[str, str, str]]:
    """The extra sign ins from MEMBERS_JSON as (email, password hash, role). A second owner can never be added this way."""
    out: list[tuple[str, str, str]] = []
    try:
        for m in json.loads(raw):
            if m.get("role") in ("approver", "viewer") and m.get("email") and m.get("password_hash"):
                out.append((clean_email(m["email"]), m["password_hash"], m["role"]))
    except (ValueError, TypeError, AttributeError):
        pass
    return out


def _accounts(ctx: Ctx) -> dict[str, tuple[str | None, str]]:
    """Who may sign in. The made up approver, interviewer and viewer accounts exist only while demo shortcuts are on, never next to a real owner password.
    An account with no password hash can sign in only with the public demo password, so it exists only in that case."""
    s = ctx.settings
    out: dict[str, tuple[str | None, str]] = {clean_email(s.owner_email): (s.owner_password_hash, "owner")}
    if s.approver_email:
        out[clean_email(s.approver_email)] = (s.approver_password_hash, "approver")
    if s.viewer_email:
        out[clean_email(s.viewer_email)] = (s.viewer_password_hash, "viewer")
    for email, pw_hash, role in _members(s.members_json):
        out.setdefault(email, (pw_hash, role))
    if s.demo_shortcuts:
        for e in DEMO_APPROVERS:
            out.setdefault(e, (None, "approver"))
        out.setdefault("viewer@example.test", (None, "viewer"))
        return out
    return {e: v for e, v in out.items() if v[0] is not None}


@router.post("/login", summary="Sign in with email and password")
def login(body: Login, request: Request, ctx: Ctx = Depends(get_ctx)):
    email = clean_email(body.email)  # one spelling, used for the throttle keys AND the lookup
    host = request.client.host if request.client else "x"
    try:
        request.app.state.login_ip_bucket.check(host)  # every try from one address, whatever email it names
        request.app.state.login_bucket.check(f"{host}:{email}")  # tries at one account from one address
        request.app.state.login_account_bucket.check(email)  # tries at one account from anywhere
    except RateLimitExceeded as exc:
        raise HTTPException(429, str(exc)) from exc
    acc = _accounts(ctx).get(email)
    pw_hash = acc[0] if acc else None
    if acc and pw_hash is None and ctx.settings.demo_shortcuts:
        ok = hmac.compare_digest(body.password.encode(), DEMO_PASSWORD.encode())
    else:
        ok = verify_password_or_dummy(body.password, pw_hash)  # an unknown account costs the same time as a wrong password
    if not acc or not ok:
        raise HTTPException(401, "Email or password is wrong.")
    token = make_session_token(ctx.settings.session_secret, email, acc[1])
    return {"token": token, "user": email, "role": acc[1]}


@router.post("/logout", summary="End the session (the web app clears the cookie)")
def logout():
    return {"ok": True}


@router.get("/me", summary="Who is signed in")
def me(u: dict = Depends(user), ctx: Ctx = Depends(get_ctx)):
    return {"user": u["user"], "role": u["role"], "demo_mode": ctx.settings.demo_shortcuts}  # the demo bar shows only while the demo routes exist
