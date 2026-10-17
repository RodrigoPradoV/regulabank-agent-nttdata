"""CONTRADICTS: pares de chunks de normas distintas, elegidos por coseno + entidad compartida, juzgados por NLI.

Misma idea que la recuperacion (docs/05-relations.md, docs/08-retrieval.md): el modelo no busca, solo juzga.

1. Candidatos: por cada chunk, sus `neighbors` mejores chunks de OTRA norma que comparten al menos una entidad
   tematica con idf > 0 (norm_ref y article_ref no cuentan: citar no es tratar el mismo tema), por coseno de los
   vectores x suma de idf. Asi cada chunk con algun vecino posible queda cubierto.
2. Se juzga la fraccion `top_fraction` de los pares por puntaje (1,0 = todos; intercambiable por flag).
   HDBSCAN (sobre PCA) agrupa el corpus para repartir la muestra de etiquetado por zona.
3. NLI (`joeddav/xlm-roberta-large-xnli`, `max_length` explicito) sobre oraciones, no chunks: la oracion de A y la
   de B que mencionan la misma entidad. Premisa = A, hipotesis = B; el par se ordena por id, la arista es simetrica.
4. El juicio corre en GPU (`pod/nli.py`); aqui solo `prepare` (pares -> nli_pairs.parquet) y `collect`
   (probabilidades -> conflicts.parquet). El grafo conserva sus 4 aristas: los conflictos son una tabla citable
   (oraciones literales, entidad, tres probabilidades), no aristas.

Sin validar: docs/05-relations.md exige medir en 50 pares etiquetados antes de confiar.
"""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

from regulabank.graphs import params as params_mod  # noqa: F401 - reservado para parametros en seeds/params.toml
from regulabank.graphs.edges import _edge, idf
from regulabank.graphs.entities import _sentence_bounds

log = logging.getLogger("regulabank.graphs.conflicts")

NOT_TOPICAL = {"norm_ref", "article_ref"}

INPUT = pa.schema([
    ("pair_id", pa.string()), ("chunk_a", pa.string()), ("chunk_b", pa.string()),
    ("entity_id", pa.string()), ("cosine", pa.float32()), ("pair_score", pa.float32()),
    ("premise", pa.string()), ("hypothesis", pa.string()),
])
PAIRS = pa.schema([*INPUT, ("p_contradiction", pa.float32()), ("p_neutral", pa.float32()),
                   ("p_entailment", pa.float32()), ("label", pa.string())])


def _norm(text: str) -> str:
    return " ".join(text.lower().split())


def _sentence_of(text: str, bounds: list[tuple[int, int]], pos: int) -> str:
    for s, e in bounds:
        if s <= pos < e:
            return text[s:e].strip()
    return text[max(0, pos - 160):pos + 160].strip()


def candidate_pairs(chunks: pa.Table, mentions: pa.Table, vectors: np.ndarray, k: int) -> list[dict[str, Any]]:
    """Por cada chunk, sus `k` mejores vecinos de OTRA norma que comparten entidades tematicas (idf > 0).

    Es la misma busqueda que las consultas: coseno de los vectores x suma de idf de las entidades compartidas.
    Cada chunk con algun vecino posible queda cubierto, no solo los del kNN global. `vectors` esta alineado a
    `chunks` y normalizado."""
    ids = chunks["chunk_id"].to_pylist()
    row = {c: i for i, c in enumerate(ids)}
    norm_of = dict(zip(ids, chunks["norm_id"].to_pylist()))
    ents_of: dict[str, set[str]] = defaultdict(set)
    df: dict[str, set[str]] = defaultdict(set)
    for r in mentions.select(["chunk_id", "entity_id", "type"]).to_pylist():
        if r["type"] in NOT_TOPICAL:
            continue
        ents_of[r["chunk_id"]].add(r["entity_id"])
        df[r["entity_id"]].add(r["chunk_id"])
    weight = {e: idf(len(ids), len(c)) for e, c in df.items()}
    inv = {e: sorted(c) for e, c in df.items() if weight[e] > 0}
    best: dict[tuple[str, str], dict[str, Any]] = {}
    for a in ids:
        acc: dict[str, float] = defaultdict(float)
        for ent in ents_of.get(a, ()):
            if ent not in inv:
                continue
            for b in inv[ent]:
                if norm_of[b] != norm_of[a]:
                    acc[b] += weight[ent]
        if not acc:
            continue
        bs = list(acc)
        cos = vectors[[row[b] for b in bs]] @ vectors[row[a]]
        score = cos * np.array([acc[b] for b in bs])
        for j in np.argsort(-score)[:k]:
            x, y = sorted((a, bs[j]))
            if (x, y) not in best or score[j] > best[(x, y)]["score"]:
                shared = [e for e in ents_of[x] & ents_of[y] if e in inv]
                shared.sort(key=lambda e: -weight[e])
                best[(x, y)] = {"a": x, "b": y, "cosine": float(cos[j]), "shared": shared, "score": float(score[j])}
    return list(best.values())


