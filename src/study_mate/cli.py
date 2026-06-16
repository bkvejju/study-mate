"""Command-line interface: `explain` and `serve`."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import explain, extract


def _explain(materials: Path, out: Path, token_budget: int, level: str, force: bool) -> int:
    if not materials.exists():
        print(f"Materials folder not found: {materials}", file=sys.stderr)
        return 1

    docs = extract.extract_dir(materials)
    if not docs:
        print(f"No PDFs found in {materials}. Add some .pdf files and retry.", file=sys.stderr)
        return 1

    manifest = explain.generate_explainers(
        docs, out, token_budget=token_budget, level=level, force=force
    )
    if not manifest:
        print("No explainers generated (no extractable text in any PDF).", file=sys.stderr)
        return 1

    index_path = out / "explainers" / "index.html"
    print(f"Generated {len(manifest)} explainer(s) from {len(docs)} PDF(s).")
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
        "explain", help="Step 1: PDFs in materials/ -> AI HTML explainers"
    )
    p_explain.add_argument("--materials", type=Path, default=root / "materials")
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
        return _explain(args.materials, args.out, args.token_budget, args.level, args.force)
    if args.command == "serve":
        return _serve(args.out, args.host, args.port)
    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
