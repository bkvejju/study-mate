"""Configuration: load a ``.env`` file and resolve AI settings per role.

Two roles use AI, and each can have its own provider / API key / model so you
can use a stronger (or cheaper) model for the heavy one-off generation and a
different one for interactive usage:

- ``explainer`` — the initial, token-heavy HTML generation (``study-mate explain``).
- ``panel``     — the on-the-go study panel (summarise / explain / quiz / ...).

Resolution order for each setting (first non-empty wins):

  1. Role-specific var:  ``STUDYMATE_EXPLAINER_AI_*`` or ``STUDYMATE_PANEL_AI_*``
  2. Shared fallback:    ``STUDYMATE_AI_*``

Recognised suffixes: ``PROVIDER`` (stub | openai | anthropic), ``API_KEY``, ``MODEL``.

Values are read from the process environment, which is populated from a ``.env``
file in the current working directory at startup (real env vars take priority).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - import guard
    load_dotenv = None

_ROLE_PREFIX = {
    "explainer": "STUDYMATE_EXPLAINER_AI_",
    "panel": "STUDYMATE_PANEL_AI_",
}
_SHARED_PREFIX = "STUDYMATE_AI_"

_env_loaded = False


def load_env(path: Path | None = None) -> None:
    """Load environment variables from a ``.env`` file (once).

    Existing process environment variables always take precedence, so explicit
    exports and test monkeypatching are never overridden.
    """
    global _env_loaded
    if _env_loaded or load_dotenv is None:
        return
    dotenv_path = path or (Path.cwd() / ".env")
    load_dotenv(dotenv_path=dotenv_path, override=False)
    _env_loaded = True


@dataclass(frozen=True)
class AIConfig:
    """Resolved AI settings for a single role."""

    provider: str
    api_key: str
    model: str | None

    @property
    def is_stub(self) -> bool:
        return self.provider == "stub" or not self.api_key


def _resolve(role: str, suffix: str) -> str | None:
    prefix = _ROLE_PREFIX.get(role)
    if prefix:
        value = os.environ.get(prefix + suffix)
        if value:
            return value
    return os.environ.get(_SHARED_PREFIX + suffix) or None


def ai_config(role: str) -> AIConfig:
    """Resolve the AI configuration for ``role`` (``"explainer"`` or ``"panel"``)."""
    load_env()
    return AIConfig(
        provider=(_resolve(role, "PROVIDER") or "stub").lower(),
        api_key=_resolve(role, "API_KEY") or "",
        model=_resolve(role, "MODEL"),
    )


# Token-reduction (headroom) settings. Resolved per role like the AI settings:
# role-specific STUDYMATE_EXPLAINER_COMPRESS / STUDYMATE_PANEL_COMPRESS, falling
# back to the shared STUDYMATE_COMPRESS. Values are truthy ("1", "true", "on",
# "yes"). Defaults to enabled — but compression is best-effort and no-ops when
# the optional `headroom-ai` library is not installed.
_COMPRESS_ROLE_PREFIX = {
    "explainer": "STUDYMATE_EXPLAINER_",
    "panel": "STUDYMATE_PANEL_",
}
_COMPRESS_SHARED_PREFIX = "STUDYMATE_"


@dataclass(frozen=True)
class CompressionConfig:
    """Resolved token-reduction settings for a single role."""

    enabled: bool


def _truthy(value: str | None, default: bool) -> bool:
    if value is None or not value.strip():
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


def _resolve_compress(role: str, suffix: str) -> str | None:
    prefix = _COMPRESS_ROLE_PREFIX.get(role)
    if prefix:
        value = os.environ.get(prefix + suffix)
        if value is not None and value.strip():
            return value
    return os.environ.get(_COMPRESS_SHARED_PREFIX + suffix)


def compression_config(role: str) -> CompressionConfig:
    """Resolve token-reduction settings for ``role``."""
    load_env()
    return CompressionConfig(enabled=_truthy(_resolve_compress(role, "COMPRESS"), default=True))