def select_top(pairs: list[dict[str, Any]], top_fraction: float) -> list[dict[str, Any]]:
    """La fraccion superior por puntaje; al menos un par si hay candidatos."""
    if not pairs:
        return []
    ordered = sorted(pairs, key=lambda p: -p["score"])
    return ordered[:max(1, int(len(ordered) * top_fraction))]


def sentence_pairs(pair: dict[str, Any], texts: dict[str, str], spans: dict[str, dict[str, list[tuple[int, int]]]],
                   per_pair: int) -> list[dict[str, Any]]:
    """Hasta `per_pair` pares de oraciones (A, B) que mencionan la misma entidad compartida, sin repetir."""
    ta, tb = texts[pair["a"]], texts[pair["b"]]
    ba, bb = _sentence_bounds(ta), _sentence_bounds(tb)
    out, seen = [], set()
    for ent in pair["shared"]:
        sa = _sentence_of(ta, ba, spans[pair["a"]][ent][0][0])
        sb = _sentence_of(tb, bb, spans[pair["b"]][ent][0][0])
        if (sa, sb) in seen or not sa or not sb or _norm(sa) == _norm(sb):
            continue   # una copia del mismo texto en dos normas no es un conflicto
        seen.add((sa, sb))
        out.append({"entity_id": ent, "premise": sa, "hypothesis": sb})
        if len(out) >= per_pair:
            break
    return out


def cluster_chunks(vectors: np.ndarray, min_cluster_size: int = 10, components: int = 20) -> np.ndarray:
    """HDBSCAN sobre PCA de los vectores (en 768 dimensiones directo casi todo es ruido). Etiqueta -1 = ruido.

    Mide, no decide: los clusters salen casi por documento, asi que sirven para repartir la muestra de
    etiquetado por zona del corpus, no para generar pares."""
    from sklearn.cluster import HDBSCAN  # noqa: PLC0415
    from sklearn.decomposition import PCA  # noqa: PLC0415

    reduced = PCA(n_components=min(components, vectors.shape[0] - 1), random_state=0).fit_transform(vectors)
    return HDBSCAN(min_cluster_size=min_cluster_size, copy=True).fit_predict(reduced)


def label_sample(rows: list[dict[str, Any]], cluster_of: dict[str, int], n: int) -> list[dict[str, Any]]:
    """`n` pares repartidos por turnos entre los clusters del chunk A, de mayor a menor puntaje en cada uno."""
    groups: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for r in sorted(rows, key=lambda r: -r["pair_score"]):
        groups[cluster_of[r["chunk_a"]]].append(r)
    out: list[dict[str, Any]] = []
    queues = [list(v) for _, v in sorted(groups.items())]
    while len(out) < n and any(queues):
        for q in queues:
            if q and len(out) < n:
                out.append(q.pop(0))
    return out


