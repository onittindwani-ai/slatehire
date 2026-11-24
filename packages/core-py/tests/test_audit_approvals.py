import pytest
from sqlalchemy import update

from sendora_core.approvals import ApprovalError, decide, pending, request_approval, require_approved
from sendora_core.audit import record_audit, verify_audit_chain
from sendora_core.models import AuditEntry


def test_chain_ok_and_tamper_detected(session):
    for i in range(4):
        record_audit(session, "owner", "x", f"t{i}", {"i": i})
    assert verify_audit_chain(session) == (True, None)
    session.execute(update(AuditEntry).where(AuditEntry.id == 2).values(actor="intruder"))
    session.flush()
    ok, bad = verify_audit_chain(session)
    assert ok is False and bad == 2


def test_approval_flow(session):
    a = request_approval(session, "send_email", "Send intro to Ada", {"to": "ada@example.test"}, risk="high")
    assert [p.id for p in pending(session)] == [a.id]
    with pytest.raises(ApprovalError):
        require_approved(session, a.id, "send_email")
    with pytest.raises(ApprovalError):
        decide(session, a.id, True, "bot", role="viewer")
    decide(session, a.id, True, "onit", role="owner", note="looks right")
    assert require_approved(session, a.id, "send_email").status == "approved"
    with pytest.raises(ApprovalError):
        require_approved(session, a.id, "other_action")
    with pytest.raises(ApprovalError):
        decide(session, a.id, False, "onit", role="owner")
    assert pending(session) == []
    assert verify_audit_chain(session)[0]


def test_approval_validation(session):
    with pytest.raises(ApprovalError):
        request_approval(session, "x", "y", risk="extreme")
    with pytest.raises(ApprovalError):
        decide(session, 999, True, "o", role="owner")


def test_requester_cannot_decide_own_request(session):
    from sendora_core.approvals import SelfApprovalError

    a = request_approval(session, "send_email", "Send intro", requested_by="Ada@Example.test")
    with pytest.raises(SelfApprovalError, match="someone else must decide"):
        decide(session, a.id, True, " ada@example.test ", role="owner")
    with pytest.raises(ApprovalError):  # callers that catch the base error keep working
        decide(session, a.id, False, "ada@example.test", role="approver")
    assert a.status == "pending" and [p.id for p in pending(session)] == [a.id]
    decide(session, a.id, True, "bo@example.test", role="approver")
    assert require_approved(session, a.id, "send_email").decided_by == "bo@example.test"


def test_self_approval_check_ignores_empty_names(session):
    a = request_approval(session, "x", "y", requested_by="")
    decide(session, a.id, True, "", role="owner")  # nothing to compare, so no false refusal
    assert a.status == "approved"
