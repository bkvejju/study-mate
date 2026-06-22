"""Deterministic markdown export for extracted study documents."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .extract import DocumentText
from .sections import ChapterSection, split_document_into_chapters

_FRONTMATTER_RE = re.compile(r"\A---\n(?P<meta>.*?)\n---\n", re.DOTALL)
_CHAPTER_HEADER_RE = re.compile(
    r"^## (?P<title>.+)\n<!-- study-mate:chapter page_start=(?P<start>\d+) page_end=(?P<end>\d+) -->\n",
    re.MULTILINE,
)


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


@dataclass
class ParsedMarkdownDocument:
    """A document reconstructed from a markdown file written by
    :func:`document_to_markdown`, for regenerating explainers without
    re-parsing the source PDF."""

    source: str
    kind: str
    course_key: str
    chapters: list[ChapterSection]


def parse_markdown_document(path: Path) -> ParsedMarkdownDocument:
    """Parse a markdown file written by :func:`document_to_markdown` back into
    chapter sections. The inverse of ``document_to_markdown`` for the fields
    the explainer pipeline needs (source, kind, course_key, chapters)."""
    raw = path.read_text(encoding="utf-8")

    meta: dict[str, str] = {}
    fm_match = _FRONTMATTER_RE.match(raw)
    if fm_match:
        for line in fm_match.group("meta").splitlines():
            key, _, value = line.partition(":")
            if key.strip():
                meta[key.strip()] = value.strip()

    source = meta.get("source", path.stem)
    headers = list(_CHAPTER_HEADER_RE.finditer(raw))
    chapters: list[ChapterSection] = []
    for i, match in enumerate(headers):
        body_end = headers[i + 1].start() if i + 1 < len(headers) else len(raw)
        chapters.append(
            ChapterSection(
                source=source,
                index=i + 1,
                title=match.group("title").strip(),
                page_start=int(match.group("start")),
                page_end=int(match.group("end")),
                text=raw[match.end() : body_end].strip(),
            )
        )

    return ParsedMarkdownDocument(
        source=source,
        kind=meta.get("kind", "note"),
        course_key=meta.get("course_key", ""),
        chapters=chapters,
    )


def load_markdown_documents(markdown_dir: Path, kind: str) -> list[ParsedMarkdownDocument]:
    """Load every previously-exported markdown document of a given ``kind``
    (``"note"`` or ``"exam"``) from ``markdown_dir``, sorted by filename."""
    paths = sorted(markdown_dir.glob(f"*-{kind}.md"))
    return [parse_markdown_document(p) for p in paths]


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
