"""Cost tracker. Prices are per million tokens and configurable. Defaults are placeholders marked UNVERIFIED."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from sendora_core.models import CostEntry

# USD per million tokens (input, output), read from the vendor models overview page on 2026-11-23 (see hub docs/FACTS-AND-SOURCES.md).
# Sonnet 5.5 is a flat 2 and 10. The page lists Haiku 5.5 as "from" 0.10 and 0.50, so this is a lower bound and the real bill can be
# higher. Set exact prices from the vendor price page for your account before you quote a cost to a client.
DEFAULT_PRICES: dict[str, tuple[float, float]] = {
    "claude-sonnet-5-5": (2.0, 10.0),
    "claude-haiku-5-5": (0.10, 0.50),
}


class CostTracker:
    def __init__(self, session: Session, prices: dict[str, tuple[float, float]] | None = None):
        self.session = session
        self.prices = prices or DEFAULT_PRICES

    def cost_usd(self, model: str, input_tokens: int, output_tokens: int) -> float:
        pin, pout = self.prices.get(model, (0.0, 0.0))
        return round((input_tokens * pin + output_tokens * pout) / 1_000_000, 6)

    def record(self, model: str, purpose: str, input_tokens: int, output_tokens: int) -> CostEntry:
        entry = CostEntry(
            model=model, purpose=purpose, input_tokens=input_tokens, output_tokens=output_tokens,
            usd=self.cost_usd(model, input_tokens, output_tokens),
        )
        self.session.add(entry)
        self.session.flush()
        return entry

    def total_usd(self) -> float:
        return float(self.session.scalar(select(func.coalesce(func.sum(CostEntry.usd), 0.0))) or 0.0)

    def by_purpose(self) -> dict[str, float]:
        rows = self.session.execute(select(CostEntry.purpose, func.sum(CostEntry.usd)).group_by(CostEntry.purpose))
        return {p: float(v) for p, v in rows}
