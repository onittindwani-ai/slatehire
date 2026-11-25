"""Settings shared by every system. Systems subclass BaseAppSettings and add their own fields."""

from __future__ import annotations

import re
from enum import StrEnum
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Mode(StrEnum):
    DRAFT = "draft"
    LIVE = "live"


class LLMMode(StrEnum):
    FIXTURE = "fixture"
    LIVE = "live"


class LLMBackendKind(StrEnum):
    """Which model path runs. offline is the zero account default and never touches the network."""

    OFFLINE = "offline"
    FIXTURE = "fixture"
    ANTHROPIC = "anthropic"


PLACEHOLDER_SECRET = re.compile(r"(dev-only|change-?me|demo-secret|example|replace|placeholder|xxxx|secret-here|your-secret)", re.I)
MIN_SECRET_LENGTH = 32


class ConfigError(RuntimeError):
    """The settings cannot be used safely. The message lists every problem in plain words and never holds a secret."""


class BaseAppSettings(BaseSettings):
    # env_ignore_empty: a line such as CALCOM_EVENT_TYPE_ID= (copied from .env.example) means "not set", it must not crash a number setting
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", env_prefix="", env_ignore_empty=True)

    app_name: str = "sendora-system"
    database_url: str = "sqlite:///./app.sqlite3"
    session_secret: str = Field(default="dev-only-change-me-please-32-bytes!", min_length=16)
    mode: Mode = Mode.DRAFT
    kill_switch: bool = False
    llm_mode: LLMMode = LLMMode.FIXTURE
    anthropic_api_key: str | None = Field(default=None, repr=False)
    llm_hard_model: str = "claude-sonnet-5-5"
    llm_bulk_model: str = "claude-haiku-5-5"
    demo_mode: bool = True
    # A demo (DEMO_MODE=true) keeps public demo logins and a data reset button, so it refuses to start on a server database (Postgres)
    # unless this is set on purpose, for example for a throw away trial on a private network.
    allow_demo_server: bool = False  # ALLOW_DEMO_SERVER
    max_body_bytes: int = Field(default=26_214_400, ge=1024)  # MAX_BODY_BYTES: a request larger than this is refused before it is read (25 MB)
    # Model path. LLM_BACKEND wins when set. When it is empty, LLM_MODE=live means anthropic and anything else means offline.
    llm_backend: LLMBackendKind | None = None
    llm_model: str | None = None  # LLM_MODEL: one model id for both the hard and the bulk kind
    anthropic_base_url: str = "https://api.anthropic.com"  # ANTHROPIC_BASE_URL: tests and proxies
    anthropic_version: str = "2026-10-21"  # the anthropic-version header
    llm_timeout: float = Field(default=120.0, gt=0)  # seconds per request
    llm_max_tokens: int = Field(default=4096, ge=1)  # default reply limit, thinking tokens included
    llm_max_retries: int = Field(default=2, ge=0, le=6)  # retries after the first try on 429, 5xx, 529 and network errors
    llm_call_budget: int | None = Field(default=None, ge=1)  # most live calls per process, then LLMBudgetError
    llm_budget_usd: float | None = Field(default=None, gt=0)  # most total tracked spend, read from the cost table
    llm_thinking: Literal["default", "off"] = "default"  # off asks for the lowest thinking setting where the model allows it
    llm_fixtures_dir: str | None = None  # LLM_FIXTURES_DIR: where fixture replay reads and recording writes
    llm_record: bool = False  # LLM_RECORD: save every live answer as a fixture
    llm_redact: bool = True  # LLM_REDACT: logs and fixtures never hold a full prompt or a key
    llm_log_prompts: bool = False  # LLM_LOG_PROMPTS: log a redacted, shortened prompt

    @field_validator("database_url")
    @classmethod
    def _db_url(cls, v: str) -> str:
        if not v.startswith(("sqlite", "postgresql")):
            raise ValueError("database_url must start with sqlite or postgresql. Example: sqlite:///./app.sqlite3")
        return v

    @property
    def effective_llm_backend(self) -> LLMBackendKind:
        if self.llm_backend is not None:
            return self.llm_backend
        return LLMBackendKind.ANTHROPIC if self.llm_mode is LLMMode.LIVE else LLMBackendKind.OFFLINE

    def model_for(self, kind: str) -> str:
        """The model id for kind 'hard' or 'bulk'. LLM_MODEL overrides both."""
        if self.llm_model:
            return self.llm_model
        return self.llm_hard_model if kind == "hard" else self.llm_bulk_model

    @property
    def demo_shortcuts(self) -> bool:
        """True when the public demo password and the demo data reset may exist: a demo with no owner password set.
        Setting OWNER_PASSWORD_HASH turns every demo shortcut off, so a real owner never shares the system with a public login."""
        return self.demo_mode and not getattr(self, "owner_password_hash", None)

    def runtime_errors(self) -> list[str]:
        """Problems that stop the app from starting. Checked once when the API or the worker starts."""
        out: list[str] = []
        if not self.demo_mode:
            if len(self.session_secret) < MIN_SECRET_LENGTH or PLACEHOLDER_SECRET.search(self.session_secret):
                out.append(
                    f"SESSION_SECRET is missing, too short (under {MIN_SECRET_LENGTH} characters) or still an example value. "
                    "Anyone who has read the public code could sign in as the owner. Create one with: python3 -c \"import secrets; print(secrets.token_urlsafe(48))\""
                )
        elif self.database_url.startswith("postgresql") and not self.allow_demo_server:
            out.append(
                "DEMO_MODE is true while DATABASE_URL points at a server database. A demo has public logins and a reset button that erases the data. "
                "Set DEMO_MODE=false (and OWNER_PASSWORD_HASH), or set ALLOW_DEMO_SERVER=true for a throw away trial."
            )
        return list(dict.fromkeys(out))

    def check_runtime(self) -> None:
        errors = self.runtime_errors()
        if errors:
            raise ConfigError("The settings are not safe to start with:\n- " + "\n- ".join(errors))

    def problems(self) -> list[str]:
        """Plain language list of config problems for tools/doctor.py. Never includes secret values."""
        out: list[str] = list(self.runtime_errors())
        if self.mode is Mode.LIVE and self.demo_mode:
            out.append("MODE is live while DEMO_MODE is true. Set DEMO_MODE=false before going live.")
        if (self.session_secret.startswith("dev-only") or PLACEHOLDER_SECRET.search(self.session_secret)) and self.demo_mode and self.mode is Mode.LIVE:
            out.append("SESSION_SECRET is still an example value. Generate a long random one.")
        if self.effective_llm_backend is LLMBackendKind.ANTHROPIC and not self.anthropic_api_key:
            out.append("The model backend is anthropic (LLM_BACKEND or LLM_MODE=live) but ANTHROPIC_API_KEY is empty.")
        if self.effective_llm_backend is LLMBackendKind.FIXTURE and not self.llm_fixtures_dir:
            out.append("LLM_BACKEND is fixture but LLM_FIXTURES_DIR is empty.")
        if self.llm_record and not self.llm_fixtures_dir:
            out.append("LLM_RECORD is on but LLM_FIXTURES_DIR is empty.")
        if not self.anthropic_base_url.startswith(("https://", "http://127.0.0.1", "http://localhost")):
            out.append("ANTHROPIC_BASE_URL must start with https:// (plain http is only for 127.0.0.1 or localhost tests).")
        return out
