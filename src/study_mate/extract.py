"""Extract text and metadata from PDFs. No AI involved."""

from __future__ import annotations

from dataclasses import dataclass, field
import os
from pathlib import Path
import re

try:
    import fitz  # PyMuPDF
except ImportError:  # pragma: no cover - import guard
    fitz = None


_NON_STUDY_LINE_PATTERNS = (
    re.compile(r"^\s*printed by\s*:", re.IGNORECASE),
    re.compile(r"^\s*printing is for personal,? private use only", re.IGNORECASE),
    re.compile(r"^\s*no part of this book may", re.IGNORECASE),
    re.compile(r"^\s*be reproduced or transmitted without .*prior permission", re.IGNORECASE),
    re.compile(r"^\s*violators will be prosecuted", re.IGNORECASE),
)


def _bool_env(name: str, default: bool = True) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() not in {"0", "false", "no", "off"}


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
    source_path: str = ""
    kind: str = "note"  # note | exam
    course_key: str = ""

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


def _strip_non_study_boilerplate(text: str) -> str:
    """Drop known copyright/private-use boilerplate from extracted PDF text."""
    kept_lines: list[str] = []
    for line in text.splitlines():
        if any(pattern.search(line) for pattern in _NON_STUDY_LINE_PATTERNS):
            continue
        kept_lines.append(line)
    cleaned = "\n".join(kept_lines)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def _extract_page_ocr_text(page) -> str:
    """Run OCR for a page when enabled and available."""
    if not _bool_env("STUDYMATE_ENABLE_OCR", default=True):
        return ""

    ocr_fn = getattr(page, "get_textpage_ocr", None)
    if not callable(ocr_fn):
        return ""

    ocr_lang = os.environ.get("STUDYMATE_OCR_LANG", "eng")
    ocr_dpi = int(os.environ.get("STUDYMATE_OCR_DPI", "300"))
    try:
        text_page = ocr_fn(language=ocr_lang, dpi=ocr_dpi)
        return page.get_text("text", textpage=text_page).strip()
    except Exception:
        return ""


def _extract_page_text(page) -> str:
    """Extract text from a page with OCR fallback after sanitization."""
    native = _strip_non_study_boilerplate(page.get_text("text").strip())
    if native:
        return native
    return _strip_non_study_boilerplate(_extract_page_ocr_text(page))


def extract_pdf(path: Path) -> DocumentText:
    """Extract text from a single PDF file."""
    if fitz is None:  # pragma: no cover - exercised only without dependency
        raise RuntimeError("PyMuPDF (pymupdf) is required. Run `uv sync`.")

    pages: list[PageText] = []
    with fitz.open(path) as doc:
        for index, page in enumerate(doc, start=1):
            text = _extract_page_text(page)
            pages.append(
                PageText(
                    page_number=index,
                    text=text,
                    headings=_page_headings(page) if text else [],
                )
            )
    return DocumentText(source=path.name, pages=pages, source_path=str(path))


def _course_key_from_filename(name: str) -> str:
    """Infer a stable grouping key from a PDF filename.

    Examples:
    - sp2-pg-1-100.pdf -> sp2
    - SP2_Exam_1.pdf -> sp2
    """
    stem = Path(name).stem.lower()
    tokens = [t for t in re.split(r"[^a-z0-9]+", stem) if t]
    if not tokens:
        return "unknown"

    for token in tokens:
        if re.fullmatch(r"[a-z]+\d+", token):
            return token
    return tokens[0]


def extract_pdf_set(root: Path, kind: str) -> list[DocumentText]:
    """Extract all PDFs under a root directory (recursive).

    Returned documents are annotated with their source kind and inferred
    course key so the explainer pipeline can pair notes with exam papers.
    """
    pdfs = sorted(root.rglob("*.pdf")) if root.exists() else []
    docs: list[DocumentText] = []
    for pdf in pdfs:
        doc = extract_pdf(pdf)
        doc.kind = kind
        doc.course_key = _course_key_from_filename(pdf.name)
        try:
            doc.source_path = str(pdf.relative_to(root))
        except ValueError:
            doc.source_path = str(pdf)
        docs.append(doc)
    return docs


def extract_material_sets(notes_dir: Path, exam_papers_dir: Path) -> tuple[list[DocumentText], list[DocumentText]]:
    """Extract notes and exam papers from their dedicated folders."""
    notes = extract_pdf_set(notes_dir, kind="note")
    exams = extract_pdf_set(exam_papers_dir, kind="exam")
    return notes, exams


def extract_dir(materials_dir: Path) -> list[DocumentText]:
    """Extract every PDF in a directory, sorted by filename."""
    pdfs = sorted(materials_dir.glob("*.pdf"))
    return [extract_pdf(pdf) for pdf in pdfs]
