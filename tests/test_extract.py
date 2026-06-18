"""Tests for PDF text extraction helpers."""

from study_mate.extract import _extract_page_text, _strip_non_study_boilerplate


class _FakePage:
    def __init__(self, native_text: str = "", ocr_text: str = ""):
        self.native_text = native_text
        self.ocr_text = ocr_text

    def get_text(self, kind: str, textpage=None):
        assert kind == "text"
        if textpage is None:
            return self.native_text
        return self.ocr_text

    def get_textpage_ocr(self, language: str, dpi: int):
        return {"language": language, "dpi": dpi}


def test_strip_private_use_and_copyright_boilerplate():
    text = """
Printed by: sharanaya.chander@pacificlifere.com
Printing is for personal, private use only. No part of this book may
be reproduced or transmitted without publisher's prior permission.
Violators will be prosecuted.

Momentum is mass times velocity.
Energy is conserved in a closed system.
""".strip()

    cleaned = _strip_non_study_boilerplate(text)

    assert "Printed by:" not in cleaned
    assert "private use only" not in cleaned
    assert "No part of this book may" not in cleaned
    assert "Violators will be prosecuted" not in cleaned
    assert "Momentum is mass times velocity." in cleaned
    assert "Energy is conserved in a closed system." in cleaned


def test_strip_keeps_normal_content_when_no_boilerplate():
    text = "Kinematics studies motion.\nDynamics studies forces."
    assert _strip_non_study_boilerplate(text) == text


def test_extract_page_text_uses_native_text_first():
    page = _FakePage(native_text="native", ocr_text="ocr")
    assert _extract_page_text(page) == "native"


def test_extract_page_text_uses_ocr_when_native_empty(monkeypatch):
    monkeypatch.setenv("STUDYMATE_ENABLE_OCR", "true")
    monkeypatch.setenv("STUDYMATE_OCR_LANG", "eng")
    monkeypatch.setenv("STUDYMATE_OCR_DPI", "300")
    page = _FakePage(native_text="", ocr_text="ocr content")
    assert _extract_page_text(page) == "ocr content"


def test_extract_page_text_uses_ocr_when_native_is_only_boilerplate(monkeypatch):
    monkeypatch.setenv("STUDYMATE_ENABLE_OCR", "true")
    page = _FakePage(
        native_text="Printed by: someone@example.com\nViolators will be prosecuted.",
        ocr_text="Momentum and energy are core topics",
    )
    assert _extract_page_text(page) == "Momentum and energy are core topics"


def test_extract_page_text_returns_empty_when_ocr_disabled(monkeypatch):
    monkeypatch.setenv("STUDYMATE_ENABLE_OCR", "false")
    page = _FakePage(native_text="", ocr_text="ocr content")
    assert _extract_page_text(page) == ""
