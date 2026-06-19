"""AI provider wrapper. Configurable via env / .env; falls back to a
deterministic stub so the app runs with no API key.

Settings are resolved per role by :mod:`study_mate.config`:
- "explainer" : the initial token-heavy HTML generation (`study-mate explain`).
- "panel"     : the on-the-go study panel.

Each role reads STUDYMATE_EXPLAINER_AI_* / STUDYMATE_PANEL_AI_*, falling back to
the shared STUDYMATE_AI_* (PROVIDER / API_KEY / MODEL).
"""

from __future__ import annotations

import functools
import html
import os
import re
import ssl
import textwrap

import httpx

from . import config, prompts

_OPENAI_DEFAULT_MODEL = "gpt-4o-mini"
# Anthropic usage is locked to Claude Haiku 4.5 regardless of any configured
# STUDYMATE_*_AI_MODEL override, so all Anthropic calls stay on this model.
_ANTHROPIC_MODEL = "claude-haiku-4-5"
_MAX_OUTPUT_TOKENS = 700
# Explainers are whole HTML pages, so they need much more output headroom.
# Claude Haiku 4.5 supports large outputs; 8000 comfortably fits a full page so
# the document is never truncated mid-sentence. Override via STUDYMATE_EXPLAINER_
# MAX_OUTPUT_TOKENS if needed.
_EXPLAINER_MAX_OUTPUT_TOKENS = int(os.environ.get("STUDYMATE_EXPLAINER_MAX_OUTPUT_TOKENS", "8000"))

_EXPLAINER_CANONICAL_CSS = """
:root {
    --bg: #f9f7f4;
    --surface: #ffffff;
    --text: #24201c;
    --muted: #6a6258;
    --accent: #b65a3b;
    --accent-2: #2f6fa8;
    --border: #e2dbd3;
}

* {
    box-sizing: border-box;
}

html,
body {
    margin: 0;
    padding: 0;
}

body {
    background: var(--bg);
    color: var(--text);
    font-family: "Segoe UI", Tahoma, Geneva, Verdana, sans-serif;
    line-height: 1.6;
}

main.page {
    max-width: 980px;
    margin: 0 auto;
    padding: 24px 16px 44px;
}

header.hero {
    background: linear-gradient(135deg, var(--accent), var(--accent-2));
    color: #ffffff;
    border-radius: 14px;
    padding: 22px 20px;
    margin-bottom: 18px;
}

header.hero h1 {
    margin: 0 0 8px;
    font-size: 1.7rem;
}

header.hero p.lead {
    margin: 0;
    font-size: 1rem;
    opacity: 0.95;
}

section {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 16px 18px;
    margin-bottom: 14px;
}

section h2 {
    margin: 0 0 10px;
    color: var(--accent);
    font-size: 1.2rem;
    border-bottom: 2px solid var(--accent-2);
    padding-bottom: 6px;
}

h3 {
    margin: 14px 0 6px;
    color: var(--text);
    font-size: 1rem;
}

p {
    margin: 0 0 10px;
}

ul,
ol,
dl {
    margin: 0 0 12px 20px;
}

li {
    margin-bottom: 6px;
}

dl.key-terms-list {
    margin-left: 0;
}

dl.key-terms-list dt {
    font-weight: 700;
    color: var(--accent);
    margin-top: 10px;
}

dl.key-terms-list dd {
    margin: 4px 0 0 0;
    color: var(--text);
}

ul.recap-list {
    margin-left: 18px;
}

@media (max-width: 720px) {
    main.page {
        padding: 14px 10px 24px;
    }

    header.hero h1 {
        font-size: 1.35rem;
    }

    section {
        padding: 14px;
    }
}
""".strip()


@functools.lru_cache(maxsize=1)
def _ssl_verify() -> ssl.SSLContext | bool:
    """Resolve how outbound HTTPS calls verify certificates.

    Many corporate networks intercept TLS with a self-signed root CA, which the
    default ``certifi`` bundle does not trust. We never disable verification;
    instead we trust the OS / corporate certificate store:

    1. An explicit PEM bundle via ``STUDYMATE_CA_BUNDLE`` / ``SSL_CERT_FILE`` /
       ``REQUESTS_CA_BUNDLE`` (if set), else
    2. the OS trust store (macOS keychain, etc.) via ``truststore``, else
    3. the default ``certifi`` bundle.
    """
    bundle = (
        os.environ.get("STUDYMATE_CA_BUNDLE")
        or os.environ.get("SSL_CERT_FILE")
        or os.environ.get("REQUESTS_CA_BUNDLE")
    )
    if bundle:
        return ssl.create_default_context(cafile=bundle)
    try:
        import truststore

        return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    except Exception:
        return True


def provider(role: str = "panel") -> str:
    """Return the configured provider name for a role (default: the study panel)."""
    return config.ai_config(role).provider


def _strip_code_fences(content: str) -> str:
    """Remove a leading ```html / ``` fence and trailing ``` if the model wraps
    its HTML output in a Markdown code block."""
    stripped = content.strip()
    if stripped.startswith("```"):
        first_newline = stripped.find("\n")
        if first_newline != -1:
            stripped = stripped[first_newline + 1 :]
        if stripped.rstrip().endswith("```"):
            stripped = stripped.rstrip()[: -len("```")]
    return stripped.strip()


