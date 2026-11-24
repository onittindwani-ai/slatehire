"""The only route that works without a session: a signed application webhook (an ATS or a form tool posts one applicant)."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy.orm import Session

from slatehire import intake
from slatehire.api.deps import db, get_ctx
from slatehire.context import Ctx
from slatehire.errors import RuleError
from slatehire.ingest import Applicant
from sendora_core.auth import verify_webhook_signature

router = APIRouter(tags=["public"])


class ApplicantIn(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    email: str = Field(default="", max_length=254)
    role: str = Field(max_length=40)
    resume_text: str = Field(min_length=40, max_length=60000)
    external_ref: str | None = Field(default=None, max_length=120)


@router.post("/api/webhooks/application", summary="Signed webhook: one applicant. Header x-signature is the hex HMAC SHA256 of the raw body.")
async def application_webhook(request: Request, s: Session = Depends(db), ctx: Ctx = Depends(get_ctx)):
    secret = ctx.settings.application_webhook_secret
    body = await request.body()
    if len(body) > 200_000:
        raise HTTPException(413, "Too large.")
    if not secret or not verify_webhook_signature(secret, body, request.headers.get("x-signature", "")):
        raise HTTPException(401, "The signature does not match.")
    try:
        b = ApplicantIn(**json.loads(body))
        role = intake.role_by_key(s, b.role)
    except (ValueError, ValidationError) as exc:
        raise HTTPException(400, "The body is not a valid applicant.") from exc
    except RuleError as exc:
        raise HTTPException(400, str(exc)) from exc
    app, status = intake.add_applicant(s, Applicant(b.name, b.email, "", b.role, b.resume_text, "", "webhook", external_ref=b.external_ref), role, "webhook", ctx.now(s), settings=ctx.settings)
    return {"status": status, "application_id": app.id if app else None}
