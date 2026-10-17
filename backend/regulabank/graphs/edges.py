"""EDGES: NEXT, REFERS_TO, SIMILAR (focus) y MENTIONS (lens). Pesos en seeds/params.toml.

- NEXT: filas consecutivas de chunks.parquet con el mismo norm_id (el release ya viene en orden de lectura).
- REFERS_TO: chunk -> articulo (`article_id`) o norma del corpus, desde las menciones regex; «artículos 8 al 12»
  se expande con `range_from`; sin norma nombrada el destino es la misma norma. Lo no resuelto se cuenta en
  `stats["refers_to_unresolved"]` (docs/05-relations.md: «unresolved y se lista»).
- MENTIONS: chunk -> entidad con peso idf (piso `mentions_floor`). Ya conecta chunk -> entidad -> chunk, por eso
  no hay SHARES_ENTITY.
- SIMILAR: kNN por coseno (k = `similar_k`) excluyendo el mismo articulo; con una tabla LanceDB se consulta ahi,
  si no se calcula con numpy sobre los vectores alineados a `chunks`.

Invariantes: sin bucles, src y dst existen en el release, peso > 0, una fila por (src, dst, type).
"""

from __future__ import annotations

import json
import math
from collections import defaultdict
from typing import Any

import numpy as np
import pyarrow as pa

from regulabank.graphs import aggregate
from regulabank.graphs import params as params_mod
from regulabank.graphs.entities import expand_range
from regulabank.shared import schema


def idf(n_chunks: int, df: int) -> float:
    """log(n/(1+df)): una entidad presente en casi todo pesa cero o menos (docs/06-graphs.md)."""
    return math.log(n_chunks / (1 + df))


def _edge(src: str, src_kind: str, dst: str, dst_kind: str, type_: str, weight: float, method: str,
          evidence: str | None) -> dict[str, Any]:
    return {"src": src, "src_kind": src_kind, "dst": dst, "dst_kind": dst_kind, "type": type_,
            "weight": float(weight), "method": method, "evidence": evidence}


def next_edges(rows: list[dict[str, Any]], weight: float) -> list[dict[str, Any]]:
    """NEXT entre filas consecutivas de la misma norma, en el orden del release."""
    out = []
    for a, b in zip(rows, rows[1:]):
        if a["norm_id"] == b["norm_id"]:
            out.append(_edge(a["chunk_id"], "chunk", b["chunk_id"], "chunk", "NEXT", weight, "structure", None))
    return out


def similar_pairs_numpy(chunk_ids: list[str], article_of: list[str], vectors: np.ndarray, k: int) -> dict:
    """kNN por coseno con numpy (vectores normalizados), excluyendo el mismo articulo. {(a, b): cos}."""
    sims = vectors @ vectors.T
    articles = np.array(article_of)
    pairs: dict[tuple[str, str], float] = {}
    for i in range(len(chunk_ids)):
        row = sims[i].copy()
        row[articles == articles[i]] = -np.inf
        top = np.argsort(-row)[:k]
        for j in top:
            if not np.isfinite(row[j]) or row[j] <= 0:
                continue
            a, b = sorted((chunk_ids[i], chunk_ids[int(j)]))
            pairs[(a, b)] = max(pairs.get((a, b), 0.0), float(row[j]))
    return pairs


def similar_pairs_lance(table: Any, chunk_ids: list[str], article_of: list[str], vectors: np.ndarray, k: int) -> dict:
    """kNN consultando la tabla LanceDB `chunks` (vector + article_id); excluye el mismo articulo."""
    pairs: dict[tuple[str, str], float] = {}
    for i, cid in enumerate(chunk_ids):
        own = article_of[i].replace("'", "\\'")
        hits = (table.search(vectors[i]).where(f"article_id != '{own}'", prefilter=True).limit(k)
                .select(["chunk_id"]).to_list())
        for h in hits:
            other = h["chunk_id"]
            if other == cid:
                continue
            cos = 1.0 - float(h["_distance"]) / 2.0 if "_distance" in h else 0.0
            # LanceDB devuelve distancia L2 al cuadrado entre vectores unitarios: cos = 1 - d/2.
            if cos <= 0:
                continue
            a, b = sorted((cid, other))
            pairs[(a, b)] = max(pairs.get((a, b), 0.0), cos)
    return pairs


