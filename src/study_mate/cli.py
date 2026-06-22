"""Command-line interface: `explain` and `serve`."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from . import config, explain, extract, markdown_export


def _default_token_budget() -> int:
    raw = os.environ.get("STUDYMATE_TOKEN_BUDGET", "").strip()
    if not raw:
        return explain.DEFAULT_TOKEN_BUDGET
    try:
        value = int(raw)
    except ValueError:
        return explain.DEFAULT_TOKEN_BUDGET
    return value if value > 0 else explain.DEFAULT_TOKEN_BUDGET


def _explain_from_markdown(markdown_dir: Path, out: Path, level: str, force: bool) -> int:
    if not markdown_dir.exists():
        print(f"Markdown folder not found: {markdown_dir}", file=sys.stderr)
        print("Hint: run `uv run study-mate extract-markdown` first.", file=sys.stderr)
        return 1

    manifest = explain.generate_explainers_from_markdown(
        markdown_dir, out, level=level, force=force
    )
    if not manifest:
        print(f"No explainers generated (no chapters found in {markdown_dir}).", file=sys.stderr)
        return 1

    index_path = out / "explainers" / "index.html"
    print(f"Generated {len(manifest)} exam-oriented explainer file(s) from markdown in {markdown_dir}.")
    print(f"Open: {index_path}")
    print("Or run: uv run study-mate serve  (then visit /explainers/)")
    return 0


def _explain(
    notes_dir: Path,
    exam_papers_dir: Path,
    out: Path,
    token_budget: int,
    level: str,
    strategy: str,
    force: bool,
) -> int:
    if not notes_dir.exists():
        print(f"Notes folder not found: {notes_dir}", file=sys.stderr)
        return 1
    if not exam_papers_dir.exists():
        print(f"Exam papers folder not found: {exam_papers_dir}", file=sys.stderr)
        return 1

    notes_docs, exam_docs = extract.extract_material_sets(notes_dir, exam_papers_dir)
    if not notes_docs:
        print(f"No PDFs found in {notes_dir}. Add notes .pdf files and retry.", file=sys.stderr)
        return 1

    manifest = explain.generate_explainers(
        notes_docs,
        out,
        exam_docs=exam_docs,
        token_budget=token_budget,
        level=level,
        strategy=strategy,
        force=force,
    )
    if not manifest:
        print("No explainers generated (no extractable text in notes PDFs).", file=sys.stderr)
        print(
            "Hint: for scanned/image PDFs, install Tesseract OCR and retry. "
            "On macOS: `brew install tesseract`.",
            file=sys.stderr,
        )
        return 1

    index_path = out / "explainers" / "index.html"
    print(
        f"Generated {len(manifest)} exam-oriented explainer file(s) "
        f"from {len(notes_docs)} notes PDF(s) and {len(exam_docs)} exam PDF(s)."
    )
    print(f"Open: {index_path}")
    print("Or run: uv run study-mate serve  (then visit /explainers/)")
    return 0


def _extract_markdown(notes_dir: Path, exam_papers_dir: Path, out: Path) -> int:
    if not notes_dir.exists():
        print(f"Notes folder not found: {notes_dir}", file=sys.stderr)
        return 1
    if not exam_papers_dir.exists():
        print(f"Exam papers folder not found: {exam_papers_dir}", file=sys.stderr)
        return 1

    notes_docs, exam_docs = extract.extract_material_sets(notes_dir, exam_papers_dir)
    if not notes_docs and not exam_docs:
        print("No PDFs found in notes or exam papers folders.", file=sys.stderr)
        return 1

    note_paths = markdown_export.export_markdown_documents(notes_docs, out)
    exam_paths = markdown_export.export_markdown_documents(exam_docs, out)
    print(
        f"Exported {len(note_paths)} notes markdown file(s) and {len(exam_paths)} exam markdown file(s) "
        f"to {out / 'markdown'}"
    )
    return 0


def _serve(out: Path, host: str, port: int) -> int:
    import uvicorn

    from .server import create_app

    if not (out / "explainers" / "index.html").exists():
        print(
            "No explainers yet. Run `uv run study-mate explain` first.",
            file=sys.stderr,
        )
        return 1

    app = create_app(out)
    print(f"Serving StudyMate at http://{host}:{port}")
    print(f"  Explainers: http://{host}:{port}/explainers/")
    uvicorn.run(app, host=host, port=port)
    return 0


def main(argv: list[str] | None = None) -> int:
    config.load_env()
    parser = argparse.ArgumentParser(prog="study-mate", description="HTML-first AI study assistant")
    sub = parser.add_subparsers(dest="command", required=True)

    root = Path.cwd()

    p_explain = sub.add_parser(
        "explain", help="Step 1: notes + exam papers -> AI HTML exam-oriented explainers"
    )
    p_explain.add_argument("--notes", type=Path, default=root / "materials" / "notes")
    p_explain.add_argument(
        "--exam-papers", type=Path, default=root / "materials" / "exam_papers"
    )
    p_explain.add_argument("--out", type=Path, default=root / "generated")
    p_explain.add_argument(
        "--token-budget",
        type=int,
        default=_default_token_budget(),
        help="Max input tokens per AI call (the headroom). Lower = cheaper, more files.",
    )
    p_explain.add_argument(
        "--level", default="intermediate", choices=("beginner", "intermediate", "advanced")
    )
    p_explain.add_argument(
        "--strategy",
        default=explain.DEFAULT_STRATEGY,
        choices=("chapters", "sections"),
        help="Generation strategy: chapter-first (default) or legacy token sections.",
    )
    p_explain.add_argument(
        "--force", action="store_true", help="Regenerate explainers that already exist."
    )
    p_explain.add_argument(
        "--from-markdown",
        action="store_true",
        help=(
            "Skip PDF re-extraction and generate explainers directly from "
            "generated/markdown/*.md (chapter strategy only)."
        ),
    )
    p_explain.add_argument(
        "--markdown-dir",
        type=Path,
        default=None,
        help="Markdown source dir when using --from-markdown (default: <out>/markdown).",
    )

    p_extract_markdown = sub.add_parser(
        "extract-markdown", help="Step 0: notes + exam papers -> deterministic markdown artifacts"
    )
    p_extract_markdown.add_argument("--notes", type=Path, default=root / "materials" / "notes")
    p_extract_markdown.add_argument(
        "--exam-papers", type=Path, default=root / "materials" / "exam_papers"
    )
    p_extract_markdown.add_argument("--out", type=Path, default=root / "generated")

    p_serve = sub.add_parser("serve", help="Serve the explainers + AI panel")
    p_serve.add_argument("--out", type=Path, default=root / "generated")
    p_serve.add_argument("--host", default="127.0.0.1")
    p_serve.add_argument("--port", type=int, default=8000)

    args = parser.parse_args(argv)

    if args.command == "explain":
        if args.from_markdown:
            markdown_dir = args.markdown_dir or (args.out / "markdown")
            return _explain_from_markdown(markdown_dir, args.out, args.level, args.force)
        return _explain(
            args.notes,
            args.exam_papers,
            args.out,
            args.token_budget,
            args.level,
            args.strategy,
            args.force,
        )
    if args.command == "extract-markdown":
        return _extract_markdown(args.notes, args.exam_papers, args.out)
    if args.command == "serve":
        return _serve(args.out, args.host, args.port)
    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
