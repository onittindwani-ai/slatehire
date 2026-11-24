"""Database level guards. They stop code paths that should never exist: editing a locked rubric, editing or deleting the audit log, changing a submitted scorecard."""

from __future__ import annotations

from sqlalchemy import event
from sqlalchemy.orm import attributes

from slatehire.errors import RuleError
from slatehire.models import Rubric, Scorecard
from sendora_core.models import AuditEntry


def _locked_rubric_changed(mapper, connection, target: Rubric) -> None:
    st = attributes.instance_state(target)
    hist = {k: attributes.get_history(target, k) for k in ("criteria", "blind", "redaction_version", "fingerprint", "role_id", "version")}
    was_locked = st.committed_state.get("locked", target.locked)
    if was_locked and any(h.has_changes() for h in hist.values()):
        raise RuleError("A locked rubric cannot be changed. Start a new version and lock it again.")


def _never(mapper, connection, target) -> None:
    raise RuleError(f"{type(target).__name__} rows are append only. They cannot be changed or deleted.")


def install() -> None:
    event.listen(Rubric, "before_update", _locked_rubric_changed)
    for cls in (AuditEntry, Scorecard):
        event.listen(cls, "before_update", _never)
        event.listen(cls, "before_delete", _never)


install()
