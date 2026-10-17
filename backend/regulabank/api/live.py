"""API con el corpus y el agente reales (en vez de la maqueta): `REGULABANK_RELEASE=<dir del release> uvicorn ...`.

Lee el release (chunks.parquet + lancedb/ + grafo en Parquet) que arma `python -m regulabank.graphs build`, carga el
embedder una vez y responde con `AnswerAgent`. Proveedor del modelo: `MODEL_PROVIDER=mock|openai` (openai = gpt-5-mini).
"""

from __future__ import annotations

import os
from collections import defaultdict
from pathlib import Path

import pyarrow.parquet as pq

from regulabank.agents.agentic import PROMPT_VERSION, STARTER_SYSTEM, AgenticAgent, load_conflicts, parse_questions
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
        self.release = release
        self.retriever = Retriever(release, emb)
        self.retriever.p["top_k"] = 8
        provider = load_provider(provider_kind, cache_dir=release / "llm-cache")
        self.agent = AgenticAgent(self.retriever, provider, conflicts=load_conflicts(release / "conflicts.parquet"),
                                  ledger_path=release / "ledger.jsonl",
                                  evidence_floor=self.retriever.params.get("grade", {}).get("evidence_floor"))
        self._load_conflicts(release)
        self.by_norm: dict[str, list[dict]] = defaultdict(list)
        self.by_article: dict[str, list[dict]] = defaultdict(list)
        for row in self.retriever.rows.values():
            self.by_norm[row["norm_id"]].append(row)
            self.by_article[row["article_id"]].append(row)

    def _load_conflicts(self, release: Path, limit: int = 60, p_min: float = 0.99) -> None:
        """Conflictos de la tabla NLI (release/conflicts.parquet): los de mayor probabilidad, sin validar."""
        self._conflicts: dict[str, c.Conflict] = {}
        path = release / "conflicts.parquet"
        if not path.exists():
            return
        rows = [r for r in pq.read_table(path).to_pylist() if r["label"] == "contradiction" and r["p_contradiction"] >= p_min]
        rows.sort(key=lambda r: -r["p_contradiction"])
        seen: set = set()
        for r in rows:
            key = (r["chunk_a"], r["chunk_b"])
            if key in seen:
                continue
            seen.add(key)
            a, b = self.retriever.rows[r["chunk_a"]], self.retriever.rows[r["chunk_b"]]
            self._conflicts[r["pair_id"]] = c.Conflict(
                id=r["pair_id"], policy_chunk_id=r["chunk_a"], policy_citation=a["citation"], policy_quote=r["premise"],
                norm_version_id=r["chunk_b"], norm_citation=b["citation"], norm_quote=r["hypothesis"], relation="contradicts",
                method="nli", score=round(float(r["p_contradiction"]), 4),
                reason=f"RoBERTa XNLI: contradicción (p = {r['p_contradiction']:.3f}) sobre «{r['entity_id'].split(':', 1)[-1]}». Sin validar con etiquetas.",
                status="pending_human")
            if len(self._conflicts) >= limit:
                break

    def conflicts(self) -> list[c.Conflict]:
        return list(self._conflicts.values())

    def decide(self, conflict_id: str, d: c.Decision) -> c.Conflict | None:
        cf = self._conflicts.get(conflict_id)
        if cf is None:
            return None
        cf.status = "dismissed" if d.action == "reject" else "confirmed"
        return cf

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

    def suggestions(self, fresh: bool = False) -> list[str]:
        """Preguntas para empezar, propuestas por el modelo a partir de fragmentos de normas distintas (cache en release/suggestions.json)."""
        import json as _json
        import random

        path = self.release / "suggestions.json"
        if not fresh and path.exists():
            return _json.loads(path.read_text(encoding="utf-8"))["questions"]
        rows = [r for r in self.retriever.rows.values() if 500 <= len(r["text"]) <= 1600 and r["node_type"] in ("article", "numbered_section", "numeral", "recommendation")]
        by_norm: dict[str, list[dict]] = defaultdict(list)
        for r in rows:
            by_norm[r["norm_id"]].append(r)
        rng = random.Random()
        norms = rng.sample(sorted(by_norm), k=min(9, len(by_norm)))
        frag = "\n\n".join(f"[{r['citation']}]\n{' '.join(r['text'].split())[:420]}" for r in (rng.choice(by_norm[n]) for n in norms))
        try:
            reply = self.agent.provider.chat([{"role": "system", "content": STARTER_SYSTEM}, {"role": "user", "content": "Fragmentos:\n" + frag}],
                                             None, PROMPT_VERSION + "-starter-" + str(rng.random()), model=self.agent.models[0],
                                             effort="minimal")
            qs = parse_questions(reply.message.get("content") or "", "", limit=6)
        except Exception:  # noqa: BLE001 - sin modelo no hay sugerencias nuevas; se devuelven las guardadas
            qs = []
        if len(qs) >= 4:
            path.write_text(_json.dumps({"questions": qs}, ensure_ascii=False), encoding="utf-8")
            return qs
        return _json.loads(path.read_text(encoding="utf-8"))["questions"] if path.exists() else []

    def _to_answer(self, s: dict, events: list[dict]) -> c.Answer:
        rows = self.retriever.rows
        claims = []
        for cl in s.get("claims", []):
            row = rows[cl["chunk_id"]]
            claims.append(c.Claim(text=cl["text"], chunk_id=cl["chunk_id"], article_id=row["article_id"], quote=cl["quote"],
                                  citation=cl["citation"], valid_from=cl["valid_from"] or "", valid_to=cl["valid_to"],
                                  verified=bool(cl["verified"]), n=cl["n"], norm_short=row["norm_short"],
                                  article_no=row["article_no"] or "", is_current=bool(cl["is_current"])))
        u = s.get("usage", {})
        models = [self.agent.models[0]] + [e["to"] for e in events if e.get("type") == "model"]
        trace = c.Trace(scenario=s["scenario"], seen=[h.chunk_id for h in s.get("hits", [])],
                        lists={"search": s["tb"].n_search, "herramientas": s.get("calls", 0)}, ppr_new=0,
                        faults=[f["kind"] for f in s.get("faults", [])], fixes=s.get("fixes", 0),
                        latency_ms=s["timings_ms"].get("total", 0), cost_usd=u.get("cost_usd", 0.0), model=u.get("model", "none"),
                        prompt_version=PROMPT_VERSION, tool_calls=s.get("calls", 0), models=models)
        return c.Answer(thread_id=s["thread_id"], status=s["status"], risk=s["risk"], as_of=s["as_of"], summary=s["summary"],
                        claims=claims, history=[], trace=trace, follow_ups=s.get("follow_ups", []))

    def answer(self, req: c.AnswerRequest) -> c.Answer:
        events: list[dict] = []
        final: dict = {}
        for kind, payload in self.agent.run(req.question, req.as_of, req.thread_id):
            if kind == "event":
                events.append(payload)
            else:
                final = payload
        return self._to_answer(final, events)

    def stream(self, req: c.AnswerRequest):
        """Server-Sent Events: un evento por paso del agente y al final `final` con la respuesta completa."""
        import json as _json

        def sse(d: dict) -> str:
            return "data: " + _json.dumps(d, ensure_ascii=False, default=str) + "\n\n"

        events: list[dict] = []
        final: dict | None = None
        try:
            for kind, payload in self.agent.run(req.question, req.as_of, req.thread_id):
                if kind == "event":
                    events.append(payload)
                    yield sse(payload)
                else:
                    final = payload
            yield sse({"type": "final", "answer": self._to_answer(final or {}, events).model_dump()})
        except Exception as exc:  # noqa: BLE001 - el error llega a la interfaz como evento, no como corte de la conexion
            yield sse({"type": "error", "message": f"{type(exc).__name__}: {str(exc)[:300]}"})


def maybe_live() -> Live | None:
    rel = os.environ.get("REGULABANK_RELEASE")
    return Live(Path(rel)) if rel else None
