"""Puente entre `answer_graph` y el contrato HTTP (`regulabank.api.contracts`). No agrega logica nueva.

`mock.py` (docstring propio) dice que se reemplaza por lecturas al release real cuando exista; `data/corpus_v0`
ya existe, asi que `/answer` corre el grafo de verdad (con `retrieve_stub`: lexico + entidades, sin embeddings
todavia) en vez de las respuestas guionadas por palabra clave. El proveedor del modelo sale de `MODEL_PROVIDER`
(docs/12-infra.md); hoy solo existe `mock`, los demas se agregan en `providers.py` sin tocar este puente.

`history` queda vacio por ahora: para armarlo hace falta el grafo de versiones (`horizon`) cargado, y
`graph_ingest_v0` todavia no esta en FalkorDB (ver docs/06-graphs.md).
"""

from __future__ import annotations

import time
import uuid
from datetime import date
from typing import Any

from regulabank.agents.contracts import RouteWeights
from regulabank.agents.graph import build_answer_graph
from regulabank.agents.providers import BaseProvider, FakeProvider
from regulabank.api import contracts as api_c

_CACHE: dict[str, tuple[Any, BaseProvider]] = {}  # un (grafo, proveedor) por MODEL_PROVIDER; una vez por proceso


def _provider_for(model_provider: str) -> BaseProvider:
    if model_provider == "mock":
        return FakeProvider()
    raise NotImplementedError(
        f"MODEL_PROVIDER={model_provider!r} todavia no tiene proveedor real (docs/09-agents.md, docs/12-infra.md)"
    )


def _graph_for(model_provider: str) -> tuple[Any, BaseProvider]:
    if model_provider not in _CACHE:
        provider = _provider_for(model_provider)
        _CACHE[model_provider] = (build_answer_graph(provider), provider)
    return _CACHE[model_provider]


def answer(req: api_c.AnswerRequest, model_provider: str = "mock") -> api_c.Answer:
    graph, provider = _graph_for(model_provider)
    thread_id = req.thread_id or f"t-{uuid.uuid4().hex[:12]}"
    as_of = req.as_of or date.today().isoformat()
    cfg = {"configurable": {"thread_id": thread_id}}

    t0 = time.perf_counter()
    out = graph.invoke({"question": req.question, "as_of": as_of}, cfg)
    latency_ms = int((time.perf_counter() - t0) * 1000)

    interrupted = bool(out.get("__interrupt__"))
    status: api_c.AnswerStatus = "pending_human" if interrupted else out.get("status", "rejected")

    answer_obj = out.get("answer")
    hits_by_id = {hit.chunk_id: hit for hit in out.get("hits", [])}
    faults = out.get("faults", [])

    claims: list[api_c.Claim] = []
    if answer_obj:
        for claim in answer_obj.claims:
            hit = hits_by_id.get(claim.chunk_id)
            if hit is None:
                continue  # no deberia pasar si `verify` corrio antes; defensivo, nunca se inventa el chunk
            claims.append(api_c.Claim(
                text=claim.text, chunk_id=claim.chunk_id, article_id=hit.article_id, quote=claim.quote,
                citation=hit.citation, valid_from=hit.valid_from or "", valid_to=hit.valid_to,
                verified=not faults,
            ))

    summary = (
        claims[0].text if claims
        else "No encontré una norma del corpus que fije eso con suficiente confianza."
    )
    grade = out.get("grade")
    weights: RouteWeights | None = out.get("route_weights")

    return api_c.Answer(
        thread_id=thread_id,
        status=status,
        risk=out.get("risk") or "auto",
        as_of=as_of,
        summary=summary,
        claims=claims,
        history=[],
        trace=api_c.Trace(
            scenario=out.get("scenario", "lookup"),
            seen=out.get("seen", []),
            lists={"fused": len(out.get("hits", []))},  # lexical+entidades ya fundidos; sin ppr real todavia
            ppr_new=0,
            route_weights=weights.model_dump() if weights else {},
            confidence_label=grade.label if grade else None,
            confidence_score=grade.score if grade else None,
            faults=[fault.kind for fault in faults],
            fixes=out.get("fixes", 0),
            latency_ms=latency_ms,
            cost_usd=0.0,
            model=provider.name,
            prompt_version="agent-v0",
        ),
    )
