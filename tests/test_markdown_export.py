"""Tests for deterministic markdown export artifacts."""

from pathlib import Path

from study_mate.extract import DocumentText, PageText
from study_mate.markdown_export import document_to_markdown, export_markdown_documents


def _doc(source: str, kind: str = "note") -> DocumentText:
    return DocumentText(
        source=source,
        kind=kind,
        course_key="sp2",
        pages=[
            PageText(page_number=1, text="intro", headings=["Part 1 Overview"]),
            PageText(page_number=2, text="pricing", headings=["Chapter 2 Pricing"]),
        ],
    )


def test_document_to_markdown_is_deterministic():
    doc = _doc("sp2.pdf")
    first = document_to_markdown(doc)
    second = document_to_markdown(doc)
    assert first == second
    assert "source: sp2.pdf" in first
    assert "## Part 1 Overview" in first
    assert "page_start=1 page_end=1" in first


def test_export_markdown_documents_writes_kind_suffix(tmp_path: Path):
    note = _doc("sp2.pdf", kind="note")
    exam = _doc("sp2.pdf", kind="exam")

    paths = export_markdown_documents([note, exam], tmp_path)

    names = sorted(p.name for p in paths)
    assert names == ["sp2-exam.md", "sp2-note.md"]
    for p in paths:
        assert p.exists()
        assert p.read_text(encoding="utf-8").startswith("---\n")
