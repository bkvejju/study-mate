"""Tests for the FastAPI app using the stub provider."""

from pathlib import Path

from fastapi.testclient import TestClient

from study_mate.server import create_app


def _client(tmp_path: Path) -> TestClient:
    return TestClient(create_app(tmp_path))


def test_study_endpoint_returns_html(tmp_path, monkeypatch):
    monkeypatch.setenv("STUDYMATE_AI_PROVIDER", "stub")
    client = _client(tmp_path)
    resp = client.post(
        "/api/study",
        json={"action": "summarise", "text": "Newton's laws of motion", "level": "beginner"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["action"] == "summarise"
    assert body["provider"] == "stub"
    assert "<" in body["html"]


def test_unknown_action_rejected(tmp_path):
    client = _client(tmp_path)
    resp = client.post("/api/study", json={"action": "nope", "text": "x"})
    assert resp.status_code == 400


def test_oversized_text_rejected(tmp_path):
    client = _client(tmp_path)
    resp = client.post("/api/study", json={"action": "summarise", "text": "a" * 13000})
    assert resp.status_code == 413


def test_index_missing_returns_404(tmp_path):
    client = _client(tmp_path)
    resp = client.get("/")
    assert resp.status_code == 404


def test_root_redirects_to_explainers(tmp_path):
    explainers = tmp_path / "explainers"
    explainers.mkdir()
    (explainers / "index.html").write_text("<html>nav</html>", encoding="utf-8")
    client = _client(tmp_path)
    resp = client.get("/", follow_redirects=False)
    assert resp.status_code == 307
    assert resp.headers["location"] == "/explainers/"
