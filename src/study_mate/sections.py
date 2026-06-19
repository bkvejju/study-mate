"""Text-splitting utilities used to keep AI input chunks within budget.

These helpers split a block of text on paragraph, then word, boundaries so a
chunk never exceeds a character budget. They also provide chapter segmentation
helpers used by chapter-first explainer generation; no AI.
"""

from __future__ import annotations

from dataclasses import dataclass
import re

from .extract import DocumentText


@dataclass
class ChapterSection:
    """A chapter-like segment from one source document."""

    source: str
    index: int
    title: str
    page_start: int
    page_end: int
    text: str

    @property
    def page_range(self) -> str:
        if self.page_start == self.page_end:
            return f"p.{self.page_start}"
        return f"pp.{self.page_start}-{self.page_end}"


_NON_HEADING_PATTERNS = (
    re.compile(r"printed by", re.IGNORECASE),
    re.compile(r"private use", re.IGNORECASE),
    re.compile(r"no part of this book", re.IGNORECASE),
    re.compile(r"be reproduced or transmitted", re.IGNORECASE),
    re.compile(r"prior permission", re.IGNORECASE),
    re.compile(r"violators will be prosecuted", re.IGNORECASE),
)


def _normalise_spaces(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _is_heading_noise(text: str) -> bool:
    candidate = _normalise_spaces(text)
    if not candidate:
        return True
    if len(candidate) > 160 or len(candidate.split()) > 24:
        return True
    return any(pattern.search(candidate) for pattern in _NON_HEADING_PATTERNS)


def _chapter_heading_score(text: str) -> int:
    """Return a confidence score for chapter-like headings.

    Higher score means more likely to be a chapter boundary.
    """
    heading = _normalise_spaces(text)
    if not heading or _is_heading_noise(heading):
        return 0
    lower = heading.lower()
    score = 0
    if re.search(r"\bchapter\b", lower):
        score += 4
    if re.search(r"\bpart\b", lower):
        score += 3
    if re.match(r"^(\d+|[ivxlcdm]+)[\.)\-:]\s+", lower):
        score += 3
    if re.match(r"^\d+(\.\d+)+\s+", lower):
        score += 2
    if 2 <= len(heading.split()) <= 12:
        score += 1
    return score


def _pick_page_heading(headings: list[str]) -> str | None:
    candidates = [h for h in headings if not _is_heading_noise(h)]
    if not candidates:
        return None
    # Prefer chapter-like headings. Fallback to first clean heading.
    ranked = sorted(candidates, key=_chapter_heading_score, reverse=True)
    return _normalise_spaces(ranked[0])


def split_document_into_chapters(doc: DocumentText) -> list[ChapterSection]:
    """Split a document into chapter-like segments based on heading boundaries."""
    chunks: list[ChapterSection] = []
    buf: list[str] = []
    current_title: str | None = None
    start_page: int | None = None
    end_page: int | None = None

    def flush() -> None:
        nonlocal buf, current_title, start_page, end_page
        body = "\n\n".join(part.strip() for part in buf if part.strip()).strip()
        if body and start_page is not None and end_page is not None:
            idx = len(chunks) + 1
            chunks.append(
                ChapterSection(
                    source=doc.source,
                    index=idx,
                    title=current_title or f"{doc.source} - Chapter {idx}",
                    page_start=start_page,
                    page_end=end_page,
                    text=body,
                )
            )
        buf = []
        current_title = None
        start_page = None
        end_page = None

    for page in doc.pages:
        text = page.text.strip()
        if not text:
            continue

        heading = _pick_page_heading(page.headings)
        heading_score = _chapter_heading_score(heading or "")
        if heading and heading_score >= 3 and buf:
            flush()

        if start_page is None:
            start_page = page.page_number
            current_title = heading or current_title
        end_page = page.page_number

        # Allow improving title on early pages if a better heading appears.
        if heading and (current_title is None or _chapter_heading_score(current_title) < heading_score):
            current_title = heading

        buf.append(text)

    flush()
    return chunks


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

