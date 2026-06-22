"""Tests for CLI defaults and env overrides."""

from pathlib import Path

from study_mate import cli, explain
from study_mate.extract import DocumentText, PageText


def test_default_token_budget_falls_back_when_unset(monkeypatch):
    monkeypatch.delenv("STUDYMATE_TOKEN_BUDGET", raising=False)
    assert cli._default_token_budget() == explain.DEFAULT_TOKEN_BUDGET


def test_default_token_budget_uses_env_value(monkeypatch):
    monkeypatch.setenv("STUDYMATE_TOKEN_BUDGET", "6000")
    assert cli._default_token_budget() == 6000


def test_default_token_budget_ignores_invalid_env_value(monkeypatch):
    monkeypatch.setenv("STUDYMATE_TOKEN_BUDGET", "abc")
    assert cli._default_token_budget() == explain.DEFAULT_TOKEN_BUDGET


def _doc(source: str, kind: str) -> DocumentText:
    return DocumentText(
        source=source,
        kind=kind,
        course_key="sp2",
        pages=[PageText(page_number=1, text="content", headings=["Part 1"])],
    )


def test_explain_from_markdown_generates_when_markdown_exists(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("STUDYMATE_AI_PROVIDER", "stub")
    docs = [_doc("a.pdf", "note")]
    explain.generate_explainers(docs, tmp_path, strategy="chapters", log=lambda _msg: None)

    exit_code = cli.main(
        [
            "explain",
            "--out",
            str(tmp_path),
            "--from-markdown",
            "--force",
        ]
    )

    assert exit_code == 0


def test_explain_from_markdown_missing_dir_errors(tmp_path: Path, capsys):
    exit_code = cli.main(["explain", "--out", str(tmp_path), "--from-markdown"])
    assert exit_code == 1
    assert "Markdown folder not found" in capsys.readouterr().err


def test_extract_markdown_writes_files(tmp_path: Path, monkeypatch):
    notes_dir = tmp_path / "notes"
    exams_dir = tmp_path / "exam_papers"
    notes_dir.mkdir()
    exams_dir.mkdir()

    monkeypatch.setattr(
        cli.extract,
        "extract_material_sets",
        lambda _n, _e: ([_doc("note.pdf", "note")], [_doc("exam.pdf", "exam")]),
    )

    exit_code = cli._extract_markdown(notes_dir, exams_dir, tmp_path)

    assert exit_code == 0
    assert (tmp_path / "markdown" / "note-note.md").exists()
    assert (tmp_path / "markdown" / "exam-exam.md").exists()
