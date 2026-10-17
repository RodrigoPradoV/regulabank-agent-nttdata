"""API de la maqueta. `uv run uvicorn regulabank.api.app:app --reload --port 8010`."""

from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from regulabank import agents
from regulabank.agents import metrics as metrics_mod
from regulabank.api import contracts as c
from regulabank.api import mock, pipeline
from regulabank.shared import config

settings = config.load()
app = FastAPI(title="regulabank", version=c.SCHEMA_VERSION)
app.add_middleware(
    CORSMiddleware, allow_origins=["http://localhost:4200", "http://127.0.0.1:4200"],
    allow_methods=["*"], allow_headers=["*"],
)


@app.get("/health")
def health() -> dict:
    return {"ok": True, "provider": settings.model_provider, "schema_version": c.SCHEMA_VERSION}


@app.get("/norms", response_model=list[c.NormSummary])
def norms() -> list[c.NormSummary]:
    return mock.norms()


@app.get("/norms/{norm_id}", response_model=c.NormDetail)
def norm(norm_id: str) -> c.NormDetail:
    n = mock.norm(norm_id)
    if n is None:
        raise HTTPException(404, "norma no encontrada")
    return n


@app.get("/articles/{article_id:path}", response_model=c.Article)
def article(article_id: str) -> c.Article:
    a = mock.article(article_id)
    if a is None:
        raise HTTPException(404, "artículo no encontrado")
    return a


@app.post("/answer", response_model=c.Answer)
def answer(req: c.AnswerRequest) -> c.Answer:
    """`answer_graph` sobre `data/corpus_v0` real (docs/09-agents.md); ya no es la maqueta de `mock.py`."""
    return agents.answer(req, model_provider=settings.model_provider)


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


@app.get("/metrics", response_model=c.MetricsResponse)
def metrics(
    date_from: str | None = None, date_to: str | None = None, scenario: str | None = None,
    status: str | None = None, risk: str | None = None, model: str | None = None,
    q: str | None = None, limit: int = 50,
) -> c.MetricsResponse:
    """Dashboard de trazabilidad sobre `data/ledger/answer_graph.jsonl` (docs/10-evaluation.md, Componente 6/7)."""
    filters = metrics_mod.MetricsFilters(
        date_from=date_from, date_to=date_to, scenario=scenario, status=status, risk=risk, model=model, q=q,
    )
    entries = metrics_mod.filter_entries(metrics_mod.load(), filters)
    ordered = sorted(entries, key=lambda e: e.get("logged_at") or "", reverse=True)
    return c.MetricsResponse(
        summary=metrics_mod.summarize(entries),
        series=metrics_mod.daily_series(entries),
        entries=ordered[:max(limit, 0)],
    )
