"""Tests for the text-splitting utilities used by the explainer chunker."""

from study_mate.extract import DocumentText, PageText
from study_mate.sections import _split_oversized, split_document_into_chapters


def test_short_text_is_unchanged():
    assert _split_oversized("hello world", 100) == ["hello world"]


def test_splits_on_paragraph_boundaries():
    text = "para one\n\npara two\n\npara three"
    chunks = _split_oversized(text, max_chars=12)
    assert len(chunks) > 1


def test_oversized_single_paragraph_is_word_split():
    big = "word " * 4000  # ~20000 chars, one paragraph
    chunks = _split_oversized(big, max_chars=6000)
    assert len(chunks) > 1
    assert all(len(c) <= 6000 for c in chunks)


def test_returns_all_content():
    text = "alpha\n\nbeta\n\ngamma"
    chunks = _split_oversized(text, max_chars=8)
    joined = " ".join(chunks)
    for word in ("alpha", "beta", "gamma"):
        assert word in joined


def test_split_document_into_chapters_by_heading_boundaries():
    doc = DocumentText(
        source="sp2.pdf",
        pages=[
            PageText(page_number=1, text="intro text", headings=["Part 1 Overview"]),
            PageText(page_number=2, text="still part 1", headings=[]),
            PageText(page_number=3, text="chapter 2 text", headings=["Chapter 2 Pricing"]),
        ],
    )
    chapters = split_document_into_chapters(doc)

    assert len(chapters) == 2
    assert chapters[0].title == "Part 1 Overview"
    assert chapters[0].page_range == "pp.1-2"
    assert chapters[1].title == "Chapter 2 Pricing"
    assert chapters[1].page_range == "p.3"


def test_split_document_into_chapters_fallback_title_when_no_heading():
    doc = DocumentText(
        source="sp2.pdf",
        pages=[
            PageText(page_number=1, text="alpha", headings=[]),
            PageText(page_number=2, text="beta", headings=[]),
        ],
    )
    chapters = split_document_into_chapters(doc)

    assert len(chapters) == 1
    assert chapters[0].title == "sp2.pdf - Chapter 1"

