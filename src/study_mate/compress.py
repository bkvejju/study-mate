"""Optional token-reduction layer built on the `headroom` library.

This is a small, modular wrapper so the same compression can be applied to any
role — the initial explainer generation now, and the study panel later — via a
single :func:`compress_text` entry point.

Design notes:
- ``headroom-ai`` is an *optional* dependency (install with the ``compress``
  extra). If it is not installed, or a call fails, the original text is returned
  unchanged — compression is always best-effort and never breaks generation.
- Enable/disable per role via config (``STUDYMATE_EXPLAINER_COMPRESS`` /
  ``STUDYMATE_PANEL_COMPRESS`` / shared ``STUDYMATE_COMPRESS``).
- Actual savings depend on the installed headroom extras and the content type;
  prose benefits most from the ``[ml]`` extra (Kompress text model).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from . import config

logger = logging.getLogger(__name__)

# Rough heuristic shared with the chunker: ~4 characters per token.
_APPROX_CHARS_PER_TOKEN = 4

# Headroom logs a WARNING per call when its optional ML model is not installed
# (e.g. "Kompress compression failed: requires onnxruntime or torch"). That is a
# routine, expected condition for us — compression is best-effort — so we quiet
# headroom's logger to ERROR to avoid noise. Genuine errors still surface.
logging.getLogger("headroom").setLevel(logging.ERROR)


@dataclass(frozen=True)
class CompressionResult:
    """Outcome of a (best-effort) compression attempt."""

    text: str
    tokens_before: int
    tokens_after: int
    applied: bool
    detail: str

    @property
    def tokens_saved(self) -> int:
        return max(0, self.tokens_before - self.tokens_after)

    @property
    def savings_percent(self) -> float:
        if self.tokens_before <= 0:
            return 0.0
        return 100.0 * self.tokens_saved / self.tokens_before


def _estimate_tokens(text: str) -> int:
    return max(0, len(text) // _APPROX_CHARS_PER_TOKEN)


def _headroom_compress(text: str) -> str | None:
    """Compress ``text`` with headroom.

    Returns the compressed string, or ``None`` if the library is not installed.
    Raises on unexpected library errors (handled by the caller).
    """
    try:
        from headroom.compression import compress as _compress
    except Exception:
        return None

    result = _compress(text)
    compressed = getattr(result, "compressed", None)
    if isinstance(compressed, str) and compressed.strip():
        return compressed
    return None


def compress_text(text: str, *, role: str = "explainer") -> CompressionResult:
    """Reduce ``text`` token usage for ``role`` before sending it to a model.

    Best-effort: returns the original text unchanged when compression is
    disabled, unavailable, fails, or would not actually save tokens.
    """
    before = _estimate_tokens(text)

    if not text or not text.strip():
        return CompressionResult(text, before, before, applied=False, detail="empty")

    if not config.compression_config(role).enabled:
        return CompressionResult(text, before, before, applied=False, detail="disabled")

    try:
        compressed = _headroom_compress(text)
    except Exception as exc:  # never let compression break generation
        logger.warning("headroom compression failed for role %s: %s", role, exc)
        return CompressionResult(text, before, before, applied=False, detail="error")

    if compressed is None:
        logger.debug("headroom not installed; skipping compression for role %s", role)
        return CompressionResult(text, before, before, applied=False, detail="unavailable")

    after = _estimate_tokens(compressed)
    if after >= before:
        # Compression didn't help (common for already-compact prose) — keep original.
        return CompressionResult(text, before, before, applied=False, detail="no-gain")

    return CompressionResult(compressed, before, after, applied=True, detail="headroom")
