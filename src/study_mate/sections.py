"""Text-splitting utilities used to keep AI input chunks within budget.

These helpers split a block of text on paragraph, then word, boundaries so a
chunk never exceeds a character budget. Used by the explainer chunker; no AI.
"""

from __future__ import annotations

import re


def _hard_split(text: str, max_chars: int) -> list[str]:
    """Last-resort split on word boundaries when a block has no paragraphs."""
    words = text.split(" ")
    chunks: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip() if current else word
        if len(candidate) > max_chars and current:
            chunks.append(current)
            current = word
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks or [text]


def _split_oversized(text: str, max_chars: int) -> list[str]:
    """Split a too-long block on paragraph boundaries, then words if needed."""
    if len(text) <= max_chars:
        return [text]
    paragraphs = re.split(r"\n\s*\n", text)
    chunks: list[str] = []
    current = ""
    for para in paragraphs:
        candidate = f"{current}\n\n{para}".strip() if current else para
        if len(candidate) > max_chars and current:
            chunks.append(current.strip())
            current = para
        else:
            current = candidate
    if current.strip():
        chunks.append(current.strip())

    # Any chunk still oversized (a single huge paragraph) gets hard-split.
    final: list[str] = []
    for chunk in chunks or [text]:
        if len(chunk) > max_chars:
            final.extend(_hard_split(chunk, max_chars))
        else:
            final.append(chunk)
    return final

