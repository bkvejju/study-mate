"""Tests for AI config resolution per role and .env loading."""

from study_mate import config


def _reset(monkeypatch):
    for var in (
        "STUDYMATE_AI_PROVIDER",
        "STUDYMATE_AI_API_KEY",
        "STUDYMATE_AI_MODEL",
        "STUDYMATE_EXPLAINER_AI_PROVIDER",
        "STUDYMATE_EXPLAINER_AI_API_KEY",
        "STUDYMATE_EXPLAINER_AI_MODEL",
        "STUDYMATE_PANEL_AI_PROVIDER",
        "STUDYMATE_PANEL_AI_API_KEY",
        "STUDYMATE_PANEL_AI_MODEL",
    ):
        monkeypatch.delenv(var, raising=False)


def test_defaults_to_stub(monkeypatch):
    _reset(monkeypatch)
    cfg = config.ai_config("panel")
    assert cfg.provider == "stub"
    assert cfg.is_stub


def test_shared_fallback_used_for_both_roles(monkeypatch):
    _reset(monkeypatch)
    monkeypatch.setenv("STUDYMATE_AI_PROVIDER", "openai")
    monkeypatch.setenv("STUDYMATE_AI_API_KEY", "shared-key")
    monkeypatch.setenv("STUDYMATE_AI_MODEL", "gpt-4o-mini")

    for role in ("explainer", "panel"):
        cfg = config.ai_config(role)
        assert cfg.provider == "openai"
        assert cfg.api_key == "shared-key"
        assert cfg.model == "gpt-4o-mini"
        assert not cfg.is_stub


def test_role_specific_overrides_shared(monkeypatch):
    _reset(monkeypatch)
    monkeypatch.setenv("STUDYMATE_AI_PROVIDER", "openai")
    monkeypatch.setenv("STUDYMATE_AI_API_KEY", "shared-key")
    # Initial generation uses a stronger anthropic model + its own key.
    monkeypatch.setenv("STUDYMATE_EXPLAINER_AI_PROVIDER", "anthropic")
    monkeypatch.setenv("STUDYMATE_EXPLAINER_AI_API_KEY", "explainer-key")
    monkeypatch.setenv("STUDYMATE_EXPLAINER_AI_MODEL", "claude-3-5-sonnet-latest")
    # Panel keeps its own cheaper model.
    monkeypatch.setenv("STUDYMATE_PANEL_AI_MODEL", "gpt-4o-mini")

    explainer = config.ai_config("explainer")
    assert explainer.provider == "anthropic"
    assert explainer.api_key == "explainer-key"
    assert explainer.model == "claude-3-5-sonnet-latest"

    panel = config.ai_config("panel")
    assert panel.provider == "openai"  # falls back to shared
    assert panel.api_key == "shared-key"  # falls back to shared
    assert panel.model == "gpt-4o-mini"  # role-specific


def test_provider_set_but_no_key_is_stub(monkeypatch):
    _reset(monkeypatch)
    monkeypatch.setenv("STUDYMATE_PANEL_AI_PROVIDER", "openai")
    cfg = config.ai_config("panel")
    assert cfg.provider == "openai"
    assert cfg.is_stub  # no key -> treated as stub


def test_load_env_reads_dotenv_without_overriding(tmp_path, monkeypatch):
    _reset(monkeypatch)
    env_file = tmp_path / ".env"
    env_file.write_text(
        "STUDYMATE_AI_PROVIDER=anthropic\nSTUDYMATE_AI_API_KEY=from-dotenv\n",
        encoding="utf-8",
    )
    # Force a fresh load against our temp file.
    monkeypatch.setattr(config, "_env_loaded", False)
    config.load_env(env_file)

    cfg = config.ai_config("panel")
    assert cfg.provider == "anthropic"
    assert cfg.api_key == "from-dotenv"
