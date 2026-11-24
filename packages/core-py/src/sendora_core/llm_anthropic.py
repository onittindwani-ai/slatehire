"""The Anthropic Messages API as a backend for the shared model wrapper, over plain HTTP (httpx, no vendor SDK).

LIVE USE IS UNVERIFIED. The request and response shapes below follow the vendor docs read on 2026-11-23
(see docs/FACTS-AND-SOURCES.md of the hub). This code has been run only against a local fake server that
checks the request shape. It has never been run against the real API with a real key.

What it sends: POST {base_url}/v1/messages with headers x-api-key, anthropic-version and content-type,
and a JSON body with model, max_tokens, system and messages. For structured output it adds
output_config.format = {"type": "json_schema", "schema": ...}. It never sends temperature, top_p or top_k
(removed in API version 2026-10-21) and never forces a tool call (not supported on the 5.5 models).
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from sendora_core.llm_types import LLMError, LLMResponse

log = logging.getLogger("sendora_core.llm")

RETRYABLE_STATUS = frozenset({408, 429, 500, 502, 503, 504, 529})
MAX_RETRY_AFTER_S = 30.0

# Keywords the structured output feature does not accept (vendor docs, 2026-11-23). They are removed from the schema
# we send. The caller's own validation still enforces them afterwards.
_UNSUPPORTED_KEYS = frozenset({
    "minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum", "multipleOf", "minLength", "maxLength", "maxItems",
    "uniqueItems", "minProperties", "maxProperties", "title",
})


class LLMAPIError(LLMError):
    """The API answered with an error, or the request could not be made."""

    def __init__(self, message: str, *, status: int | None = None, error_type: str | None = None,
                 request_id: str | None = None, retry_after: float | None = None):
        super().__init__(message)
        self.status, self.error_type, self.request_id, self.retry_after = status, error_type, request_id, retry_after

    @property
    def retryable(self) -> bool:
        return self.status is None or self.status in RETRYABLE_STATUS or self.error_type in {"overloaded_error", "timeout_error", "api_error"}


def to_api_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Make a Pydantic JSON schema acceptable to structured outputs: additionalProperties false on every object,
    oneOf turned into anyOf, unsupported keywords dropped, minItems kept only when 0 or 1."""

    def walk(node: Any) -> Any:
        if isinstance(node, list):
            return [walk(n) for n in node]
        if not isinstance(node, dict):
            return node
        out: dict[str, Any] = {}
        for k, v in node.items():
            if k in _UNSUPPORTED_KEYS and not isinstance(v, dict):
                continue
            if k == "oneOf":
                k = "anyOf"
            if k == "minItems" and v not in (0, 1):
                continue
            out[k] = v if k in {"enum", "const", "required", "default"} else walk(v)
        if out.get("type") == "object" or "properties" in out:
            out["additionalProperties"] = False
        return out

    return walk(schema)


class AnthropicBackend:
    supports_json_schema = True
    is_live = True  # the kill switch and the call budget apply to live backends

    def __init__(self, api_key: str, *, base_url: str = "https://api.anthropic.com", version: str = "2026-10-21",
                 timeout: float = 120.0, thinking: str = "default", transport: httpx.BaseTransport | None = None):
        if not api_key:
            raise LLMError("ANTHROPIC_API_KEY is empty.")
        self._key, self.version, self.thinking = api_key, version, thinking
        self.url = base_url.rstrip("/") + "/v1/messages"
        self._client = httpx.Client(timeout=timeout, transport=transport)

    def __repr__(self) -> str:  # never show the key
        return f"AnthropicBackend(url={self.url!r}, version={self.version!r})"

    def build_request(self, *, model: str, system: str, prompt: str, max_tokens: int, schema: dict | None) -> dict[str, Any]:
        body: dict[str, Any] = {"model": model, "max_tokens": max_tokens, "messages": [{"role": "user", "content": prompt}]}
        if system:
            body["system"] = system
        if schema is not None:
            body["output_config"] = {"format": {"type": "json_schema", "schema": to_api_schema(schema)}}
        if self.thinking == "off":
            # Sonnet 5.5 rejects "disabled" and wants "between_tools"; Haiku 5.5 accepts "disabled" (vendor docs, 2026-11-23).
            if "sonnet-5-5" in model:
                body["thinking"] = {"type": "between_tools"}
            elif "haiku-5-5" in model:
                body["thinking"] = {"type": "disabled"}
        return body

    def complete(self, *, model: str, system: str, prompt: str, max_tokens: int, schema: dict | None = None) -> LLMResponse:
        headers = {"x-api-key": self._key, "anthropic-version": self.version, "content-type": "application/json"}
        body = self.build_request(model=model, system=system, prompt=prompt, max_tokens=max_tokens, schema=schema)
        try:
            r = self._client.post(self.url, headers=headers, json=body)
        except httpx.TimeoutException as exc:
            raise LLMAPIError(f"The model request timed out ({type(exc).__name__}).", error_type="timeout_error") from None
        except httpx.HTTPError as exc:
            raise LLMAPIError(f"The model request could not be made ({type(exc).__name__}).") from None
        request_id = r.headers.get("request-id")
        if r.status_code != 200:
            raise self._error(r, request_id)
        try:
            data = r.json()
            text = "".join(b.get("text", "") for b in data["content"] if b.get("type") == "text")  # thinking blocks are skipped
            usage = data.get("usage", {})
            stop = data.get("stop_reason")
            resp = LLMResponse(text, int(usage.get("input_tokens", 0)), int(usage.get("output_tokens", 0)), data.get("model", model), stop, request_id)
        except (ValueError, KeyError, TypeError, AttributeError):
            raise LLMAPIError("The model answered with a body this code does not understand.", status=200, request_id=request_id) from None
        if stop == "refusal":
            raise LLMError(f"The model declined to answer (request {request_id}).")
        log.info("llm ok model=%s in=%d out=%d stop=%s request_id=%s", resp.model, resp.input_tokens, resp.output_tokens, stop, request_id)
        return resp

    @staticmethod
    def _error(r: httpx.Response, request_id: str | None) -> LLMAPIError:
        etype = msg = None
        try:
            err = r.json().get("error", {})
            etype, msg = err.get("type"), err.get("message")
            request_id = request_id or r.json().get("request_id")
        except (ValueError, AttributeError):
            pass
        retry_after: float | None = None
        try:
            if "retry-after" in r.headers:
                retry_after = min(float(r.headers["retry-after"]), MAX_RETRY_AFTER_S)
        except ValueError:
            pass
        text = (msg or "no message")[:300]
        log.warning("llm error status=%s type=%s request_id=%s", r.status_code, etype, request_id)
        return LLMAPIError(f"The model API said {r.status_code} {etype or ''}: {text} (request {request_id}).",
                           status=r.status_code, error_type=etype, request_id=request_id, retry_after=retry_after)