def _normalise_explainer_style(content: str) -> str:
    """Force one shared stylesheet so every generated explainer looks consistent."""
    style_block = f"<style>\n{_EXPLAINER_CANONICAL_CSS}\n</style>"
    if re.search(r"<style\b[^>]*>.*?</style>", content, flags=re.IGNORECASE | re.DOTALL):
        return re.sub(
            r"<style\b[^>]*>.*?</style>",
            style_block,
            content,
            count=1,
            flags=re.IGNORECASE | re.DOTALL,
        )
    if re.search(r"</head>", content, flags=re.IGNORECASE):
        return re.sub(r"</head>", f"{style_block}\n</head>", content, count=1, flags=re.IGNORECASE)
    return content


def _stub_response(action: str, text: str) -> str:
    preview = html.escape(textwrap.shorten(text.strip(), width=240, placeholder=" …"))
    note = (
        "<p><em>Stub mode — no AI provider configured. "
        "Set STUDYMATE_AI_PROVIDER and STUDYMATE_AI_API_KEY to use a real model."
        "</em></p>"
    )
    return (
        f"<p><strong>{html.escape(action)}</strong> (preview of selected text):</p>"
        f"<blockquote>{preview}</blockquote>{note}"
    )


def _call_openai(
    system: str, user: str, model: str, api_key: str, max_tokens: int = _MAX_OUTPUT_TOKENS
) -> str:
    resp = httpx.post(
        "https://api.openai.com/v1/chat/completions",
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "max_tokens": max_tokens,
            "temperature": 0.3,
        },
        timeout=120,
        verify=_ssl_verify(),
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


def _call_anthropic(
    system: str, user: str, model: str, api_key: str, max_tokens: int = _MAX_OUTPUT_TOKENS
) -> str:
    resp = httpx.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        },
        json={
            "model": model,
            "system": system,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": user}],
        },
        timeout=120,
        verify=_ssl_verify(),
    )
    resp.raise_for_status()
    return resp.json()["content"][0]["text"]


def generate(action: str, text: str, level: str = "intermediate") -> str:
    """Generate an HTML response for a study action over a single snippet
    (the on-the-go study panel)."""
    cfg = config.ai_config("panel")
    if cfg.is_stub:
        return _stub_response(action, text)

    system = prompts.system_prompt()
    user = prompts.build_prompt(action, text, level)
    if cfg.provider == "openai":
        return _call_openai(system, user, cfg.model or _OPENAI_DEFAULT_MODEL, cfg.api_key)
    if cfg.provider == "anthropic":
        return _call_anthropic(system, user, _ANTHROPIC_MODEL, cfg.api_key)
    return _stub_response(action, text)


def _stub_explainer(title: str, text: str) -> str:
    """Deterministic standalone HTML explainer used when no AI provider is set."""
    safe_title = html.escape(title)
    preview = html.escape(textwrap.shorten(text.strip(), width=600, placeholder=" …"))
    return (
        "<!DOCTYPE html>\n"
        '<html lang="en">\n<head>\n<meta charset="UTF-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1.0">\n'
        f"<title>{safe_title}</title>\n"
        "<style>\n"
        "  body{margin:0;background:#0e1320;color:#e8edf7;"
        "font-family:-apple-system,Segoe UI,Roboto,sans-serif;line-height:1.65;}\n"
        "  .wrap{max-width:760px;margin:0 auto;padding:64px 24px 120px;}\n"
        "  .kicker{font-size:12px;letter-spacing:.2em;text-transform:uppercase;color:#2dd4bf;}\n"
        "  h1{font-size:40px;margin:.2em 0;}\n"
        "  h2{font-size:24px;margin-top:40px;}\n"
        "  blockquote{border-left:3px solid #2dd4bf;margin:0;padding:8px 16px;"
        "color:#cdd6ea;background:#161f33;border-radius:8px;}\n"
        "  em{color:#97a3bd;}\n"
        "</style>\n</head>\n<body>\n<div class=\"wrap\">\n"
        '  <p class="kicker">StudyMate Explainer</p>\n'
        f"  <h1>{safe_title}</h1>\n"
        "  <p><em>Stub mode — no AI provider configured. Set STUDYMATE_AI_PROVIDER "
        "and STUDYMATE_AI_API_KEY to generate a full AI explainer.</em></p>\n"
        "  <h2>Source material (preview)</h2>\n"
        f"  <blockquote>{preview}</blockquote>\n"
        "</div>\n</body>\n</html>\n"
    )


def generate_explainer(
    title: str,
    text: str,
    level: str = "intermediate",
    exam_snippets: list[str] | None = None,
) -> str:
    """Generate a complete standalone HTML explainer document for one chunk of
    study material (the initial token-heavy generation step)."""
    cfg = config.ai_config("explainer")
    if cfg.is_stub:
        return _stub_explainer(title, text)

    system = prompts.explainer_system_prompt()
    user = prompts.build_explainer_prompt(title, text, level, exam_snippets=exam_snippets)
    if cfg.provider == "openai":
        content = _call_openai(
            system, user, cfg.model or _OPENAI_DEFAULT_MODEL, cfg.api_key, _EXPLAINER_MAX_OUTPUT_TOKENS
        )
    elif cfg.provider == "anthropic":
        content = _call_anthropic(
            system,
            user,
            _ANTHROPIC_MODEL,
            cfg.api_key,
            _EXPLAINER_MAX_OUTPUT_TOKENS,
        )
    else:
        return _stub_explainer(title, text)
    return _normalise_explainer_style(_strip_code_fences(content))
