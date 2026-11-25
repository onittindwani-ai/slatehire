from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from slatehire.api.deps import db, get_ctx, owner, writer
from slatehire.api.serializers import iso
from slatehire.context import Ctx, set_state
from slatehire.models import Application, Offer
from slatehire.registry import CATEGORIES, ENV_VARS
from sendora_core.approvals import ApprovalError, decide
from sendora_core.audit import record_audit, verify_audit_chain
from sendora_core.auth import clean_email
from sendora_core.models import Approval, AuditEntry

router = APIRouter(prefix="/api", tags=["admin"])


@router.get("/approvals", summary="Pending and recent approvals")
def approvals(s: Session = Depends(db)):
    rows = list(s.scalars(select(Approval).order_by(Approval.id.desc()).limit(100)))
    return [{"id": a.id, "action": a.action, "summary": a.summary, "risk": a.risk, "status": a.status, "requested_by": a.requested_by, "decided_by": a.decided_by, "note": a.decision_note, "created_at": iso(a.created_at), "payload": a.payload, "offer": _offer_of(s, a)} for a in rows]


def _offer_of(s: Session, a: Approval) -> dict | None:
    """What a person is being asked to approve, in words: the terms are shown next to the buttons, so nobody approves a title alone."""
    if a.action != "offer.approve":
        return None
    o = s.get(Offer, int(a.payload.get("offer_id", 0) or 0))
    if o is None:
        return None
    app = s.get(Application, o.application_id)
    return {"id": o.id, "title": o.title, "start_date": o.start_date, "terms": o.terms, "body": o.body, "created_by": o.created_by, "status": o.status, "application_id": o.application_id, "stage": app.stage if app else None}


class DecideIn(BaseModel):
    approve: bool
    note: str = Field(default="", max_length=500)


@router.post("/approvals/{approval_id}/decide", summary="Approve or reject. The person who asked cannot decide (the shared base refuses it).")
def decide_approval(approval_id: int, body: DecideIn, s: Session = Depends(db), u: dict = Depends(writer)):
    pending = s.get(Approval, approval_id)
    if pending is not None and pending.action == "offer.approve":
        o = s.get(Offer, int(pending.payload.get("offer_id", 0) or 0))
        app = s.get(Application, o.application_id) if o else None
        if app is not None and app.stage in ("declined", "withdrawn"):
            raise HTTPException(409, "This person is no longer in the process, so there is no offer to decide.")
        # The second person must be someone who did not write the terms. The base only refuses the person who clicked "Ask for approval", so a
        # favour (author drafts, a colleague asks, the author approves) would otherwise leave one person in control of both. Terms cannot be edited after
        # they are drafted, so the person who drafted them is also the last person who changed them.
        # (Someone who only asked for the approval is refused by the base below, with its own message.)
        if o is not None and clean_email(u["user"]) == clean_email(o.created_by or "") and clean_email(u["user"]) != clean_email(pending.requested_by or ""):
            raise HTTPException(403, "You wrote these terms, so a different person has to approve them.")
    try:
        a = decide(s, approval_id, body.approve, u["user"], u["role"], body.note or None)
    except ApprovalError as exc:
        raise HTTPException(409, str(exc)) from exc
    if a.action == "offer.approve":
        o = s.get(Offer, int(a.payload.get("offer_id", 0)))
        if o is not None and o.approval_id == a.id:
            o.status = "approved" if body.approve else "rejected"
            record_audit(s, u["user"], "offer.approved" if body.approve else "offer.rejected", f"offer:{o.id}", {"approval": a.id})
    return {"status": a.status}


def _utc(v: str) -> str:
    """The audit log stores its time as text. Make sure it says UTC, so a browser does not read it as local time."""
    try:
        t = datetime.fromisoformat(v)
    except (TypeError, ValueError):
        return v
    return (t if t.tzinfo else t.replace(tzinfo=timezone.utc)).isoformat()


@router.get("/audit", summary="Audit log, newest first")
def audit(limit: int = Query(100, ge=1, le=1000), s: Session = Depends(db)):
    return [{"id": e.id, "actor": e.actor, "action": e.action, "target": e.target, "detail": e.detail, "at": _utc(e.created_at)} for e in s.scalars(select(AuditEntry).order_by(AuditEntry.id.desc()).limit(limit))]


@router.get("/audit/verify", summary="Check the audit chain has not been edited")
def audit_verify(s: Session = Depends(db)):
    ok, bad = verify_audit_chain(s)
    return {"ok": ok, "first_bad_id": bad, "entries": s.scalar(select(__import__("sqlalchemy").func.count()).select_from(AuditEntry))}


@router.get("/integrations", summary="Every adapter, which one is selected, and what it needs")
def integrations(ctx: Ctx = Depends(get_ctx)):
    st = ctx.settings
    chosen = {c: getattr(st, f"{c}_adapter") for c in CATEGORIES}
    out = []
    for row in ctx.registry.describe():
        env = ENV_VARS.get((row["category"], row["name"]), [])
        out.append({**row, "selected": chosen.get(row["category"]) == row["name"], "env_vars": env, "configured": all(bool(getattr(st, v.lower(), "")) for v in env) if env else True})
    return {"categories": list(CATEGORIES), "adapters": out, "demo_mode": st.demo_mode, "platform_note": "Slatehire only reads from your ATS and mailbox. It never writes to them, never emails a candidate and never sends an offer: offers leave as a file for your signing tool."}


@router.post("/integrations/{category}/test", summary="Test the selected adapter in a category")
def test_integration(category: str, ctx: Ctx = Depends(get_ctx), u: dict = Depends(writer)):
    if category not in CATEGORIES:
        raise HTTPException(404, "Unknown category.")
    try:
        ok, detail = ctx.adapters[category].healthcheck()
    except Exception as exc:  # noqa: BLE001 - a failed check is a plain message, never a stack trace
        ok, detail = False, f"The check failed: {type(exc).__name__}."
    return {"category": category, "ok": ok, "detail": detail}


@router.get("/settings", summary="Mode, kill switch and config problems")
def get_settings(s: Session = Depends(db), ctx: Ctx = Depends(get_ctx)):
    eff, st = ctx.effective(s), ctx.settings
    return {"mode": st.mode.value, "effective_mode": eff.mode.value, "kill_switch": eff.kill_switch, "demo_mode": st.demo_mode, "problems": st.problems(), "scorer": "offline rules (not a language model)", "llm_backend": st.effective_llm_backend.value,
            "rules": {"retention_days": st.retention_days, "fairness_min_group": st.fairness_min_group, "fairness_threshold": st.fairness_threshold, "min_scorecards": st.min_scorecards, "blind_default": st.blind_default},
            "adapters": {c: getattr(st, f"{c}_adapter") for c in CATEGORIES}}


class SettingsIn(BaseModel):
    kill_switch: bool | None = None
    force_draft: bool | None = None


@router.post("/settings", summary="Turn the kill switch or draft mode on or off (owner only). The app can never switch live mode on.")
def post_settings(body: SettingsIn, s: Session = Depends(db), ctx: Ctx = Depends(get_ctx), u: dict = Depends(owner)):
    if body.kill_switch is not None:
        set_state(s, "kill_switch", "1" if body.kill_switch else "0")
        record_audit(s, u["user"], "settings.kill_switch", None, {"on": body.kill_switch})
    if body.force_draft is not None:
        set_state(s, "force_draft", "1" if body.force_draft else "0")
        record_audit(s, u["user"], "settings.force_draft", None, {"on": body.force_draft})
    s.flush()
    return get_settings(s, ctx)
