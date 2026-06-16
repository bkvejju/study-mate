"""Extract text and metadata from PDFs. No AI involved."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

try:
    import fitz  # PyMuPDF
except ImportError:  # pragma: no cover - import guard
    fitz = None


@dataclass
class PageText:
    """Text extracted from a single PDF page."""

    page_number: int
    text: str
    # Heading-like lines detected by font size (largest spans on the page).
    headings: list[str] = field(default_factory=list)


@dataclass
class DocumentText:
    """All extracted text for one PDF file."""

    source: str
    pages: list[PageText]

    @property
    def has_text(self) -> bool:
        return any(page.text.strip() for page in self.pages)


def _page_headings(page) -> list[str]:
    """Return heading-like lines based on relative font size."""
    data = page.get_text("dict")
    sizes: list[tuple[float, str]] = []
    for block in data.get("blocks", []):
        for line in block.get("lines", []):
            spans = line.get("spans", [])
            if not spans:
                continue
            line_text = "".join(span.get("text", "") for span in spans).strip()
            if not line_text:
                continue
            max_size = max(span.get("size", 0) for span in spans)
            sizes.append((max_size, line_text))

    if not sizes:
        return []

    largest = max(size for size, _ in sizes)
    # Treat noticeably-larger, short lines as headings.
    return [
        text
        for size, text in sizes
        if size >= largest * 0.92 and len(text) <= 120 and len(text.split()) <= 14
    ]


def extract_pdf(path: Path) -> DocumentText:
    """Extract text from a single PDF file."""
    if fitz is None:  # pragma: no cover - exercised only without dependency
        raise RuntimeError("PyMuPDF (pymupdf) is required. Run `uv sync`.")

    pages: list[PageText] = []
    with fitz.open(path) as doc:
        for index, page in enumerate(doc, start=1):
            text = page.get_text("text").strip()
            pages.append(
                PageText(
                    page_number=index,
                    text=text,
                    headings=_page_headings(page) if text else [],
                )
            )
    return DocumentText(source=path.name, pages=pages)


def extract_dir(materials_dir: Path) -> list[DocumentText]:
    """Extract every PDF in a directory, sorted by filename."""
    pdfs = sorted(materials_dir.glob("*.pdf"))
    return [extract_pdf(pdf) for pdf in pdfs]
