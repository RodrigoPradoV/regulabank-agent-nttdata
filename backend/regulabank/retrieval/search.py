"""De la pregunta a los 8 chunks con cita (docs/08-retrieval.md). Codigo determinista + embedding; sin LLM.

question, as_of -> read -> understand -> candidates -> fuse -> ppr -> fuse2 -> dedup -> validity -> contracts -> cites

- read: normas nombradas en la pregunta (regex `norm_ref` + alias) y `as_of` (explicito o hoy).
- understand: n-gramas (hasta 5 palabras) normalizados contra las entidades del grafo; ancla el mas largo que tenga
  alguna palabra fuera de las stop medidas en el corpus (df > 5 %).
- candidates: dense (LanceDB, coseno), bm25 (FTS espanol), entities (suma de idf), norm (denso filtrado a las
  normas nombradas).
- fuse: RRF ponderada; ppr: PageRank personalizado sembrado con entidades y los mejores de fuse; fuse2 con ppr.
- dedup por texto y por articulo; validity: unica regla dura, un chunk fuera de vigencia a `as_of` pasa a `history`.
- contracts (version minima): tope por norma y TOP_K. Los lugares asegurados por escenario no estan implementados.
- cites: por chunk, la oracion con mayor coseno a la pregunta (<= quote_max_chars); verificada contra el texto.

Salida: `Hit` y `Trace` (la traza explica «por que este articulo»).
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow.parquet as pq

from regulabank.graphs import embed as embed_mod
from regulabank.graphs import params as params_mod
from regulabank.graphs import ppr as ppr_mod
from regulabank.graphs.edges import idf
from regulabank.graphs.entities import NormAliases, _sentence_bounds, extract_norm_refs, norm_key


def _norm_text(text: str) -> str:
    return " ".join(text.lower().split())


def _words(text: str) -> list[str]:
    return re.findall(r"\w+", text.lower())


@dataclass
class HistoryItem:
    chunk_id: str
    valid_from: str | None
    valid_to: str | None


@dataclass
class Hit:
    chunk_id: str
    norm_id: str
    norm_short: str
    article_no: str | None
    path: str | None
    citation: str          # «texto literal» {Res. SBS ..., art. 12, p. 4 | vigente desde ...}
    text: str
    quote: str             # tramo literal de `text` (verificado)
    quote_verified: bool
    score: float
    sources: dict[str, int]    # lista -> rango (1 = mejor) en que aparecio
    valid_from: str | None
    valid_to: str | None
    is_current: bool
    history: list[HistoryItem] = field(default_factory=list)
    refers_to: list[str] = field(default_factory=list)
    entities: list[str] = field(default_factory=list)


@dataclass
class Trace:
    question: str
    as_of: str
    norms_named: list[str]
    anchors: list[str]
    lists: dict[str, list[str]]
    fused: list[str]
    ppr_new: list[str]
    dedup_dropped: int
    validity_moved: int
    evidence_mean6: float | None
    timings_ms: dict[str, float]
    params_hash: str


@dataclass
class Result:
    hits: list[Hit]
    trace: Trace

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, indent=2, default=str)


def verify_quote(quote: str, text: str) -> bool:
    """La cita es un tramo literal del chunk (tras normalizar espacios)."""
    return bool(quote) and _norm_text(quote) in _norm_text(text)


class Retriever:
    def __init__(self, release: Path, embedder: Any | None = None, params: dict[str, Any] | None = None,
                 norms_csv: Path | None = None):
        self.params = params or params_mod.load()
        self.p = self.params["retrieval"]
        self.release = release
        self.chunks = pq.read_table(release / "chunks.parquet")
        self.entities = pq.read_table(release / "entities.parquet")
        self.mentions = pq.read_table(release / "mentions.parquet")
        self.edges = pq.read_table(release / "edges.parquet")
        self.rows = {r["chunk_id"]: r for r in self.chunks.to_pylist()}
        self.order = list(self.rows)
        self.graph = ppr_mod.build_graph(self.chunks, self.entities, self.edges)
        import lancedb  # noqa: PLC0415

        self.table = lancedb.connect(str(release / "lancedb")).open_table("chunks")
        self.embedder = embedder
        self.aliases = NormAliases.from_csv(norms_csv) if norms_csv else NormAliases.from_csv()
        n = self.chunks.num_rows
        # entidades: clave -> ids, idf, y chunks que las mencionan
        self.by_key: dict[str, list[str]] = defaultdict(list)
        for r in self.entities.select(["entity_id", "type", "key", "name"]).to_pylist():
            self.by_key[norm_key(r["name"])].append(r["entity_id"])
        self.chunks_of: dict[str, set[str]] = defaultdict(set)
        for r in self.mentions.select(["chunk_id", "entity_id"]).to_pylist():
            self.chunks_of[r["entity_id"]].add(r["chunk_id"])
        self.idf = {e: idf(n, len(c)) for e, c in self.chunks_of.items()}
        self.entities_of: dict[str, list[str]] = defaultdict(list)
        for e, cs in self.chunks_of.items():
            for c in cs:
                self.entities_of[c].append(e)
        df: dict[str, int] = defaultdict(int)
        for r in self.rows.values():
            for w in set(_words(r["text"])):
                df[w] += 1
        self.stop = {w for w, c in df.items() if c / n > float(self.p["stop_df_fraction"])}
        self.refers: dict[str, list[str]] = defaultdict(list)
        for e in self.edges.to_pylist():
            if e["type"] == "REFERS_TO":
                self.refers[e["src"]].append(e["dst"])
        self.params_hash = hashlib.sha256(json.dumps(self.p, sort_keys=True, default=str).encode()).hexdigest()[:12]

    # ---- read / understand -------------------------------------------------------------------------------
    def read(self, question: str) -> list[str]:
        named = []
        for m in extract_norm_refs(question, "q", self.aliases):
            nid = (m.value or {}).get("norm_id")
            if nid and nid in {r["norm_id"] for r in self.rows.values()} and nid not in named:
                named.append(nid)
        return named

    def understand(self, question: str) -> list[str]:
        words = _words(question)
        taken: set[int] = set()
        anchors: list[str] = []
        for n in range(int(self.p["ngram_max"]), 0, -1):
            for i in range(len(words) - n + 1):
                span = range(i, i + n)
                if any(j in taken for j in span):
                    continue
                gram = words[i:i + n]
                if all(w in self.stop for w in gram):
                    continue
                for ent in self.by_key.get(norm_key(" ".join(gram)), []):
                    anchors.append(ent)
                    taken.update(span)
        return list(dict.fromkeys(anchors))

    # ---- candidates --------------------------------------------------------------------------------------
    def candidates(self, question: str, qvec: np.ndarray, anchors: list[str], norms: list[str]) -> dict[str, list[str]]:
        k = int(self.p["cand_k"])
        lists: dict[str, list[str]] = {}
        lists["dense"] = [r["chunk_id"] for r in self.table.search(qvec.tolist()).metric("cosine").limit(k).to_list()]
        try:
            lists["bm25"] = [r["chunk_id"] for r in
                             self.table.search(question, query_type="fts").limit(k).to_list()]
        except Exception:  # noqa: BLE001 - pregunta sin terminos indexables
            lists["bm25"] = []
        score: dict[str, float] = defaultdict(float)
        for ent in anchors:
            for c in self.chunks_of.get(ent, ()):
                score[c] += max(self.idf.get(ent, 0.0), 0.0)
        lists["entities"] = [c for c, _ in sorted(score.items(), key=lambda kv: -kv[1])[:k]]
        if norms:
            quoted = ", ".join("'" + n.replace("'", "''") + "'" for n in norms)
            lists["norm"] = [r["chunk_id"] for r in
                             self.table.search(qvec.tolist()).metric("cosine").where(f"norm_id IN ({quoted})")
                             .limit(k).to_list()]
        return lists

    def fuse(self, lists: dict[str, list[str]], weights: dict[str, float], limit: int) -> list[tuple[str, float]]:
        rrf = float(self.p["rrf_k"])
        score: dict[str, float] = defaultdict(float)
        for name, ids in lists.items():
            w = float(weights.get(name, 0.0))
            for rank, cid in enumerate(ids, start=1):
                score[cid] += w / (rrf + rank)
        return sorted(score.items(), key=lambda kv: -kv[1])[:limit]

    # ---- dedup / validity / contracts --------------------------------------------------------------------
    @staticmethod
    def _current(row: dict[str, Any], as_of: str) -> bool:
        vf, vt = row["valid_from"], row["valid_to"]
        return (not vf or vf <= as_of) and (not vt or as_of < vt)

    def dedup_validity(self, ranked: list[tuple[str, float]], as_of: str) -> tuple[list, int, int]:
        seen_text: set[str] = set()
        kept: list[tuple[str, float]] = []
        dropped = 0
        n = int(self.p["dedup_chars"])
        for cid, s in ranked:
            key = _norm_text(self.rows[cid]["text"])[:n]
            if key in seen_text:
                dropped += 1
                continue
            seen_text.add(key)
            kept.append((cid, s))
        groups: dict[str, list[tuple[str, float]]] = defaultdict(list)
        for cid, s in kept:
            groups[self.rows[cid]["article_id"]].append((cid, s))
        out, moved = [], 0
        history: dict[str, list[HistoryItem]] = {}
        for art, members in groups.items():
            current = [m for m in members if self._current(self.rows[m[0]], as_of)]
            stale = [m for m in members if m not in current]
            if current:
                rep = max(current, key=lambda m: m[1])
                history[rep[0]] = [HistoryItem(c, self.rows[c]["valid_from"], self.rows[c]["valid_to"])
                                   for c, _ in stale]
                moved += len(stale)
                out.extend(current)
            else:
                out.extend(members)
        self._history = history
        return sorted(out, key=lambda m: -m[1]), dropped, moved

    def contracts(self, ranked: list[tuple[str, float]]) -> list[tuple[str, float]]:
        cap, k = int(self.p["per_norm"]), int(self.p["top_k"])
        per: dict[str, int] = defaultdict(int)
        out = []
        for cid, s in ranked:
            norm = self.rows[cid]["norm_id"]
            if per[norm] >= cap:
                continue
            per[norm] += 1
            out.append((cid, s))
            if len(out) == k:
                break
        return out

    # ---- citas -------------------------------------------------------------------------------------------
    def own_quote(self, question_vec: np.ndarray, text: str) -> str:
        """La oracion con mayor coseno a la pregunta, recortada a `quote_max_chars` (siempre tramo literal)."""
        bounds = [(s, e) for s, e in _sentence_bounds(text) if text[s:e].strip()]
        if not bounds:
            return text[:int(self.p["quote_max_chars"])].strip()
        sentences = [text[s:e].strip() for s, e in bounds]
        vecs = self.embedder.encode(sentences)
        best = int(np.argmax(vecs @ question_vec))
        start = text.index(sentences[best])
        return text[start:start + int(self.p["quote_max_chars"])].strip() if len(sentences[best]) > int(
            self.p["quote_max_chars"]) else sentences[best]

    def cite(self, row: dict[str, Any], quote: str) -> str:
        tail = row["citation"] or row["norm_short"]
        if row["valid_from"]:
            tail += f" | vigente desde {row['valid_from']}"
        return f"«{quote}» {{{tail}}}"

    # ---- principal ---------------------------------------------------------------------------------------
    def search(self, question: str, as_of: str | None = None) -> Result:
        t: dict[str, float] = {}
        t0 = time.perf_counter()

        def lap(name: str) -> None:
            nonlocal t0
            now = time.perf_counter()
            t[name] = round((now - t0) * 1000, 1)
            t0 = now

        as_of = as_of or date.today().isoformat()
        norms = self.read(question)
        anchors = self.understand(question)
        lap("read_understand")
        qvec = embed_mod.embed_query(question, self.embedder)
        lap("embed")
        weights = self.params["retrieval"]["weights"]
        lists = self.candidates(question, qvec, anchors, norms)
        lap("candidates")
        fused = self.fuse(lists, weights, int(self.p["fused_k"]))
        lap("fuse")
        seeds = {e: max(self.idf.get(e, 0.0), 0.1) for e in anchors}
        for rank, (cid, _) in enumerate(fused[:int(self.p["ppr_seed_top"])], start=1):
            seeds[cid] = 1.0 / rank
        pp = self.params["ppr"]
        scores = ppr_mod.personalized_pagerank(self.graph, seeds, alpha=float(pp["alpha"]), iters=int(pp["iters"]))
        ppr_ids = [n for n, _ in ppr_mod.top(scores, self.graph, "chunk", int(self.p["cand_k"]))]
        lap("ppr")
        in_fused = {c for c, _ in fused}
        new = [c for c in ppr_ids if c not in in_fused][:int(self.p["ppr_new"])]
        lists2 = {**lists, "ppr": ppr_ids}
        fused2 = self.fuse(lists2, weights, int(self.p["fused_k"]) + len(new))
        lap("fuse2")
        ranked, dropped, moved = self.dedup_validity(fused2, as_of)
        top = self.contracts(ranked)
        lap("dedup_validity_contracts")
        hits = []
        for cid, s in top:
            row = self.rows[cid]
            quote = self.own_quote(qvec, row["text"])
            ok = verify_quote(quote, row["text"])
            hits.append(Hit(
                chunk_id=cid, norm_id=row["norm_id"], norm_short=row["norm_short"], article_no=row["article_no"],
                path=row["parent_path"], citation=self.cite(row, quote), text=row["text"], quote=quote,
                quote_verified=ok, score=float(s),
                sources={n: ids.index(cid) + 1 for n, ids in lists2.items() if cid in ids},
                valid_from=row["valid_from"], valid_to=row["valid_to"], is_current=self._current(row, as_of),
                history=self._history.get(cid, []), refers_to=self.refers.get(cid, []),
                entities=sorted(self.entities_of.get(cid, []), key=lambda e: -self.idf.get(e, 0.0))[:8]))
        lap("cites")
        dense = self.table.search(qvec.tolist()).metric("cosine").limit(6).to_list()
        mean6 = float(np.mean([1.0 - r["_distance"] for r in dense])) if dense else None
        trace = Trace(question, as_of, norms, anchors, lists2, [c for c, _ in fused2], new, dropped, moved, mean6, t,
                      self.params_hash)
        return Result(hits, trace)
