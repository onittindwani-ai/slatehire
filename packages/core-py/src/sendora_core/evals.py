"""Tiny eval runner: cases with expected answers, a scorer, a report with pass rate and failures."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


@dataclass
class EvalCase:
    id: str
    input: Any
    expected: Any
    tags: tuple[str, ...] = ()


@dataclass
class EvalReport:
    name: str
    total: int
    passed: int
    failures: list[dict] = field(default_factory=list)

    @property
    def pass_rate(self) -> float:
        return self.passed / self.total if self.total else 0.0

    def summary(self) -> str:
        return f"{self.name}: {self.passed}/{self.total} passed ({self.pass_rate:.0%})"


def run_eval(
    name: str, cases: list[EvalCase], predict: Callable[[Any], Any],
    score: Callable[[Any, Any], bool] = lambda got, want: got == want,
) -> EvalReport:
    failures: list[dict] = []
    passed = 0
    for c in cases:
        try:
            got = predict(c.input)
            ok = score(got, c.expected)
        except Exception as exc:
            got, ok = f"error: {exc}", False
        if ok:
            passed += 1
        else:
            failures.append({"id": c.id, "expected": c.expected, "got": got, "tags": list(c.tags)})
    return EvalReport(name, len(cases), passed, failures)
