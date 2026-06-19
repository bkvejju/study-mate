"""Tests for prompt building and the stub AI provider."""

import os

from study_mate import llm, prompts


def test_all_actions_have_instructions():
    for action in prompts.ACTIONS:
        text = prompts.build_prompt(action, "some material", "beginner")
        assert "STUDY MATERIAL START" in text
        assert "some material" in text


def test_prompt_includes_level_hint():
    text = prompts.build_prompt("summarise", "x", "advanced")
    assert "background knowledge" in text.lower()


def test_stub_provider_returns_html(monkeypatch):
    monkeypatch.setenv("STUDYMATE_AI_PROVIDER", "stub")
    out = llm.generate("summarise", "photosynthesis converts light to energy")
    assert "<" in out and ">" in out
    assert "Stub mode" in out


def test_missing_key_falls_back_to_stub(monkeypatch):
    monkeypatch.setenv("STUDYMATE_AI_PROVIDER", "openai")
    monkeypatch.delenv("STUDYMATE_AI_API_KEY", raising=False)
    out = llm.generate("explain", "text")
    assert "Stub mode" in out


def test_provider_default_is_stub(monkeypatch):
    monkeypatch.delenv("STUDYMATE_AI_PROVIDER", raising=False)
    assert llm.provider() == "stub"
    assert os.environ.get("STUDYMATE_AI_PROVIDER") is None


def test_explainer_prompt_includes_exam_snippets():
    out = prompts.build_explainer_prompt(
        "Mechanics",
        "Force equals mass times acceleration",
        level="intermediate",
        exam_snippets=["sp2-exam.pdf p.2: force and momentum"],
    )
    assert "RELATED EXAM SNIPPETS START" in out
    assert "sp2-exam.pdf p.2" in out


def test_explainer_system_prompt_defines_fixed_pattern():
    system = prompts.explainer_system_prompt()
    assert "#core-notes" in system
    assert "#exam-focus" in system
    assert "#brush-up" in system
    assert "#common-mistakes" in system
    assert "#key-terms" in system
    assert "#quick-recap" in system
    assert "No inline styles, no tables" in system


def test_explainer_style_is_normalized():
    raw = (
        "<!DOCTYPE html><html><head><meta charset='utf-8'>"
        "<style>body{background:red}</style></head>"
        "<body><main class='page'></main></body></html>"
    )
    out = llm._normalise_explainer_style(raw)
    assert "background:red" not in out
    assert "--bg: #f9f7f4;" in out
