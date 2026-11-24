"""One error type for business rules. The message is written for a person."""

from __future__ import annotations


class RuleError(ValueError):
    """A rule refused the action. Nothing was changed."""


def need_person(actor: str) -> None:
    """Every outcome is decided by a named person. A system actor (the worker, a job, 'system') can never decide."""
    if not actor or "@" not in actor:
        raise RuleError("A person has to do this. Automatic decisions are not allowed.")
