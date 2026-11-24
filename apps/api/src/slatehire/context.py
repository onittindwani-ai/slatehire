"""Runtime context shared by the API and the worker: settings, database, adapters."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from sqlalchemy.orm import Session, sessionmaker

from slatehire import clock, model_tasks
from slatehire.config import Settings
from slatehire.models import State
from slatehire.offline_llm import OfflineBackend
from slatehire.registry import build_adapters, build_registry
from sendora_core.costs import CostTracker
from sendora_core.llm import LLM, build_llm
from sendora_core.settings import LLMBackendKind, Mode


@dataclass
class Ctx:
    settings: Settings
    factory: sessionmaker[Session]
    adapters: dict[str, Any] = field(default_factory=dict)
    registry: Any = None

    def __post_init__(self) -> None:
        self.registry = self.registry or build_registry(self.settings)
        if not self.adapters:
            self.adapters = build_adapters(self.settings, self.registry)

    def effective(self, session: Session) -> Settings:
        """The kill switch can be turned on in the app and the mode pulled back to draft. Neither can go the other way."""
        kill, force = session.get(State, "kill_switch"), session.get(State, "force_draft")
        upd: dict[str, Any] = {}
        if kill and kill.value == "1":
            upd["kill_switch"] = True
        if force and force.value == "1":
            upd["mode"] = Mode.DRAFT
        return self.settings.model_copy(update=upd) if upd else self.settings

    def adapter(self, session: Session, category: str):
        """The adapter with the effective settings (kill switch and forced draft) applied, so a write is stopped by them."""
        import copy

        a = copy.copy(self.adapters[category])
        if hasattr(a, "s"):
            a.s = self.effective(session)
        return a

    def llm(self, session: Session) -> LLM:
        # LLM_BACKEND=offline (default) | fixture | anthropic. The offline stand in is the zero account default.
        # The anthropic path is UNVERIFIED against the real service. The one job behind it is in model_tasks.py.
        return build_llm(self.effective(session), CostTracker(session), offline=OfflineBackend())

    def model_on(self) -> bool:
        """True when a model backend (recorded fixtures or the real API) is selected. With LLM_BACKEND=offline nothing calls a model, so the default behaviour does not change."""
        return self.settings.effective_llm_backend is not LLMBackendKind.OFFLINE

    def scorer(self, session: Session):
        """The model scorer, or None for the rules. It needs a model backend AND SCORER=model: scoring people with a model is always an explicit choice. It sees redacted text only."""
        if self.settings.scorer == "model" and self.model_on():
            return model_tasks.ModelScorer(self.llm(session))
        return None

    def now(self, session: Session):
        return clock.now(session, self.settings.demo_mode)

    def today(self, session: Session) -> date:
        return clock.today(session, self.settings.demo_mode)


def set_state(session: Session, key: str, value: str) -> None:
    row = session.get(State, key)
    if row is None:
        session.add(State(key=key, value=value))
    else:
        row.value = value


def get_state(session: Session, key: str, default: str = "") -> str:
    row = session.get(State, key)
    return row.value if row else default
