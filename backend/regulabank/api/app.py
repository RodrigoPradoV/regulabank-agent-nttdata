"""API de la maqueta. `uv run uvicorn regulabank.api.app:app --reload --port 8010`."""

from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from regulabank.api import contracts as c
from regulabank.api import live as live_mod
from regulabank.api import mock, pipeline
from regulabank.shared import config

settings = config.load()
live = live_mod.maybe_live()   # con REGULABANK_RELEASE responde con el corpus y el agente reales; sin ella, la maqueta
app = FastAPI(title="regulabank", version=c.SCHEMA_VERSION)
app.add_middleware(
    CORSMiddleware, allow_origins=["http://localhost:4200", "http://127.0.0.1:4200"],
    allow_methods=["*"], allow_headers=["*"],
)


@app.get("/health")
def health() -> dict:
    return {"ok": True, "provider": settings.model_provider, "live": live is not None, "schema_version": c.SCHEMA_VERSION}


@app.get("/norms", response_model=list[c.NormSummary])
def norms() -> list[c.NormSummary]:
    return live.norms() if live else mock.norms()


@app.get("/norms/{norm_id}", response_model=c.NormDetail)
def norm(norm_id: str) -> c.NormDetail:
    n = live.norm(norm_id) if live else mock.norm(norm_id)
    if n is None:
        raise HTTPException(404, "norma no encontrada")
    return n


@app.get("/articles/{article_id:path}", response_model=c.Article)
def article(article_id: str) -> c.Article:
    a = live.article(article_id) if live else mock.article(article_id)
    if a is None:
        raise HTTPException(404, "artículo no encontrado")
    return a


@app.post("/answer", response_model=c.Answer)
def answer(req: c.AnswerRequest) -> c.Answer:
    return live.answer(req) if live else mock.answer(req)


@app.get("/conflicts", response_model=list[c.Conflict])
def conflicts() -> list[c.Conflict]:
    return mock.conflicts()


@app.post("/conflicts/{conflict_id}/decide", response_model=c.Conflict)
def decide(conflict_id: str, decision: c.Decision) -> c.Conflict:
    cf = mock.decide(conflict_id, decision)
    if cf is None:
        raise HTTPException(404, "conflicto no encontrado")
    return cf


@app.get("/pipeline", response_model=pipeline.Pipeline)
def get_pipeline() -> pipeline.Pipeline:
    return pipeline.build(settings)
