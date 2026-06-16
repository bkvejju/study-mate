"""Tests for the explainer step: chunking by token budget and stub generation."""

from study_mate import explain, llm
from study_mate.extract import DocumentText, PageText


def _doc(pages, source="test.pdf"):
    return DocumentText(
        source=source,
        pages=[
            PageText(page_number=i + 1, text=text, headings=heads)
            for i, (text, heads) in enumerate(pages)
        ],
    )


def test_chunks_respect_token_budget():
    big = "word " * 4000  # ~20000 chars
    doc = _doc([("BIG\n" + big, ["BIG"])])
    chunks = explain.chunk_document(doc, token_budget=1000)  # ~4000 chars
    assert len(chunks) > 1
    assert all(len(c.text) <= 1000 * explain.APPROX_CHARS_PER_TOKEN + 50 for c in chunks)


def test_chunk_uses_heading_as_title_and_tracks_pages():
    doc = _doc([("OVERVIEW\nbody", ["OVERVIEW"]), ("more body", [])])
    chunks = explain.chunk_document(doc, token_budget=4000)
    assert len(chunks) == 1
    assert chunks[0].title == "OVERVIEW"
    assert chunks[0].page_start == 1
    assert chunks[0].page_end == 2
    assert chunks[0].page_range == "pp.1-2"


def test_stub_explainer_is_full_html_document(monkeypatch):
    monkeypatch.setenv("STUDYMATE_AI_PROVIDER", "stub")
    out = llm.generate_explainer("Photosynthesis", "light to energy")
    assert out.startswith("<!DOCTYPE html>")
    assert "</html>" in out
    assert "Photosynthesis" in out


def test_generate_explainers_writes_files_and_index(tmp_path, monkeypatch):
    monkeypatch.setenv("STUDYMATE_AI_PROVIDER", "stub")
    docs = [_doc([("ALPHA\nbody", ["ALPHA"])], source="a.pdf")]
    manifest = explain.generate_explainers(docs, tmp_path, log=lambda _msg: None)

    assert len(manifest) == 1
    explainers_dir = tmp_path / "explainers"
    assert (explainers_dir / manifest[0].file).exists()
    assert (explainers_dir / "index.html").exists()
    assert (explainers_dir / "manifest.json").exists()


def test_existing_files_skipped_without_force(tmp_path, monkeypatch):
    monkeypatch.setenv("STUDYMATE_AI_PROVIDER", "stub")
    docs = [_doc([("ALPHA\nbody", ["ALPHA"])], source="a.pdf")]
    manifest = explain.generate_explainers(docs, tmp_path, log=lambda _msg: None)
    target = tmp_path / "explainers" / manifest[0].file

    target.write_text("SENTINEL", encoding="utf-8")
    explain.generate_explainers(docs, tmp_path, log=lambda _msg: None)
    assert target.read_text(encoding="utf-8") == "SENTINEL"  # not regenerated

    explain.generate_explainers(docs, tmp_path, force=True, log=lambda _msg: None)
    assert target.read_text(encoding="utf-8") != "SENTINEL"  # regenerated


def test_scanned_pdf_skipped(tmp_path, monkeypatch):
    monkeypatch.setenv("STUDYMATE_AI_PROVIDER", "stub")
    docs = [_doc([("", [])], source="scan.pdf")]
    manifest = explain.generate_explainers(docs, tmp_path, log=lambda _msg: None)
    assert manifest == []
