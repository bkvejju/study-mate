"""Step 1 of the workflow: read PDFs and use AI to generate simple, standalone
HTML explainer docs.

Token usage is controlled by a budget: each PDF is split into chunks that fit
within a configurable input-token budget, and one explainer HTML file is
generated per chunk. Files are written incrementally and existing files are
skipped on re-runs, so generation stays cheap and resumable ("as needed").
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path

from . import compress, llm, render
from .extract import DocumentText
from .sections import _split_oversized

# Rough heuristic: ~4 characters per token for English prose.
APPROX_CHARS_PER_TOKEN = 4
# Default input-token budget per AI call (the "headroom"). Keeping each request
# small bounds token usage and makes cost predictable.
DEFAULT_TOKEN_BUDGET = 4000


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


def estimate_tokens(text: str) -> int:
    """Rough input-token estimate for a piece of text."""
    return max(1, len(text) // APPROX_CHARS_PER_TOKEN)


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "doc"


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
                title = page.headings[0] if page.headings else None
            end_page = page.page_number
            buf.append(piece)
            buf_chars += len(piece)
    flush()
    return chunks


def generate_explainers(
    docs: list[DocumentText],
    out_dir: Path,
    token_budget: int = DEFAULT_TOKEN_BUDGET,
    level: str = "intermediate",
    force: bool = False,
    log: Callable[[str], None] = print,
) -> list[Explainer]:
    """Generate one explainer HTML file per chunk across all documents.

    Files are written as they are produced. Existing files are skipped unless
    ``force`` is set, so re-running only generates what is missing.
    """
    explainers_dir = out_dir / "explainers"
    explainers_dir.mkdir(parents=True, exist_ok=True)

    docs_with_text = sum(1 for d in docs if d.has_text)
    log(f"Read {len(docs)} PDF(s); {docs_with_text} with extractable text.")

    total_words = 0
    total_source_tokens = 0
    total_sent_tokens = 0
    total_received_tokens = 0
    generated_count = 0

    manifest: list[Explainer] = []
    for doc in docs:
        if not doc.has_text:
            log(f"  ! {doc.source}: no extractable text (scanned PDF?). Skipped.")
            continue

        chunks = chunk_document(doc, token_budget)
        base = _slug(Path(doc.source).stem)
        for chunk in chunks:
            name = f"{base}-{chunk.index:02d}.html" if len(chunks) > 1 else f"{base}.html"
            path = explainers_dir / name
            entry = Explainer(
                source=doc.source,
                title=chunk.title,
                page_range=chunk.page_range,
                file=name,
                text=chunk.text,
            )
            manifest.append(entry)

            if path.exists() and not force:
                log(f"  = {name}: exists, skipped (use --force to regenerate)")
                continue

            words = len(chunk.text.split())
            source_tokens = estimate_tokens(chunk.text)
            log(f"  + {name}: generating ({words} words, ~{source_tokens} input tokens)\u2026")
            comp = compress.compress_text(chunk.text, role="explainer")
            if comp.applied:
                log(
                    f"    headroom: {comp.tokens_before}\u2192{comp.tokens_after} tokens "
                    f"({comp.savings_percent:.0f}% saved)"
                )
            sent_tokens = estimate_tokens(comp.text)
            doc_html = llm.generate_explainer(chunk.title, comp.text, level)
            received_tokens = estimate_tokens(doc_html)
            log(f"    ~{sent_tokens} tokens sent to LLM \u2192 ~{received_tokens} tokens received")
            path.write_text(doc_html, encoding="utf-8")

            total_words += words
            total_source_tokens += source_tokens
            total_sent_tokens += sent_tokens
            total_received_tokens += received_tokens
            generated_count += 1

    (explainers_dir / "manifest.json").write_text(
        json.dumps(
            [{k: v for k, v in asdict(e).items() if k != "text"} for e in manifest],
            indent=2,
        ),
        encoding="utf-8",
    )
    render.render_explainer_index(manifest, explainers_dir)

    log(
        f"Summary: {generated_count} explainer(s) generated from "
        f"{docs_with_text}/{len(docs)} PDF(s) | "
        f"{total_words:,} words (~{total_source_tokens:,} source tokens) | "
        f"~{total_sent_tokens:,} tokens sent to LLM | "
        f"~{total_received_tokens:,} tokens received"
    )
    return manifest
