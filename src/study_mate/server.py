"""FastAPI app: serves the generated study app and the AI endpoint."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import llm, prompts

# Hard cap so a single request can never blow the token budget.
MAX_REQUEST_CHARS = 12000


class StudyRequest(BaseModel):
    action: str = Field(..., description="One of: summarise, explain, quiz, flashcards, key_terms")
    text: str = Field(..., min_length=1, description="Current section or highlighted text only")
    level: str = Field("intermediate")
    section_id: str | None = None
    section_title: str | None = None
    source_pdf: str | None = None
    page_range: str | None = None


class StudyResponse(BaseModel):
    html: str
    action: str
    provider: str


def create_app(generated_dir: Path) -> FastAPI:
    app = FastAPI(title="StudyMate")

    @app.post("/api/study", response_model=StudyResponse)
    def study(req: StudyRequest) -> StudyResponse:
        if req.action not in prompts.ACTIONS:
            raise HTTPException(status_code=400, detail=f"Unknown action: {req.action}")
        if len(req.text) > MAX_REQUEST_CHARS:
            raise HTTPException(
                status_code=413,
                detail="Selection too large. Narrow your highlight or pick a smaller section.",
            )
        result_html = llm.generate(req.action, req.text, req.level)
        return StudyResponse(html=result_html, action=req.action, provider=llm.provider())

    @app.get("/")
    def index():
        # The explainers navigation shell is the only entry point. Redirect so
        # its iframe can load explainer files relative to /explainers/.
        explainers_index = generated_dir / "explainers" / "index.html"
        if explainers_index.exists():
            return RedirectResponse(url="/explainers/")
        raise HTTPException(
            status_code=404,
            detail="Nothing generated yet. Run `uv run study-mate explain` first.",
        )

    if (generated_dir / "assets").exists():
        app.mount(
            "/assets",
            StaticFiles(directory=generated_dir / "assets"),
            name="assets",
        )

    if (generated_dir / "explainers").exists():
        app.mount(
            "/explainers",
            StaticFiles(directory=generated_dir / "explainers", html=True),
            name="explainers",
        )

    return app
