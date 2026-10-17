"""API con el corpus y el agente reales (en vez de la maqueta): `REGULABANK_RELEASE=<dir del release> uvicorn ...`.

Lee el release (chunks.parquet + lancedb/ + grafo en Parquet) que arma `python -m regulabank.graphs build`, carga el
embedder una vez y responde con `AnswerAgent`. Proveedor del modelo: `MODEL_PROVIDER=mock|openai` (openai = gpt-5-mini).
"""

from __future__ import annotations

import os
from collections import defaultdict
from pathlib import Path

from regulabank.agents.answer import AnswerAgent
from regulabank.agents.llm import load_provider
from regulabank.api import contracts as c
from regulabank.graphs import embed as embed_mod
from regulabank.retrieval.search import Retriever
from regulabank.shared import config

KIND_TOPICS = {}


class Live:
    def __init__(self, release: Path, provider_kind: str | None = None):
        settings = config.load()
        emb = embed_mod.load_embedder(settings.embed_model, "intfloat/multilingual-e5-small", 32)
        self.retriever = Retriever(release, emb)
        self.retriever.p["top_k"] = 8
        provider = load_provider(provider_kind, cache_dir=release / "llm-cache")
        from regulabank.agents import answer as answer_mod
        self.agent = AnswerAgent(self.retriever, provider, default_strategy="dense_valid",
                                 mean6_floor=float(self.retriever.params.get("grade", {}).get("mean6_floor", 0)) or None,
                                 ledger_path=release / "ledger.jsonl")
        self.agent.route = answer_mod.load_route()
        self.by_norm: dict[str, list[dict]] = defaultdict(list)
        self.by_article: dict[str, list[dict]] = defaultdict(list)
        for row in self.retriever.rows.values():
            self.by_norm[row["norm_id"]].append(row)
            self.by_article[row["article_id"]].append(row)

    def norms(self) -> list[c.NormSummary]:
        out = []
        for nid, rows in self.by_norm.items():
            r = rows[0]
            out.append(c.NormSummary(id=nid, short=r["norm_short"], title=r["title"], kind=r["norm_kind"], issuer=r["issuer"] or "",
                                     published=r["published"] or "", status=r["status"],
                                     n_articles=len({x["article_id"] for x in rows}), topics=[]))
        return sorted(out, key=lambda n: n.short)

    def _article(self, article_id: str) -> c.Article | None:
        rows = self.by_article.get(article_id)
        if not rows:
            return None
        rows = sorted(rows, key=lambda r: (r["page_start"] or 0, r["chunk_id"]))
        r0 = rows[0]
        v = c.Version(id=article_id + "@v1", n=1, valid_from=r0["valid_from"] or r0["published"] or "", valid_to=r0["valid_to"],
                      change_kind="original", changed_by=None, text="\n".join(r["text"] for r in rows))
        refs = sorted({d for r in rows for d in self.retriever.refers.get(r["chunk_id"], [])})
        return c.Article(id=article_id, norm_id=r0["norm_id"], no=r0["article_no"] or "", path=r0["parent_path"] or "", current=v,
                         versions=[v], refers_to=refs, entities=[])

    def article(self, article_id: str) -> c.Article | None:
        return self._article(article_id)

    def norm(self, norm_id: str) -> c.NormDetail | None:
        rows = self.by_norm.get(norm_id)
        if not rows:
            return None
        summary = next(n for n in self.norms() if n.id == norm_id)
        arts = [a for a in (self._article(i) for i in dict.fromkeys(r["article_id"] for r in rows)) if a]
        return c.NormDetail(**summary.model_dump(), articles=arts)

    def answer(self, req: c.AnswerRequest) -> c.Answer:
        s = self.agent.ask(req.question, req.as_of, req.thread_id)
        rows = self.retriever.rows
        claims = []
        for cl in s.get("claims", []):
            row = rows[cl["chunk_id"]]
            claims.append(c.Claim(text=cl["text"], chunk_id=cl["chunk_id"], article_id=row["article_id"], quote=cl["quote"],
                                  citation=cl["citation"], valid_from=cl["valid_from"] or "", valid_to=cl["valid_to"],
                                  verified=bool(cl["verified"])))
        history = []
        for h in s.get("hits", []):
            for it in self.retriever._history.get(h.chunk_id, []):
                row = rows[it.chunk_id]
                history.append(c.HistoryItem(article_id=row["article_id"], citation=row["citation"], valid_from=it.valid_from or "",
                                             valid_to=it.valid_to, change_kind="replaced", changed_by=None))
        u = s.get("usage", {})
        trace = c.Trace(scenario=s["scenario"], seen=[h.chunk_id for h in s.get("hits", [])], lists=s.get("lists", {}),
                        ppr_new=s.get("ppr_new", 0), faults=[f["kind"] for f in s.get("faults", [])], fixes=s.get("fixes", 0),
                        latency_ms=s["timings_ms"].get("total", 0), cost_usd=u.get("cost_usd", 0.0), model=u.get("model", "none"),
                        prompt_version="answer-v1")
        return c.Answer(thread_id=s["thread_id"], status=s["status"], risk=s["risk"], as_of=s["as_of"], summary=s["summary"],
                        claims=claims, history=history, trace=trace)


def maybe_live() -> Live | None:
    rel = os.environ.get("REGULABANK_RELEASE")
    return Live(Path(rel)) if rel else None
