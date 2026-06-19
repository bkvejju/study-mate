# StudyMate

Turn your study PDFs into clean, AI-written HTML explainers you can read in the
browser - with a side panel to ask questions, get summaries, quizzes, and
flashcards.

## How to use it

1. **Install dependencies**

   ```bash
   uv sync
   ```

2. **Add your PDFs** to these folders:

   - `materials/notes/` for lecture/class notes
   - `materials/exam_papers/` for past papers

   Only these two folders are used by `study-mate explain`.
   PDFs directly in `materials/` are ignored.

3. **Generate the explainers** (this is the AI step):

   ```bash
   uv run study-mate explain
   ```

    StudyMate now uses a **chapter-first strategy** by default.

    - Notes are segmented into chapter-like units (using heading boundaries).
    - Each chapter is paired with related exam-paper snippets (course key +
       keyword overlap).
    - One exam-oriented HTML explainer is generated per chapter in
       `generated/explainers/`.
    - A deterministic extraction artifact is also written to
       `generated/markdown/` so extraction and prompting stay decoupled.

    Re-running skips files that already exist - add `--force` to regenerate.

4. **(Optional) Export markdown only** (no AI call):

    ```bash
    uv run study-mate extract-markdown
    ```

    This exports normalized markdown for notes and exam papers into
    `generated/markdown/`.

5. **Open the app**

   ```bash
   uv run study-mate serve
   ```

   Visit http://localhost:8000. You get one page with:
   - a **sidebar** to navigate between explainers (grouped by PDF),
   - the **AI explainer** in the middle,
   - an **AI question panel** on the right (Summarise, Explain simply, Quiz me,
     Flashcards, Key terms). It uses the current explainer — or any text you
     highlight in it — so token use stays low.

## Setting up an AI key

Without a key the app runs in **stub mode** (placeholder responses), so you can
try it with no setup. To use a real model, create a `.env` file in the project
root:

```bash
# Provider for everything: stub | openai | anthropic
STUDYMATE_AI_PROVIDER=anthropic
STUDYMATE_AI_API_KEY=sk-ant-...
```

That's enough to get started. The Anthropic provider always uses **Claude Haiku
4.5**.

### Optional: different models for generation vs. questions

There are two roles. Set per-role values to override the shared ones above:

| Role | Used by | Env prefix |
| --- | --- | --- |
| Explainer | `study-mate explain` | `STUDYMATE_EXPLAINER_AI_*` |
| Panel | the question panel | `STUDYMATE_PANEL_AI_*` |
| Shared fallback | both, if a role value is unset | `STUDYMATE_AI_*` |

Each prefix accepts `PROVIDER`, `API_KEY`, and `MODEL`. For example, use OpenAI
for the panel:

```bash
STUDYMATE_PANEL_AI_PROVIDER=openai
STUDYMATE_PANEL_AI_API_KEY=sk-...
STUDYMATE_PANEL_AI_MODEL=gpt-4o-mini
```

Real shell `export`s always win over `.env`.

## Useful options

```bash
# Chapter-first (default)
uv run study-mate explain --strategy chapters

# Legacy token chunking mode (old behavior)
uv run study-mate explain --strategy sections

# Token budget only affects section strategy
uv run study-mate explain --strategy sections --token-budget 1500

# Set default token budget via env (.env supported)
STUDYMATE_TOKEN_BUDGET=6000

# Custom input folders
uv run study-mate explain --notes materials/notes --exam-papers materials/exam_papers

# Regenerate everything
uv run study-mate explain --force

# Markdown export only (deterministic extraction stage)
uv run study-mate extract-markdown

# Reading level for the AI output
uv run study-mate explain --level beginner   # or intermediate / advanced

# Serve on a different port
uv run study-mate serve --port 9000
```

## Behind a corporate proxy?

Outbound HTTPS automatically trusts your OS keychain, which covers most TLS
proxies. If certificate verification still fails, point at your CA bundle:

```bash
STUDYMATE_CA_BUNDLE=/path/to/corp-ca.pem
```

## Privacy and copyright filtering

StudyMate strips common non-study boilerplate from extracted text before
chunking and before sending material to the LLM. This includes lines such as:

- `Printed by: ...`
- `Printing is for personal, private use only ...`
- `No part of this book may ...`
- `Violators will be prosecuted.`

This helps keep prompts focused on actual learning content only.

## Output structure

After generation, StudyMate writes:

- `generated/explainers/*.html`: chapter explainers (or section explainers in
   legacy `--strategy sections` mode)
- `generated/explainers/manifest.json`: navigation metadata
- `generated/explainers/index.html`: explainer index page
- `generated/markdown/*.md`: deterministic markdown extraction artifacts

Markdown filenames include source kind suffixes to avoid collisions:

- `*-note.md`
- `*-exam.md`

## Scanned PDFs (OCR)

If a PDF is image-only (no selectable text), StudyMate tries OCR before
sending text to the LLM.

Install Tesseract first:

```bash
brew install tesseract
```

Optional OCR settings:

```bash
# default: true
STUDYMATE_ENABLE_OCR=true

# default: eng
STUDYMATE_OCR_LANG=eng

# default: 300
STUDYMATE_OCR_DPI=300
```

## Token reduction (optional)

The explainer step can compress source text before sending it to the model
using the optional [headroom](https://github.com/chopratejas/headroom) library:

```bash
uv sync --extra compress
# For actual prose compression also install headroom's ML runtime:
#   pip install "headroom-ai[proxy]"   # lighter (onnxruntime)
#   pip install "headroom-ai[ml]"      # heavier (torch)
```

It's best-effort: if the library isn't installed, text is sent unchanged.
Toggle per role in `.env` (default on):

```bash
STUDYMATE_COMPRESS=true
STUDYMATE_EXPLAINER_COMPRESS=true
STUDYMATE_PANEL_COMPRESS=true
```

## Development

```bash
uv sync --extra dev
uv run pytest -q                # run tests
uv run ruff check src tests     # lint
```

