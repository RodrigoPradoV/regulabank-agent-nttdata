"""Contratos de la API (Pydantic). El frontend solo conoce estas formas; schema_version las versiona."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

SCHEMA_VERSION = "0.1.0"

NormKind = Literal["law", "legislative_decree", "supreme_decree", "sbs_resolution", "sbs_circular", "bcrp_circular",
                   "internal_policy", "international_standard", "international_guideline", "eu_regulation", "standard"]
RiskLevel = Literal["auto", "notify", "approve"]
AnswerStatus = Literal["ok", "abstained", "rejected", "pending_human"]


class NormSummary(BaseModel):
    id: str
    short: str
    title: str
    kind: NormKind
    issuer: str
    published: str
    status: Literal["in_force", "repealed", "partial", "scheduled"]
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
    n: int = 0                  # numero [n] con que el texto cita este fragmento
    norm_short: str = ""
    article_no: str = ""
    is_current: bool = True


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
    faults: list[str]
    fixes: int
    latency_ms: int
    cost_usd: float
    model: str
    prompt_version: str
    tool_calls: int = 0
    models: list[str] = Field(default_factory=list)   # modelos usados, en orden (el agente puede escalar)


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