def build_edges(chunks: pa.Table, entities: pa.Table, mentions: pa.Table, vectors: np.ndarray | None = None,
                params: dict[str, Any] | None = None, lance_table: Any = None) -> tuple[pa.Table, dict[str, Any]]:
    """Devuelve (tabla EDGES, stats). `vectors` alineado con `chunks`; sin vectores no hay SIMILAR."""
    params = params or params_mod.load()
    w = params["ppr"]["edge_weights"]
    cfg = params["edges"]
    rows = chunks.to_pylist()
    n = len(rows)
    chunk_ids = [r["chunk_id"] for r in rows]
    norm_of = {r["chunk_id"]: r["norm_id"] for r in rows}
    article_ids = {r["article_id"] for r in rows}
    norm_ids = {r["norm_id"] for r in rows}
    entity_ids = set(entities["entity_id"].to_pylist())
    edges: list[dict[str, Any]] = []
    stats: dict[str, Any] = {}

    edges.extend(next_edges(rows, w["NEXT"]))

    # Menciones que cuentan: regex/gazetteer y GLiNER2 sobre el corte, de entidades que entraron.
    kept = mentions.filter(aggregate.keep_mask(mentions, params)).to_pylist()
    kept = [m for m in kept if m["entity_id"] in entity_ids]

    # REFERS_TO (regex): chunk -> articulo o norma del corpus; rangos expandidos.
    unresolved: set[str] = set()
    for m in kept:
        value = json.loads(m["value"]) if m["value"] else {}
        if m["type"] == "article_ref":
            target = m["entity_id"].split(":", 1)[1]
            if "#art-" not in target:
                unresolved.add(target)
                continue
            target_norm, last_no = target.split("#art-", 1)
            numbers = expand_range(value["range_from"], last_no) if value.get("range_from") else [last_no]
            for no in numbers:
                art = f"{target_norm}#art-{no}"
                if art in article_ids:
                    edges.append(_edge(m["chunk_id"], "chunk", art, "article", "REFERS_TO", w["REFERS_TO"], "regex",
                                       m["mention"]))
                else:
                    unresolved.add(art)
        elif m["type"] == "norm_ref":
            target = value.get("norm_id")
            if target in norm_ids and target != norm_of[m["chunk_id"]]:
                edges.append(_edge(m["chunk_id"], "chunk", target, "norm", "REFERS_TO", w["REFERS_TO"], "regex",
                                   m["mention"]))
            elif target not in norm_ids:
                unresolved.add(target or m["mention"])
    stats["refers_to_unresolved"] = len(unresolved)
    stats["refers_to_unresolved_targets"] = sorted(unresolved)

    # MENTIONS (lens): chunk -> entidad, peso idf con piso para que la arista exista en Falkor.
    chunks_by_entity: dict[str, set[str]] = defaultdict(set)
    for m in kept:
        chunks_by_entity[m["entity_id"]].add(m["chunk_id"])
    floor = float(w["mentions_floor"])
    for e, cs in chunks_by_entity.items():
        weight = max(idf(n, len(cs)), floor)
        for c in sorted(cs):
            edges.append(_edge(c, "chunk", e, "entity", "MENTIONS", weight, "regex", None))

    # SIMILAR: kNN por coseno excluyendo el mismo articulo.
    if vectors is not None and n > 1:
        k = int(cfg["similar_k"])
        article_of = [r["article_id"] for r in rows]
        if lance_table is not None:
            pairs = similar_pairs_lance(lance_table, chunk_ids, article_of, vectors, k)
        else:
            pairs = similar_pairs_numpy(chunk_ids, article_of, vectors, k)
        for (a, b), cos in pairs.items():
            edges.append(_edge(a, "chunk", b, "chunk", "SIMILAR", cos, "knn", json.dumps({"cosine": round(cos, 4)})))
    stats["similar_built"] = vectors is not None

    # Una fila por (src, dst, type); sin bucles; peso > 0.
    seen: set[tuple[str, str, str]] = set()
    unique = []
    for e in edges:
        key = (e["src"], e["dst"], e["type"])
        if e["src"] == e["dst"] or e["weight"] <= 0 or key in seen:
            continue
        seen.add(key)
        unique.append(e)
    table = pa.Table.from_pylist(unique, schema=schema.EDGES)
    stats["edges_by_type"] = dict(sorted(_count(table["type"].to_pylist()).items()))
    return table, stats


def _count(values: list[str]) -> dict[str, int]:
    out: dict[str, int] = defaultdict(int)
    for v in values:
        out[v] += 1
    return dict(out)