def prepare(release: Path, top_fraction: float, per_pair: int, neighbors: int = 10,
            sample: int = 200) -> dict[str, Any]:
    """Elige pares (coseno + entidad compartida) y escribe release/nli_pairs.parquet para el job de GPU."""
    from regulabank.graphs import embed as embed_mod  # noqa: PLC0415

    chunks = pq.read_table(release / "chunks.parquet")
    mentions = pq.read_table(release / "mentions.parquet")
    ids = chunks["chunk_id"].to_pylist()
    vtable = pq.read_table(release / "vectors.parquet")
    vectors, model = embed_mod.read_vectors(vtable, ids)
    texts = dict(zip(ids, chunks["text"].to_pylist()))
    spans: dict[str, dict[str, list[tuple[int, int]]]] = defaultdict(lambda: defaultdict(list))
    for r in mentions.select(["chunk_id", "entity_id", "start", "end"]).to_pylist():
        spans[r["chunk_id"]][r["entity_id"]].append((r["start"], r["end"]))
    candidates = candidate_pairs(chunks, mentions, vectors, neighbors)
    chosen = select_top(candidates, top_fraction)
    rows = []
    for p in chosen:
        for sp in sentence_pairs(p, texts, spans, per_pair):
            rows.append({"pair_id": f"{p['a']}|{p['b']}|{len(rows)}", "chunk_a": p["a"], "chunk_b": p["b"],
                         "entity_id": sp["entity_id"], "cosine": p["cosine"], "pair_score": p["score"],
                         "premise": sp["premise"], "hypothesis": sp["hypothesis"]})
    pq.write_table(pa.Table.from_pylist(rows, schema=INPUT), release / "nli_pairs.parquet")
    labels = cluster_chunks(vectors)
    cluster_of = dict(zip(ids, (int(x) for x in labels)))
    pq.write_table(pa.table({"chunk_id": ids, "cluster": [cluster_of[c] for c in ids]}), release / "clusters.parquet")
    picked = label_sample(rows, cluster_of, sample)
    import csv  # noqa: PLC0415

    with open(release / "etiquetar_pares.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["pair_id", "cluster", "entity_id", "premise", "hypothesis", "label"])
        for r in picked:
            w.writerow([r["pair_id"], cluster_of[r["chunk_a"]], r["entity_id"], r["premise"], r["hypothesis"], ""])
    covered = {r["chunk_a"] for r in rows} | {r["chunk_b"] for r in rows}
    stats = {"embed_model": model, "chunk_pairs": len(chosen), "sentence_pairs": len(rows),
             "chunks_covered": len(covered), "chunks": len(ids), "neighbors": neighbors, "per_pair": per_pair,
             "clusters": len({c for c in cluster_of.values() if c >= 0}),
             "cluster_noise": sum(c < 0 for c in cluster_of.values()), "label_sample": len(picked)}
    (release / "nli_pairs_manifest.json").write_text(json.dumps(stats, indent=2), encoding="utf-8")
    log.info("nli_pairs: %s", stats)
    return stats


def collect(release: Path, scores: Path) -> dict[str, Any]:
    """Une nli_pairs.parquet con las probabilidades del pod en release/conflicts.parquet (no toca las aristas)."""
    pairs = pq.read_table(release / "nli_pairs.parquet")
    result = pq.read_table(scores)
    by_id = {r["pair_id"]: r for r in result.to_pylist()}
    missing = [i for i in pairs["pair_id"].to_pylist() if i not in by_id]
    if missing:
        raise ValueError(f"faltan {len(missing)} pares en {scores} (p. ej. {missing[:2]})")
    rows = []
    for r in pairs.to_pylist():
        s = by_id[r["pair_id"]]
        rows.append({**r, "p_contradiction": s["p_contradiction"], "p_neutral": s["p_neutral"],
                     "p_entailment": s["p_entailment"], "label": s["label"]})
    table = pa.Table.from_pylist(rows, schema=PAIRS)
    pq.write_table(table, release / "conflicts.parquet")
    labels: dict[str, int] = defaultdict(int)
    for r in rows:
        labels[r["label"]] += 1
    return {"pairs": len(rows), "labels": dict(labels)}


def nli_edges(conflicts: pa.Table, p_min: float) -> list[dict[str, Any]]:
    """CONTRADICTS: una arista por par de chunks, con la oracion de mayor P(contradiccion) >= p_min como evidencia (literal)."""
    best: dict[tuple[str, str], dict[str, Any]] = {}
    for r in conflicts.to_pylist():
        if r["label"] != "contradiction" or r["p_contradiction"] < p_min:
            continue
        key = (r["chunk_a"], r["chunk_b"])
        if key not in best or r["p_contradiction"] > best[key]["p_contradiction"]:
            best[key] = r
    return [
        _edge(a, "chunk", b, "chunk", "CONTRADICTS", r["p_contradiction"], "nli",
              json.dumps({"entity": r["entity_id"], "premise": r["premise"], "hypothesis": r["hypothesis"],
                          "p": {"contradiction": r["p_contradiction"], "neutral": r["p_neutral"], "entailment": r["p_entailment"]},
                          "validated": False}, ensure_ascii=False))
        for (a, b), r in best.items()
    ]


def add_nli_edges(release: Path, p_min: float, do_load: bool = False) -> dict[str, Any]:
    """Reemplaza las aristas CONTRADICTS de release/edges.parquet con las del NLI y, si se pide, recarga FalkorDB."""
    import pyarrow.compute as pc  # noqa: PLC0415

    from regulabank.graphs import load as load_mod  # noqa: PLC0415
    from regulabank.shared import config, schema  # noqa: PLC0415

    edges = pq.read_table(release / "edges.parquet")
    new = nli_edges(pq.read_table(release / "conflicts.parquet"), p_min)
    kept = edges.filter(pc.not_equal(edges["type"], "CONTRADICTS"))
    merged = pa.concat_tables([kept, pa.Table.from_pylist(new, schema=schema.EDGES)]) if new else kept
    pq.write_table(merged, release / "edges.parquet")
    out: dict[str, Any] = {"contradicts": len(new), "p_min": p_min, "edges_total": merged.num_rows}
    if do_load:
        chunks = pq.read_table(release / "chunks.parquet")
        out["falkor"] = load_mod.load(chunks.select(schema.CHUNKS.names), pq.read_table(release / "entities.parquet"), merged, config.load())
    return out
