"""Contratos del agente de respuesta: lo que entra y sale de cada nodo (docs/09-agents.md).

Pydantic valida lo que toca al modelo (`Answer`, `Claim`); el estado de LangGraph es un `TypedDict` chico, con
referencias (ids), nunca copias de textos enteros. Nombres en ingles (valores y codigo); docstrings en espanol.
"""

from __future__ import annotations

from typing import Literal, TypedDict

from pydantic import BaseModel, Field

Scenario = Literal[
    "lookup", "definition", "threshold", "procedure", "validity",
    "crossref", "policy_vs_norm", "impact", "negative",
]
GradeLabel = Literal["ok", "ambiguous", "no_evidence"]
RiskLevel = Literal["auto", "notify", "approve"]
FaultKind = Literal[
    "quote_missing", "quote_altered", "foreign_fact", "not_seen",
    "not_in_force", "fake_consistency", "inappropriate_language",
]
RunStatus = Literal["ok", "abstained", "rejected", "pending_human", "quota_deferred"]
HumanAction = Literal["accept", "edit", "reject"]


class Hit(BaseModel):
    """Un chunk recuperado, con lo minimo para citar y verificar (docs/08-retrieval.md)."""

    chunk_id: str
    norm_id: str
    norm_short: str
    article_id: str
    citation: str
    text: str
    valid_from: str | None  # algunas fuentes todavia no tienen fecha de publicacion resuelta (data/corpus_v0)
    valid_to: str | None
    score: float


class RouteWeights(BaseModel):
    """Cuanto pesa cada canal de busqueda; nunca excluye uno, solo lo pondera mas o menos.

    docs/README.md, principio 2: "el grafo suma, no filtra". Esto es lo que hace `read` ademas de clasificar
    el escenario, para que `fuse`/`fuse2` (docs/08-retrieval.md) pesen distinto segun el tipo de pregunta.
    """

    dense: float = 1.0
    bm25: float = 0.3
    entities: float = 0.3
    ppr: float = 0.3


class GradeResult(BaseModel):
    """Salida del nodo `grade`: categoria (lo que decide el ruteo) y numero (lo que se muestra en la UI)."""

    label: GradeLabel
    score: float


class Claim(BaseModel):
    """Una afirmacion = una cita; `quote` debe existir literal en el texto del chunk citado."""

    text: str
    chunk_id: str
    quote: str


class Answer(BaseModel):
    """Lo que redacta el modelo en el nodo `answer`. `risk_hint` es un piso, nunca baja lo que diga `risk_rules.csv`."""

    claims: list[Claim] = Field(default_factory=list)
    as_of: str
    abstain: bool = False
    risk_hint: RiskLevel = "auto"


class Fault(BaseModel):
    """Una falta tipada que `verify` encontro; nunca se corrige en silencio, se muestra al modelo o se rechaza."""

    kind: FaultKind
    detail: str


class HumanResponse(BaseModel):
    """Lo que devuelve la persona al reanudar un `interrupt()` (docs/09-agents.md)."""

    type: HumanAction
    note: str | None = None


class State(TypedDict, total=False):
    """Estado de `answer_graph`. Chico: ids y resultados, no documentos enteros."""

    question: str
    as_of: str
    started_at: float  # time.perf_counter() en `read`; `ledger` lo resta para la latencia (docs/10-evaluation.md)
    scenario: Scenario
    route_weights: RouteWeights
    hits: list[Hit]
    seen: list[str]
    grade: GradeResult
    answer: Answer | None
    faults: list[Fault]
    fixes: int
    risk: RiskLevel
    human: HumanResponse | None
    cost_usd: float
    status: RunStatus
