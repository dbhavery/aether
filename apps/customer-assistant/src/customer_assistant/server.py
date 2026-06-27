"""FastAPI service for the Customer Assistant demo.

Endpoints
---------
* ``GET  /health``                      — liveness + Ollama status.
* ``GET  /companies``                   — list onboarded company ids.
* ``GET  /companies/{id}/branding``     — branding payload for the widget.
* ``POST /chat``                        — answer a message for a company.
* ``GET  /widget.js`` / ``GET /`` ...   — static widget + demo page.

On startup every company under ``COMPANIES_ROOT`` is discovered, its profile
validated, and its knowledge base opened (ingested on first run if empty).
"""

from __future__ import annotations

import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from customer_assistant.assistant import CustomerAssistant
from customer_assistant.config import (
    CompanyConfigError,
    CompanyProfile,
    discover_companies,
    load_company,
)
from customer_assistant.knowledge_base import KnowledgeBase
from customer_assistant.llm import OllamaClient

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("customer_assistant.server")

# Repo layout: apps/customer-assistant/src/customer_assistant/server.py
APP_ROOT = Path(__file__).resolve().parents[2]  # apps/customer-assistant
COMPANIES_ROOT = Path(os.environ.get("COMPANIES_ROOT", APP_ROOT / "companies")).resolve()
WIDGET_DIR = APP_ROOT / "widget"

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Discover and open every company on startup (replaces on_event)."""
    _load_all()
    yield


app = FastAPI(title="Aether Customer Assistant", version="0.1.0", lifespan=lifespan)

# The widget is meant to be embedded on arbitrary company sites, so allow any
# origin for this local demo. A production deployment would allowlist the
# company's domain(s) per company.yaml.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

# Registry of loaded assistants, keyed by company id.
_assistants: dict[str, CustomerAssistant] = {}
_profiles: dict[str, CompanyProfile] = {}
_llm = OllamaClient()


class ChatRequest(BaseModel):
    company_id: str = Field(..., description="Onboarded company id")
    message: str = Field(..., description="The customer's message")
    top_k: int = Field(default=4, ge=1, le=10)


class CitationOut(BaseModel):
    source: str
    snippet: str


class ChatResponse(BaseModel):
    company_id: str
    answer: str
    citations: list[CitationOut]
    model: str
    degraded: bool
    escalate: bool


def _load_all() -> None:
    """Discover, validate, and open every company; ingest KB if empty."""
    found = discover_companies(COMPANIES_ROOT)
    if not found:
        logger.warning("no companies found under %s", COMPANIES_ROOT)
    for company_id, company_dir in found.items():
        try:
            profile = load_company(company_dir)
            kb = KnowledgeBase(profile)
            if kb.count() == 0:
                logger.info("knowledge base for %r is empty; ingesting…", company_id)
                kb.ingest(reset=True)
            _profiles[company_id] = profile
            _assistants[company_id] = CustomerAssistant(profile, kb, llm=_llm)
            logger.info(
                "loaded company %r (%d KB chunks, model=%s)",
                company_id,
                kb.count(),
                profile.effective_model(),
            )
        except (CompanyConfigError, FileNotFoundError) as exc:
            logger.error("failed to load company %r: %s", company_id, exc)


@app.get("/health")
def health() -> dict[str, object]:
    return {
        "status": "ok",
        "companies": sorted(_assistants),
        "ollama_up": _llm.is_up(),
    }


@app.get("/companies")
def list_companies() -> dict[str, list[str]]:
    return {"companies": sorted(_assistants)}


@app.get("/companies/{company_id}/branding")
def branding(company_id: str) -> dict[str, object]:
    profile = _profiles.get(company_id)
    if profile is None:
        raise HTTPException(status_code=404, detail=f"unknown company {company_id!r}")
    b = profile.branding
    return {
        "company_id": company_id,
        "display_name": profile.company.display_name,
        "tagline": profile.company.tagline,
        "greeting": b.greeting,
        "logo": b.logo,
        "colors": b.colors.model_dump(),
    }


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest) -> ChatResponse:
    assistant = _assistants.get(req.company_id)
    if assistant is None:
        raise HTTPException(
            status_code=404,
            detail=f"unknown company {req.company_id!r}; known: {sorted(_assistants)}",
        )
    reply = assistant.answer(req.message, top_k=req.top_k)
    return ChatResponse(
        company_id=req.company_id,
        answer=reply.answer,
        citations=[CitationOut(source=c.source, snippet=c.snippet) for c in reply.citations],
        model=reply.model,
        degraded=reply.degraded,
        escalate=reply.escalate,
    )


# ── Static widget + demo page ───────────────────────────────────────────────
@app.get("/widget.js")
def widget_js() -> FileResponse:
    path = WIDGET_DIR / "widget.js"
    if not path.is_file():
        raise HTTPException(status_code=404, detail="widget.js not found")
    return FileResponse(path, media_type="application/javascript")


@app.get("/")
def demo_index() -> FileResponse:
    path = WIDGET_DIR / "index.html"
    if not path.is_file():
        raise HTTPException(status_code=404, detail="demo index.html not found")
    return FileResponse(path, media_type="text/html")


def main() -> None:
    """Console entry point: ``python -m customer_assistant.server``."""
    import uvicorn

    host = os.environ.get("CA_HOST", "127.0.0.1")
    port = int(os.environ.get("CA_PORT", "8200"))
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
