"""Adapter registry. Every integration is an adapter with a tier and a seed (offline) implementation.

Tier A: built and tested against a mock server. Tier B: built from public docs, not run live (UNVERIFIED).
Tier C: a Claude Code recipe prompt generates the adapter.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from sendora_core.settings import BaseAppSettings


class AdapterError(RuntimeError):
    pass


@dataclass(frozen=True)
class AdapterSpec:
    category: str  # for example "email", "calendar", "crm"
    name: str  # for example "gmail", "calcom", "seed"
    tier: str  # "A", "B" or "C"
    factory: Callable[[BaseAppSettings], Any]
    live_verified: bool = False  # True only after a run against the real vendor
    notes: str = ""


@dataclass
class AdapterRegistry:
    settings: BaseAppSettings
    _specs: dict[tuple[str, str], AdapterSpec] = field(default_factory=dict)

    def register(self, spec: AdapterSpec) -> None:
        if spec.tier not in {"A", "B", "C"}:
            raise AdapterError("tier must be A, B or C")
        key = (spec.category, spec.name)
        if key in self._specs:
            raise AdapterError(f"Adapter {spec.category}/{spec.name} is already registered.")
        self._specs[key] = spec

    def get(self, category: str, name: str) -> Any:
        spec = self._specs.get((category, name))
        if spec is None:
            known = ", ".join(sorted(n for c, n in self._specs if c == category)) or "none"
            raise AdapterError(f"No adapter {category}/{name}. Known for {category}: {known}.")
        return spec.factory(self.settings)

    def describe(self) -> list[dict]:
        """Rows for the Integrations page and the capabilities doc. live_verified is never inferred."""
        return [
            {"category": s.category, "name": s.name, "tier": s.tier, "live_verified": s.live_verified, "notes": s.notes}
            for s in sorted(self._specs.values(), key=lambda s: (s.category, s.name))
        ]

    def by_tier(self) -> dict[str, int]:
        out: dict[str, int] = {"A": 0, "B": 0, "C": 0}
        for s in self._specs.values():
            out[s.tier] += 1
        return out
