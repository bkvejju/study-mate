"""Step 1 workflow: read notes + exam PDFs and generate standalone explainers.

Token usage is controlled by a budget: each notes PDF is split into chunks that
fit within a configurable input-token budget. For each notes chunk, related
exam-paper snippets are matched and included in the AI prompt so the output is
revision-focused. Files are written incrementally and existing files are
skipped on re-runs, so generation stays cheap and resumable.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path

from . import compress, llm, markdown_export, render
from .extract import DocumentText
from .sections import _split_oversized, split_document_into_chapters

# Rough heuristic: ~4 characters per token for English prose.
APPROX_CHARS_PER_TOKEN = 4
# Default input-token budget per AI call (the "headroom"). Keeping each request
# small bounds token usage and makes cost predictable.
DEFAULT_TOKEN_BUDGET = 4000
DEFAULT_STRATEGY = "chapters"

_NON_TITLE_PATTERNS = (
    re.compile(r"printed by", re.IGNORECASE),
    re.compile(r"private use", re.IGNORECASE),
    re.compile(r"no part of this book", re.IGNORECASE),
    re.compile(r"be reproduced or transmitted", re.IGNORECASE),
    re.compile(r"prior permission", re.IGNORECASE),
    re.compile(r"violators will be prosecuted", re.IGNORECASE),
)


@dataclass
class Chunk:
    """A budget-sized slice of one PDF, fed to a single AI call."""

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


@dataclass
class Explainer:
    """A generated explainer HTML file, referenced by the navigation index."""

    source: str
    title: str
    page_range: str
    file: str  # path relative to the explainers directory
    text: str = ""  # source material for this chunk (panel context; not persisted)


@dataclass
class ExamSnippet:
    """A compact exam-paper excerpt considered during section generation."""

    source: str
    page_number: int
    text: str


@dataclass
class _UnitStats:
    """Outcome of generating (or skipping) one explainer unit."""

    words: int = 0
    source_tokens: int = 0
    sent_tokens: int = 0
    received_tokens: int = 0
    generated: bool = False


def estimate_tokens(text: str) -> int:
    """Rough input-token estimate for a piece of text."""
    return max(1, len(text) // APPROX_CHARS_PER_TOKEN)


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "doc"


def _normalise_spaces(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _is_title_candidate(text: str) -> bool:
    candidate = _normalise_spaces(text)
    if not candidate:
        return False
    if any(pattern.search(candidate) for pattern in _NON_TITLE_PATTERNS):
        return False
    # Keep titles compact and heading-like.
    if len(candidate) > 140 or len(candidate.split()) > 20:
        return False
    return True


def _pick_title(headings: list[str]) -> str | None:
    for heading in headings:
        if _is_title_candidate(heading):
            return _normalise_spaces(heading)
    return None


def _keyword_set(text: str) -> set[str]:
    stop = {
        "about",
        "after",
        "again",
        "below",
        "being",
        "could",
        "every",
        "first",
        "from",
        "have",
        "into",
        "just",
        "like",
        "more",
        "most",
        "other",
        "over",
        "same",
        "some",
        "such",
        "than",
        "that",
        "their",
        "there",
        "these",
        "they",
        "this",
        "through",
        "under",
        "very",
        "what",
        "when",
        "which",
        "while",
        "with",
        "would",
    }
    words = set(re.findall(r"[a-z0-9]{4,}", text.lower()))
    return {w for w in words if w not in stop}


def _exam_snippets_for_course(docs: list[DocumentText], course_key: str) -> list[ExamSnippet]:
    snippets: list[ExamSnippet] = []
    for doc in docs:
        if doc.course_key != course_key:
            continue
        for page in doc.pages:
            if not page.text.strip():
                continue
            snippets.append(
                ExamSnippet(
                    source=doc.source,
                    page_number=page.page_number,
                    text=_normalise_spaces(page.text),
                )
            )
    return snippets


def _exam_snippets_from_markdown(
    docs: list[markdown_export.ParsedMarkdownDocument], course_key: str
) -> list[ExamSnippet]:
    """Like :func:`_exam_snippets_for_course`, but over markdown-derived exam
    chapters (chapter-level granularity, since per-page text isn't preserved
    once exported to markdown)."""
    snippets: list[ExamSnippet] = []
    for doc in docs:
        if doc.course_key != course_key:
            continue
        for chapter in doc.chapters:
            if not chapter.text.strip():
                continue
            snippets.append(
                ExamSnippet(
                    source=doc.source,
                    page_number=chapter.page_start,
                    text=_normalise_spaces(chapter.text),
                )
            )
    return snippets


def _match_exam_snippets(section_text: str, snippets: list[ExamSnippet], limit: int = 3) -> list[str]:
    """Pick the most relevant exam snippets for a notes section via keyword overlap."""
    section_words = _keyword_set(section_text)
    if not section_words or not snippets:
        return []

    scored: list[tuple[int, ExamSnippet]] = []
    for snippet in snippets:
        overlap = len(section_words & _keyword_set(snippet.text))
        if overlap > 0:
            scored.append((overlap, snippet))
    scored.sort(key=lambda t: t[0], reverse=True)

    selected: list[str] = []
    for _score, snippet in scored[:limit]:
        preview = snippet.text[:320].strip()
        selected.append(f"{snippet.source} p.{snippet.page_number}: {preview}")
    return selected


def chunk_document(doc: DocumentText, token_budget: int = DEFAULT_TOKEN_BUDGET) -> list[Chunk]:
    """Split a document into chunks that each fit within the token budget.

    Pages are accumulated until adding the next page would exceed the budget; a
    single oversized page is paragraph-split first. No AI is involved here.
    """
    budget_chars = max(1, token_budget) * APPROX_CHARS_PER_TOKEN
    chunks: list[Chunk] = []
    buf: list[str] = []
    buf_chars = 0
    start_page: int | None = None
    end_page: int | None = None
    title: str | None = None

    def flush() -> None:
        nonlocal buf, buf_chars, start_page, end_page, title
        body = "\n".join(buf).strip()
        if body and start_page is not None and end_page is not None:
            idx = len(chunks) + 1
            chunks.append(
                Chunk(
                    source=doc.source,
                    index=idx,
                    title=title or f"{doc.source} \u2014 Part {idx}",
                    page_start=start_page,
                    page_end=end_page,
                    text=body,
                )
            )
        buf = []
        buf_chars = 0
        start_page = None
        end_page = None
        title = None

    for page in doc.pages:
        text = page.text.strip()
        if not text:
            continue
        pieces = _split_oversized(text, budget_chars) if len(text) > budget_chars else [text]
        for piece in pieces:
            if buf_chars and buf_chars + len(piece) > budget_chars:
                flush()
            if start_page is None:
                start_page = page.page_number
                title = _pick_title(page.headings)
            end_page = page.page_number
            buf.append(piece)
            buf_chars += len(piece)
    flush()
    return chunks


def _generate_explainer_unit(
    chunk: Chunk,
    name: str,
    explainers_dir: Path,
    level: str,
    force: bool,
    log: Callable[[str], None],
    course_exam_snippets: list[ExamSnippet],
) -> tuple[Explainer, _UnitStats]:
    """Generate (or skip, if already on disk) one explainer file for ``chunk``.

    Shared by both the PDF-driven and markdown-driven entry points.
    """
    path = explainers_dir / name
    entry = Explainer(
        source=chunk.source,
        title=chunk.title,
        page_range=chunk.page_range,
        file=name,
        text=chunk.text,
    )

    if path.exists() and not force:
        log(f"  = {name}: exists, skipped (use --force to regenerate)")
        return entry, _UnitStats()

    words = len(chunk.text.split())
    source_tokens = estimate_tokens(chunk.text)
    log(f"  + {name}: generating ({words} words, ~{source_tokens} input tokens)...")
    comp = compress.compress_text(chunk.text, role="explainer")
    if comp.applied:
        log(
            f"    headroom: {comp.tokens_before}->{comp.tokens_after} tokens "
            f"({comp.savings_percent:.0f}% saved)"
        )
    sent_tokens = estimate_tokens(comp.text)

    matched_exam = _match_exam_snippets(chunk.text, course_exam_snippets)
    if matched_exam:
        log(f"    matched {len(matched_exam)} related exam snippet(s)")
    else:
        log("    no strong exam match found; using notes-only exam guidance")

    doc_html = llm.generate_explainer(chunk.title, comp.text, level, exam_snippets=matched_exam)
    received_tokens = estimate_tokens(doc_html)
    log(f"    ~{sent_tokens} tokens sent to LLM -> ~{received_tokens} tokens received")
    path.write_text(doc_html, encoding="utf-8")

    return entry, _UnitStats(
        words=words,
        source_tokens=source_tokens,
        sent_tokens=sent_tokens,
        received_tokens=received_tokens,
        generated=True,
    )


def _write_manifest_and_index(manifest: list[Explainer], explainers_dir: Path) -> None:
    (explainers_dir / "manifest.json").write_text(
        json.dumps(
            [{k: v for k, v in asdict(e).items() if k != "text"} for e in manifest],
            indent=2,
        ),
        encoding="utf-8",
    )
    render.render_explainer_index(manifest, explainers_dir)


def generate_explainers_from_markdown(
    markdown_dir: Path,
    out_dir: Path,
    level: str = "intermediate",
    force: bool = False,
    log: Callable[[str], None] = print,
) -> list[Explainer]:
    """Generate explainers directly from previously-exported markdown
    (``study-mate extract-markdown``), skipping PDF re-extraction entirely.

    Markdown only preserves chapter-level granularity (see
    :func:`markdown_export.parse_markdown_document`), so this always behaves
    like ``--strategy chapters``.
    """
    explainers_dir = out_dir / "explainers"
    explainers_dir.mkdir(parents=True, exist_ok=True)

    note_docs = markdown_export.load_markdown_documents(markdown_dir, kind="note")
    exam_docs = markdown_export.load_markdown_documents(markdown_dir, kind="exam")
    log(
        f"Loaded {len(note_docs)} notes markdown doc(s) and {len(exam_docs)} exam markdown doc(s) "
        f"from {markdown_dir}"
    )

    manifest: list[Explainer] = []
    total_words = total_source_tokens = total_sent_tokens = total_received_tokens = 0
    generated_count = 0

    for doc in note_docs:
        if not doc.chapters:
            log(f"  ! {doc.source}: no chapters found in markdown. Skipped.")
            continue

        course_key = doc.course_key or _slug(Path(doc.source).stem)
        course_exam_snippets = _exam_snippets_from_markdown(exam_docs, course_key)
        base = _slug(Path(doc.source).stem)

        chunks = [
            Chunk(
                source=doc.source,
                index=chapter.index,
                title=chapter.title,
                page_start=chapter.page_start,
                page_end=chapter.page_end,
                text=chapter.text,
            )
            for chapter in doc.chapters
        ]
        for chunk in chunks:
            name = f"{base}-chapter-{chunk.index:02d}.html" if len(chunks) > 1 else f"{base}.html"
            entry, stats = _generate_explainer_unit(
                chunk, name, explainers_dir, level, force, log, course_exam_snippets
            )
            manifest.append(entry)
            if stats.generated:
                total_words += stats.words
                total_source_tokens += stats.source_tokens
                total_sent_tokens += stats.sent_tokens
                total_received_tokens += stats.received_tokens
                generated_count += 1

    _write_manifest_and_index(manifest, explainers_dir)

    log(
        f"Summary: {generated_count} explainer(s) generated from markdown | "
        f"{len(note_docs)} note doc(s) | ~{total_words:,} words (~{total_source_tokens:,} source tokens) | "
        f"~{total_sent_tokens:,} tokens sent to LLM | ~{total_received_tokens:,} tokens received"
    )
    return manifest


def generate_explainers(
    notes_docs: list[DocumentText],
    out_dir: Path,
    exam_docs: list[DocumentText] | None = None,
    token_budget: int = DEFAULT_TOKEN_BUDGET,
    level: str = "intermediate",
    strategy: str = DEFAULT_STRATEGY,
    force: bool = False,
    log: Callable[[str], None] = print,
) -> list[Explainer]:
    """Generate one exam-oriented explainer per notes section.

    Notes are chunked by token budget to create section-level explainers. Related
    exam-paper snippets are matched to each notes section and included in the AI
    prompt to keep output revision-focused.
    """
    explainers_dir = out_dir / "explainers"
    explainers_dir.mkdir(parents=True, exist_ok=True)

    exam_docs = exam_docs or []
    notes_with_text = sum(1 for d in notes_docs if d.has_text)
    exams_with_text = sum(1 for d in exam_docs if d.has_text)
    log(
        f"Read {len(notes_docs)} notes PDF(s); {notes_with_text} with extractable text. "
        f"Read {len(exam_docs)} exam PDF(s); {exams_with_text} with extractable text."
    )

    total_words = 0
    total_source_tokens = 0
    total_sent_tokens = 0
    total_received_tokens = 0
    generated_count = 0

    if strategy not in {"sections", "chapters"}:
        raise ValueError("strategy must be one of: sections, chapters")

    # Deterministic extraction artifact for inspection/debugging, regardless of
    # strategy. Both kinds are exported so --from-markdown can later regenerate
    # explainers (including exam-snippet matching) without re-reading the PDFs.
    markdown_export.export_markdown_documents(notes_docs, out_dir)
    markdown_export.export_markdown_documents(exam_docs, out_dir)

    manifest: list[Explainer] = []
    for doc in notes_docs:
        if not doc.has_text:
            log(f"  ! {doc.source}: no extractable text (scanned PDF?). Skipped.")
            continue

        if strategy == "chapters":
            chapter_units = split_document_into_chapters(doc)
            chunks = [
                Chunk(
                    source=doc.source,
                    index=chapter.index,
                    title=chapter.title,
                    page_start=chapter.page_start,
                    page_end=chapter.page_end,
                    text=chapter.text,
                )
                for chapter in chapter_units
            ]
        else:
            chunks = chunk_document(doc, token_budget)

        course_key = doc.course_key or _slug(Path(doc.source).stem)
        course_exam_snippets = _exam_snippets_for_course(exam_docs, course_key)
        base = _slug(Path(doc.source).stem)
        for chunk in chunks:
            unit_name = "chapter" if strategy == "chapters" else "section"
            name = f"{base}-{unit_name}-{chunk.index:02d}.html" if len(chunks) > 1 else f"{base}.html"
            entry, stats = _generate_explainer_unit(
                chunk, name, explainers_dir, level, force, log, course_exam_snippets
            )
            manifest.append(entry)
            if stats.generated:
                total_words += stats.words
                total_source_tokens += stats.source_tokens
                total_sent_tokens += stats.sent_tokens
                total_received_tokens += stats.received_tokens
                generated_count += 1

    _write_manifest_and_index(manifest, explainers_dir)

    log(
        f"Summary: {generated_count} explainer(s) generated with strategy={strategy} from "
        f"{notes_with_text}/{len(notes_docs)} note PDF(s) | "
        f"~{total_words:,} words (~{total_source_tokens:,} source tokens) | "
        f"~{total_sent_tokens:,} tokens sent to LLM | "
        f"~{total_received_tokens:,} tokens received"
    )
    return manifest
