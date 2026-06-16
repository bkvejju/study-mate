# StudyMate

Turn your study PDFs into clean, AI-written HTML explainers you can read in the
browser — with a side panel to ask questions, get summaries, quizzes, and
flashcards.

## How to use it

1. **Install dependencies**

   ```bash
   uv sync
   ```

2. **Add your PDFs** to the `materials/` folder.

3. **Generate the explainers** (this is the AI step):

   ```bash
   uv run study-mate explain
   ```

   Each PDF is read, split into budget-sized chunks, and turned into a
   standalone HTML explainer in `generated/explainers/`. Re-running skips files
   that already exist — add `--force` to regenerate.

4. **Open the app**

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
# Smaller chunks = more, shorter explainers (one per chunk)
uv run study-mate explain --token-budget 1500

# Regenerate everything
uv run study-mate explain --force

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

