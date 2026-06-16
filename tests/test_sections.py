"""Tests for the text-splitting utilities used by the explainer chunker."""

from study_mate.sections import _split_oversized


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

