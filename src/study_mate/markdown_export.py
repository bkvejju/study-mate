"""Deterministic markdown export for extracted study documents."""

from __future__ import annotations

import re
from pathlib import Path

from .extract import DocumentText
from .sections import ChapterSection, split_document_into_chapters


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "doc"


def chapter_to_markdown(chapter: ChapterSection) -> str:
    return (
        f"## {chapter.title}\n"
        f"<!-- study-mate:chapter page_start={chapter.page_start} page_end={chapter.page_end} -->\n\n"
        f"{chapter.text.strip()}\n"
    )


def document_to_markdown(doc: DocumentText) -> str:
    """Export one extracted PDF document to deterministic markdown."""
    chapters = split_document_into_chapters(doc)
    lines = [
        "---",
        f"source: {doc.source}",
        f"kind: {doc.kind}",
        f"course_key: {doc.course_key}",
        f"chapters: {len(chapters)}",
        "---",
        "",
        f"# {doc.source}",
        "",
    ]
    for chapter in chapters:
        lines.append(chapter_to_markdown(chapter).rstrip())
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def export_markdown_documents(docs: list[DocumentText], out_dir: Path) -> list[Path]:
    """Write markdown files for a set of extracted documents.

    Files are written under ``out_dir/markdown`` and returned in source order.
    """
    markdown_dir = out_dir / "markdown"
    markdown_dir.mkdir(parents=True, exist_ok=True)

    written: list[Path] = []
    for doc in docs:
        base = _slug(Path(doc.source).stem)
        kind = _slug(doc.kind or "doc")
        path = markdown_dir / f"{base}-{kind}.md"
        path.write_text(document_to_markdown(doc), encoding="utf-8")
        written.append(path)
    return written
