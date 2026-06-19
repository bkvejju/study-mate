"""Prompt templates for each study action. Each prompt operates ONLY on the
provided snippet (current section or highlighted text)."""

from __future__ import annotations

ACTIONS = ("summarise", "explain", "quiz", "flashcards", "key_terms")

_LEVEL_HINT = {
    "beginner": "Assume the reader is new to the topic. Avoid jargon.",
    "intermediate": "Assume some background knowledge.",
    "advanced": "Assume strong background knowledge; be concise and precise.",
}

_SYSTEM = (
    "You are StudyMate, a focused study assistant. You ONLY use the study "
    "material provided in the user message. Do not invent facts beyond it. "
    "If the material is insufficient, say so briefly. Respond in clean HTML "
    "(no <html> or <body> wrapper) suitable for embedding in a panel."
)


_EXPLAINER_SYSTEM = (
    "You are StudyMate. Turn the provided study material into a single, "
    "self-contained, exam-oriented HTML explainer document. "
    "Output a COMPLETE valid HTML5 document: start with <!DOCTYPE html> and end "
    "with </html>, with all CSS embedded in a single <style> tag. "
    "Follow ONE consistent layout pattern exactly: "
    "body > main.page > header.hero (h1 + p.lead) + six <section> blocks in this "
    "exact order and with these exact ids: #core-notes, #exam-focus, #brush-up, "
    "#common-mistakes, #key-terms, #quick-recap. "
    "Use these exact <h2> titles in order: '1. Core Notes Summary', "
    "'2. Exam Focus Areas', '3. What To Brush Up On', '4. Common Mistakes', "
    "'5. Key Terms', '6. Quick Recap'. "
    "Use a single consistent CSS token set in :root with variables: --bg, --surface, "
    "--text, --muted, --accent, --accent-2, --border. "
    "No inline styles, no tables, no scripts, no external CSS/fonts/images, and no "
    "network requests. Use concise bullets and short paragraphs. Render key terms "
    "as <dl class='key-terms-list'> with <dt>/<dd> pairs. Render quick recap as "
    "<ul class='recap-list'> with 5-8 bullets. If related exam snippets are provided, "
    "tie advice to them explicitly. Only use the material provided; do not invent "
    "facts beyond it. Do not wrap the document in Markdown code fences."
)


def system_prompt() -> str:
    return _SYSTEM


def explainer_system_prompt() -> str:
    return _EXPLAINER_SYSTEM


def build_explainer_prompt(
    title: str, text: str, level: str = "intermediate", exam_snippets: list[str] | None = None
) -> str:
    """Build the user prompt for generating a standalone HTML explainer for one
    chunk of study material."""
    level_hint = _LEVEL_HINT.get(level, _LEVEL_HINT["intermediate"])
    snippets = exam_snippets or []
    exam_block = "\n\n".join(f"- {snippet}" for snippet in snippets)
    if not exam_block:
        exam_block = "- No related exam snippets were matched. Provide general exam guidance from the notes."
    return (
        f"Create an exam-oriented HTML explainer titled \"{title}\" for the notes "
        f"material below.\n{level_hint}\n\n"
        "Prioritise likely exam framing, revision targets, and concise brush-up tasks. "
        "Follow the required HTML structure and section order from the system "
        "instructions exactly.\n\n"
        f"--- NOTES MATERIAL START ---\n{text}\n--- NOTES MATERIAL END ---\n\n"
        f"--- RELATED EXAM SNIPPETS START ---\n{exam_block}\n--- RELATED EXAM SNIPPETS END ---"
    )


def build_prompt(action: str, text: str, level: str = "intermediate") -> str:
    """Build the user prompt for a given action and snippet."""
    level_hint = _LEVEL_HINT.get(level, _LEVEL_HINT["intermediate"])
    instructions = {
        "summarise": (
            "Summarise the study material below into concise bullet points "
            "capturing the key ideas."
        ),
        "explain": (
            "Explain the study material below in simple, plain language, as if "
            "teaching a student. Use short paragraphs and a simple example if helpful."
        ),
        "quiz": (
            "Create 3-5 short questions that test understanding of the material "
            "below. Provide each question, then a collapsible answer using "
            "<details><summary>Show answer</summary>...</details>."
        ),
        "flashcards": (
            "Create 4-8 flashcards from the material below. Render each as "
            "'<div class=\"flashcard\"><strong>Q:</strong> ... <br><strong>A:</strong> ...</div>'."
        ),
        "key_terms": (
            "Extract the key terms and definitions from the material below. "
            "Render as a <dl> list of <dt>term</dt><dd>definition</dd> pairs."
        ),
    }
    task = instructions.get(action, instructions["summarise"])
    return (
        f"{task}\n{level_hint}\n\n"
        f"--- STUDY MATERIAL START ---\n{text}\n--- STUDY MATERIAL END ---"
    )
