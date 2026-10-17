"""Contratos de la API (Pydantic). El frontend solo conoce estas formas; schema_version las versiona."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

SCHEMA_VERSION = "0.1.0"

NormKind = Literal["law", "sbs_resolution", "sbs_circular", "bcrp_circular", "internal_policy"]
RiskLevel = Literal["auto", "notify", "approve"]
AnswerStatus = Literal["ok", "abstained", "rejected", "pending_human"]


class NormSummary(BaseModel):
    id: str
    short: str
    title: str
    kind: NormKind
    issuer: str
    published: str
    status: Literal["in_force", "repealed", "partial"]
    n_articles: int
    topics: list[str] = Field(default_factory=list)


class Version(BaseModel):
    id: str
    n: int
    valid_from: str
    valid_to: str | None
    change_kind: Literal["original", "modified", "replaced", "repealed", "added"]
    changed_by: str | None
    text: str


class Article(BaseModel):
    id: str
    norm_id: str
    no: str
    path: str
    current: Version
    versions: list[Version]
    refers_to: list[str] = Field(default_factory=list)
    entities: list[str] = Field(default_factory=list)


class NormDetail(NormSummary):
    articles: list[Article]


class AnswerRequest(BaseModel):
    question: str = Field(min_length=3)
    as_of: str | None = None
    thread_id: str | None = None


class Claim(BaseModel):
    text: str
    chunk_id: str
    article_id: str
    quote: str
    citation: str
    valid_from: str
    valid_to: str | None
    verified: bool


class HistoryItem(BaseModel):
    article_id: str
    citation: str
    valid_from: str
    valid_to: str | None
    change_kind: str
    changed_by: str | None


class Trace(BaseModel):
    scenario: str
    seen: list[str]
    lists: dict[str, int]
    ppr_new: int
    route_weights: dict[str, float] = Field(default_factory=dict)  # dense/bm25/entities/ppr; nunca excluyente
    confidence_label: Literal["ok", "ambiguous", "no_evidence"] | None = None  # salida de `grade` (agents/grade.py)
    confidence_score: float | None = None  # evidence.mean6, 0 a 1; mismo origen que confidence_label
    faults: list[str]
    fixes: int
    latency_ms: int
    cost_usd: float
    model: str
    prompt_version: str


class Answer(BaseModel):
    schema_version: str = SCHEMA_VERSION
    thread_id: str
    status: AnswerStatus
    risk: RiskLevel
    as_of: str
    summary: str
    claims: list[Claim]
    history: list[HistoryItem]
    trace: Trace


class Conflict(BaseModel):
    id: str
    policy_chunk_id: str
    policy_citation: str
    policy_quote: str
    norm_version_id: str
    norm_citation: str
    norm_quote: str
    relation: Literal["contradicts", "stricter", "complies", "unrelated"]
    method: Literal["rules", "nli", "judge", "human"]
    score: float
    reason: str
    status: Literal["pending_human", "confirmed", "dismissed"]


class Decision(BaseModel):
    action: Literal["accept", "edit", "reject"]
    note: str | None = None


class MetricsSummary(BaseModel):
    total: int
    by_status: dict[str, int]
    by_risk: dict[str, int]
    by_scenario: dict[str, int]
    fault_counts: dict[str, int]
    fixes_histogram: dict[str, int]
    human_review_rate: float
    latency_ms_avg: float
    latency_ms_p50: float
    latency_ms_p95: float
    time_saved_minutes: float
    human_baseline_minutes: float


class MetricsSeriesPoint(BaseModel):
    bucket: str
    count: int
    latency_ms_avg: float
    abstained: int
    rejected: int


class MetricsEntry(BaseModel):
    logged_at: str
    question: str | None = None
    as_of: str | None = None
    scenario: str | None = None
    status: str | None = None
    risk: str | None = None
    latency_ms: int | None = None
    fixes: int = 0
    faults: list[str] = Field(default_factory=list)
    human_decision: str | None = None
    model: str | None = None
    seen: list[str] = Field(default_factory=list)


class MetricsResponse(BaseModel):
    summary: MetricsSummary
    series: list[MetricsSeriesPoint]
    entries: list[MetricsEntry]
