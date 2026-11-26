"""Approval queue. Risky actions are requested here and a person decides."""

from __future__ import annotations

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from sendora_core.audit import record_audit
from sendora_core.db import utcnow
from sendora_core.models import Approval

ROLES_THAT_DECIDE = {"owner", "approver"}


class ApprovalError(ValueError):
    pass


class SelfApprovalError(ApprovalError):
    """The person who asked for an action tried to decide it themselves. A second person must decide."""


def request_approval(
    session: Session, action: str, summary: str, payload: dict | None = None, risk: str = "medium", requested_by: str = "system"
) -> Approval:
    if risk not in {"low", "medium", "high"}:
        raise ApprovalError("risk must be low, medium or high")
    a = Approval(action=action, summary=summary[:500], payload=payload or {}, risk=risk, requested_by=requested_by)
    session.add(a)
    session.flush()
    record_audit(session, requested_by, "approval.requested", f"approval:{a.id}", {"action": action, "risk": risk})
    return a


def _same_person(a: str | None, b: str | None) -> bool:
    return bool(a) and bool(b) and a.strip().lower() == b.strip().lower()


def decide(session: Session, approval_id: int, approve: bool, decided_by: str, role: str, note: str | None = None) -> Approval:
    if role not in ROLES_THAT_DECIDE:
        raise ApprovalError("Only an owner or an approver can decide.")
    a = session.get(Approval, approval_id)
    if a is None:
        raise ApprovalError(f"Approval {approval_id} does not exist.")
    if a.status != "pending":
        raise ApprovalError(f"Approval {approval_id} was already {a.status}.")
    if _same_person(a.requested_by, decided_by):
        raise SelfApprovalError(
            f"Approval {approval_id} was requested by {a.requested_by}, so someone else must decide it. "
            "Ask another owner or approver."
        )
    new_status = "approved" if approve else "rejected"
    # One conditional update decides it: when two people (or one double click) decide at the same moment, exactly one update changes a row.
    res = session.execute(
        update(Approval)
        .where(Approval.id == approval_id, Approval.status == "pending")
        .values(status=new_status, decided_by=decided_by, decision_note=note, decided_at=utcnow())
        .execution_options(synchronize_session=False)
    )
    if res.rowcount != 1:
        session.refresh(a)
        raise ApprovalError(f"Approval {approval_id} was already {a.status}.")
    session.refresh(a)
    record_audit(session, decided_by, f"approval.{a.status}", f"approval:{a.id}", {"note": note})
    return a


def pending(session: Session) -> list[Approval]:
    return list(session.scalars(select(Approval).where(Approval.status == "pending").order_by(Approval.id)))


def require_approved(session: Session, approval_id: int, action: str) -> Approval:
    """Gate for code that performs the risky action: only runs when the exact approval was approved."""
    a = session.get(Approval, approval_id)
    if a is None or a.status != "approved" or a.action != action:
        raise ApprovalError(f"'{action}' needs an approved request. Approval {approval_id} is not approved for it.")
    return a
