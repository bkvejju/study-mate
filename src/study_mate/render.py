"""Render the explainer navigation shell from generated explainer files."""

from __future__ import annotations

import json
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

_TEMPLATES = Path(__file__).parent / "templates"


def render_explainer_index(explainers: list, explainers_dir: Path) -> Path:
    """Render the navigation shell that lists every generated explainer and
    loads them in a single page. Returns the index.html path."""
    explainers_dir.mkdir(parents=True, exist_ok=True)

    entries = [
        {
            "source": e.source,
            "title": e.title,
            "page_range": e.page_range,
            "file": e.file,
            "text": e.text,
        }
        for e in explainers
    ]

    env = Environment(
        loader=FileSystemLoader(_TEMPLATES),
        autoescape=select_autoescape(["html"]),
    )
    template = env.get_template("explainers.html")
    html = template.render(
        entries=entries,
        entries_json=json.dumps(entries),
    )

    index_path = explainers_dir / "index.html"
    index_path.write_text(html, encoding="utf-8")
    return index_path
