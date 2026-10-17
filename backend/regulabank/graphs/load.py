"""Carga del release en FalkorDB (grafo `regulabank`): MERGE por lotes de 500 y verificacion de conteos.

Etiquetas: (:Chunk {id}), (:Entity {id}), (:Article {id}), (:Norm {id}). Las aristas llevan el tipo de EDGES
(NEXT, REFERS_TO, MENTIONS, SIMILAR) con weight, method y evidence. Si FalkorDB no responde se informa y se
devuelve None: el build local no depende del grafo (docs/06-graphs.md).
"""

from __future__ import annotations

import logging
import re
from collections import Counter
from typing import Any

import pyarrow as pa

from regulabank.shared import config, stores

log = logging.getLogger("regulabank.graphs.load")

BATCH = 500
LABEL = {"chunk": "Chunk", "entity": "Entity", "article": "Article", "norm": "Norm"}
CHUNK_PROPS = ("norm_id", "norm_short", "title", "issuer", "norm_kind", "status", "published", "valid_from",
               "valid_to", "article_id", "article_no", "node_type", "parent_path", "page_start", "page_end",
               "citation", "confidence", "review_required", "text")
ENTITY_PROPS = ("type", "name", "key", "catalog_id", "n_chunks", "n_norms")


_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def _clean(row: dict[str, Any]) -> dict[str, Any]:
    """FalkorDB no acepta caracteres de control (NUL de PDFs) en parametros; solo se limpia la copia del grafo."""
    return {k: _CTRL.sub("", v) if isinstance(v, str) else v for k, v in row.items()}


def _batches(rows: list[dict[str, Any]], size: int = BATCH):
    for i in range(0, len(rows), size):
        yield rows[i:i + size]


def _connect(settings: config.Settings):
    try:
        g = stores.graph(settings)
        g.query("RETURN 1")
        return g
    except Exception as exc:  # noqa: BLE001 - cualquier falla de conexion se informa y se salta
        log.warning("FalkorDB no responde en %s:%s (%s: %s); se salta la carga", settings.falkor_host,
                    settings.falkor_port, type(exc).__name__, exc)
        return None


def load(chunks: pa.Table, entities: pa.Table, edges: pa.Table, settings: config.Settings | None = None,
         batch: int = BATCH) -> dict[str, Any] | None:
    """Reemplaza el grafo con el release y devuelve los conteos verificados; None si FalkorDB esta caido."""
    settings = settings or config.load()
    g = _connect(settings)
    if g is None:
        return None
    try:
        g.delete()
    except Exception:  # noqa: BLE001 - el grafo puede no existir todavia
        pass
    g = stores.graph(settings)

    chunk_rows = [_clean({"id": r["chunk_id"], **{k: r[k] for k in CHUNK_PROPS}}) for r in chunks.to_pylist()]
    for b in _batches(chunk_rows, batch):
        g.query("UNWIND $rows AS r MERGE (c:Chunk {id: r.id}) SET c += r", {"rows": b})
    entity_rows = [_clean({"id": r["entity_id"], **{k: r[k] for k in ENTITY_PROPS}}) for r in entities.to_pylist()]
    for b in _batches(entity_rows, batch):
        g.query("UNWIND $rows AS r MERGE (e:Entity {id: r.id}) SET e += r", {"rows": b})
    article_rows = sorted({(r["article_id"], r["norm_id"]) for r in chunks.to_pylist()})
    for b in _batches([{"id": a, "norm_id": n} for a, n in article_rows], batch):
        g.query("UNWIND $rows AS r MERGE (a:Article {id: r.id}) SET a.norm_id = r.norm_id", {"rows": b})
    norm_rows = sorted({(r["norm_id"], r["norm_short"]) for r in chunks.to_pylist()})
    for b in _batches([{"id": n, "short": s} for n, s in norm_rows], batch):
        g.query("UNWIND $rows AS r MERGE (n:Norm {id: r.id}) SET n.short = r.short", {"rows": b})

    edge_rows = edges.to_pylist()
    groups: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for e in edge_rows:
        groups.setdefault((e["type"], e["src_kind"], e["dst_kind"]), []).append(e)
    for (type_, sk, dk), rows in groups.items():
        cypher = (
            f"UNWIND $rows AS r MATCH (a:{LABEL[sk]} {{id: r.src}}), (b:{LABEL[dk]} {{id: r.dst}}) "
            f"MERGE (a)-[x:{type_}]->(b) SET x.weight = r.weight, x.method = r.method, x.evidence = r.evidence"
        )
        for b in _batches(rows, batch):
            g.query(cypher, {"rows": [{k: r[k] for k in ("src", "dst", "weight", "method", "evidence")} for r in b]})

    counts = verify(g, chunks, entities, edges, len(article_rows), len(norm_rows))
    return counts


def verify(g: Any, chunks: pa.Table, entities: pa.Table, edges: pa.Table, n_articles: int, n_norms: int) -> dict:
    """Compara conteos del grafo con los Parquet; lanza ValueError si difieren."""
    expected = {
        "Chunk": chunks.num_rows, "Entity": entities.num_rows, "Article": n_articles, "Norm": n_norms,
    }
    got: dict[str, int] = {}
    for label, n in expected.items():
        got[label] = int(g.query(f"MATCH (x:{label}) RETURN count(x)").result_set[0][0])
    edge_expected = Counter(edges["type"].to_pylist())
    edge_got: dict[str, int] = {}
    for type_ in edge_expected:
        edge_got[type_] = int(g.query(f"MATCH ()-[x:{type_}]->() RETURN count(x)").result_set[0][0])
    mismatches = [f"{k}: esperado {expected[k]}, grafo {got[k]}" for k in expected if expected[k] != got[k]]
    mismatches += [f"{k}: esperado {edge_expected[k]}, grafo {edge_got[k]}" for k in edge_expected
                   if edge_expected[k] != edge_got[k]]
    if mismatches:
        raise ValueError("conteos del grafo no coinciden: " + "; ".join(mismatches))
    return {"nodes": got, "edges": edge_got}
