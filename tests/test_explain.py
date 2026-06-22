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


def test_chunk_ignores_copyright_heading_and_falls_back_title():
    bad = "be reproduced or transmitted without publisher's prior permission. Violators will be prosecuted."
    doc = _doc([("body", [bad])], source="sp2.pdf")
    chunks = explain.chunk_document(doc, token_budget=4000)

    assert len(chunks) == 1
    assert chunks[0].title == "sp2.pdf — Part 1"


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


def test_generate_explainers_chapter_strategy_writes_chapter_files(tmp_path, monkeypatch):
    monkeypatch.setenv("STUDYMATE_AI_PROVIDER", "stub")
    docs = [
        _doc(
            [
                ("intro", ["Part 1 Overview"]),
                ("pricing", ["Chapter 2 Pricing"]),
            ],
            source="a.pdf",
        )
    ]

    manifest = explain.generate_explainers(docs, tmp_path, strategy="chapters", log=lambda _msg: None)

    assert len(manifest) == 2
    assert manifest[0].file == "a-chapter-01.html"
    assert manifest[1].file == "a-chapter-02.html"
    assert (tmp_path / "markdown" / "a-note.md").exists()


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


def test_exam_snippets_are_matched_by_course(monkeypatch):
    notes = _doc(
        [("KINETIC ENERGY and momentum are central ideas", ["Mechanics"])],
        source="sp2-notes.pdf",
    )
    notes.course_key = "sp2"
    exams = [
        _doc([("This question tests kinetic energy in moving systems", [])], source="sp2-exam.pdf"),
        _doc([("Cell structure and osmosis", [])], source="bio1-exam.pdf"),
    ]
    exams[0].course_key = "sp2"
    exams[1].course_key = "bio1"

    snippets = explain._exam_snippets_for_course(exams, "sp2")
    matched = explain._match_exam_snippets(notes.pages[0].text, snippets)

    assert len(matched) == 1
    assert "sp2-exam.pdf" in matched[0]


def test_generate_explainers_from_markdown_writes_files_and_index(tmp_path, monkeypatch):
    monkeypatch.setenv("STUDYMATE_AI_PROVIDER", "stub")
    docs = [_doc([("ALPHA\nbody", ["ALPHA"])], source="a.pdf")]
    explain.generate_explainers(docs, tmp_path, strategy="chapters", log=lambda _msg: None)

    manifest = explain.generate_explainers_from_markdown(
        tmp_path / "markdown", tmp_path, log=lambda _msg: None
    )

    assert len(manifest) == 1
    explainers_dir = tmp_path / "explainers"
    assert (explainers_dir / manifest[0].file).exists()
    assert (explainers_dir / "index.html").exists()


def test_generate_explainers_from_markdown_matches_exam_snippets(tmp_path, monkeypatch):
    monkeypatch.setenv("STUDYMATE_AI_PROVIDER", "stub")
    notes = [_doc([("KINETIC ENERGY and momentum are central ideas", ["Mechanics"])], source="sp2-notes.pdf")]
    notes[0].course_key = "sp2"
    exams = [_doc([("This question tests kinetic energy in moving systems", [])], source="sp2-exam.pdf")]
    exams[0].course_key = "sp2"
    exams[0].kind = "exam"
    explain.generate_explainers(
        notes, tmp_path, exam_docs=exams, strategy="chapters", log=lambda _msg: None
    )

    captured: list[list[str] | None] = []

    def fake_generate_explainer(title, text, level="intermediate", exam_snippets=None):
        captured.append(exam_snippets)
        return "<!DOCTYPE html><html><body>ok</body></html>"

    monkeypatch.setattr(llm, "generate_explainer", fake_generate_explainer)
    explain.generate_explainers_from_markdown(
        tmp_path / "markdown", tmp_path, force=True, log=lambda _msg: None
    )

    assert captured
    assert captured[0]
    assert "sp2-exam.pdf" in captured[0][0]


def test_generate_explainers_from_markdown_missing_dir_returns_empty(tmp_path):
    manifest = explain.generate_explainers_from_markdown(
        tmp_path / "no-such-dir", tmp_path, log=lambda _msg: None
    )
    assert manifest == []


def test_generate_explainers_passes_exam_snippets(tmp_path, monkeypatch):
    monkeypatch.setenv("STUDYMATE_AI_PROVIDER", "stub")
    notes = [_doc([("ENERGY TRANSFER IN SYSTEMS", ["Energy"])] , source="sp2-notes.pdf")]
    notes[0].course_key = "sp2"
    exams = [_doc([("energy transfer appears in many exam questions", [])], source="sp2-exam.pdf")]
    exams[0].course_key = "sp2"

    captured: list[list[str] | None] = []

    def fake_generate_explainer(title, text, level="intermediate", exam_snippets=None):
        captured.append(exam_snippets)
        return "<!DOCTYPE html><html><body>ok</body></html>"

    monkeypatch.setattr(llm, "generate_explainer", fake_generate_explainer)
    explain.generate_explainers(notes, tmp_path, exam_docs=exams, log=lambda _msg: None)

    assert captured
    assert captured[0]
    assert "sp2-exam.pdf" in captured[0][0]
