"""Command-line interface: `explain` and `serve`."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import explain, extract


def _explain(
    notes_dir: Path,
    exam_papers_dir: Path,
    out: Path,
    token_budget: int,
    level: str,
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
        f"Generated {len(manifest)} exam-oriented explainer section(s) "
        f"from {len(notes_docs)} notes PDF(s) and {len(exam_docs)} exam PDF(s)."
    )
    print(f"Open: {index_path}")
    print("Or run: uv run study-mate serve  (then visit /explainers/)")
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
        default=explain.DEFAULT_TOKEN_BUDGET,
        help="Max input tokens per AI call (the headroom). Lower = cheaper, more files.",
    )
    p_explain.add_argument(
        "--level", default="intermediate", choices=("beginner", "intermediate", "advanced")
    )
    p_explain.add_argument(
        "--force", action="store_true", help="Regenerate explainers that already exist."
    )

    p_serve = sub.add_parser("serve", help="Serve the explainers + AI panel")
    p_serve.add_argument("--out", type=Path, default=root / "generated")
    p_serve.add_argument("--host", default="127.0.0.1")
    p_serve.add_argument("--port", type=int, default=8000)

    args = parser.parse_args(argv)

    if args.command == "explain":
        return _explain(
            args.notes,
            args.exam_papers,
            args.out,
            args.token_budget,
            args.level,
            args.force,
        )
    if args.command == "serve":
        return _serve(args.out, args.host, args.port)
    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
