"""The offline stand in for the model behind `build_llm`. It is plain rules, NOT a language model.

It answers the one job Slatehire gives a model (see `model_tasks.py`): score one rubric criterion against a redacted resume. The request starts with the line `[task:score_criterion]`,
carries the criterion on a line `CRITERION_JSON: {...}` and the redacted resume in a marked data block (`source=resume`). The answer is JSON that matches the schema a real model must match:

    {"shown": true | false, "level": 1 to 5, "evidence": "<one sentence copied from the resume, or empty>", "reason": "<one short sentence>"}

The stand in reads the sentences of the resume it was given and runs `scoring.propose`, the rules scorer Slatehire always had, then keeps the first quote as the evidence. A real model
(`LLM_BACKEND=anthropic`) uses the same shape, so the checks around it (every quote must be found in the resume, the total is arithmetic, a person makes every decision) do not change.
Nothing here calls a network.
"""

from __future__ import annotations

import json
import re

from slatehire.scoring import propose, sentences
from sendora_core.llm import LLMResponse
from sendora_core.safety import UNTRUSTED_CLOSE, UNTRUSTED_OPEN


def blocks(prompt: str) -> dict[str, str]:
    """The data blocks of a prompt, by source name."""
    pat = re.escape(UNTRUSTED_OPEN) + r" source=([^\n]*)\n(.*?)\n" + re.escape(UNTRUSTED_CLOSE)
    return {m.group(1): m.group(2) for m in re.finditer(pat, prompt, re.S)}


def task_of(prompt: str) -> str:
    m = re.match(r"\[task:(\w+)\]", prompt)
    return m.group(1) if m else ""


def answer_score_criterion(prompt: str) -> dict:
    m = re.search(r"CRITERION_JSON: (\{.*\})", prompt)
    try:
        criterion = json.loads(m.group(1)) if m else {}
    except ValueError:
        criterion = {}
    resume = blocks(prompt).get("resume", "")
    item = propose({"id": criterion.get("id", 0), "look_for": list(criterion.get("look_for", []))}, sentences(resume, []))
    if item["state"] != "scored" or not item["quotes"]:
        return {"shown": False, "level": 1, "evidence": "", "reason": item["rationale"][:300]}
    return {"shown": True, "level": int(item["value"]), "evidence": item["quotes"][0], "reason": item["rationale"][:300]}


class OfflineBackend:
    """Same call shape as the real backends, so the whole product runs with no key and no network."""

    is_live = False
    supports_json_schema = False

    def complete(self, *, model: str, system: str, prompt: str, max_tokens: int) -> LLMResponse:
        text = json.dumps(answer_score_criterion(prompt)) if task_of(prompt) == "score_criterion" else "{}"
        return LLMResponse(text=text, input_tokens=len(prompt) // 4, output_tokens=len(text) // 4, model="offline-rules")
