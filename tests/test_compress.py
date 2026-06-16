"""Tests for the modular token-reduction (headroom) wrapper."""

from study_mate import compress, config


def _reset(monkeypatch):
    for var in (
        "STUDYMATE_COMPRESS",
        "STUDYMATE_EXPLAINER_COMPRESS",
        "STUDYMATE_PANEL_COMPRESS",
    ):
        monkeypatch.delenv(var, raising=False)


def test_unavailable_returns_original(monkeypatch):
    _reset(monkeypatch)
    monkeypatch.setattr(compress, "_headroom_compress", lambda _text: None)
    out = compress.compress_text("some study material here", role="explainer")
    assert out.applied is False
    assert out.detail == "unavailable"
    assert out.text == "some study material here"
    assert out.tokens_saved == 0


def test_applies_compression_when_shorter(monkeypatch):
    _reset(monkeypatch)
    long_text = "word " * 400  # ~2000 chars
    monkeypatch.setattr(compress, "_headroom_compress", lambda _text: "word " * 50)
    out = compress.compress_text(long_text, role="explainer")
    assert out.applied is True
    assert out.detail == "headroom"
    assert out.tokens_after < out.tokens_before
    assert out.savings_percent > 0


def test_no_gain_keeps_original(monkeypatch):
    _reset(monkeypatch)
    text = "short text"
    # "Compressed" output is not actually shorter.
    monkeypatch.setattr(compress, "_headroom_compress", lambda _t: text + " extra padding")
    out = compress.compress_text(text, role="explainer")
    assert out.applied is False
    assert out.detail == "no-gain"
    assert out.text == text


def test_disabled_via_config(monkeypatch):
    _reset(monkeypatch)
    monkeypatch.setenv("STUDYMATE_EXPLAINER_COMPRESS", "false")

    def _boom(_text):  # should never be called when disabled
        raise AssertionError("compression should be skipped when disabled")

    monkeypatch.setattr(compress, "_headroom_compress", _boom)
    out = compress.compress_text("word " * 400, role="explainer")
    assert out.applied is False
    assert out.detail == "disabled"


def test_errors_fall_back_to_original(monkeypatch):
    _reset(monkeypatch)

    def _raise(_text):
        raise RuntimeError("headroom blew up")

    monkeypatch.setattr(compress, "_headroom_compress", _raise)
    out = compress.compress_text("word " * 400, role="panel")
    assert out.applied is False
    assert out.detail == "error"
    assert out.text == "word " * 400


def test_empty_text_is_noop(monkeypatch):
    _reset(monkeypatch)
    out = compress.compress_text("   ", role="explainer")
    assert out.applied is False
    assert out.detail == "empty"


def test_compression_config_defaults_enabled(monkeypatch):
    _reset(monkeypatch)
    assert config.compression_config("explainer").enabled is True


def test_role_specific_overrides_shared(monkeypatch):
    _reset(monkeypatch)
    monkeypatch.setenv("STUDYMATE_COMPRESS", "true")
    monkeypatch.setenv("STUDYMATE_PANEL_COMPRESS", "off")
    assert config.compression_config("explainer").enabled is True
    assert config.compression_config("panel").enabled is False
