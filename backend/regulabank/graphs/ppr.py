"""PageRank personalizado sobre chunks ∪ entidades (docs/06-graphs.md, «Grafo en memoria para PageRank»).

Grafo no dirigido: cada arista suma su peso en ambos sentidos; la matriz es columna-estocastica (P = A D^-1) en
scipy.sparse. Las aristas a articulos o normas (REFERS_TO) se reparten entre los chunks de ese destino, de modo
que todos los nodos son chunks o entidades. `personalized_pagerank(seeds, alpha=0.5, iters=30)`: alpha es la
probabilidad de reinicio hacia las semillas; 30 pasos de potencia bastan para que converja en grafos de este
tamano (sin iteracion adaptativa para que el resultado sea reproducible).
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Iterable, Mapping

import numpy as np
import pyarrow as pa
import scipy.sparse as sp


@dataclass
class PPRGraph:
    """Indice de nodos y matriz de transicion columna-estocastica."""

    nodes: list[str]
    index: dict[str, int]
    kind: dict[str, str]  # chunk | entity
    matrix: sp.csc_matrix

    @property
    def n(self) -> int:
        return len(self.nodes)


def build_graph(chunks: pa.Table, entities: pa.Table, edges: pa.Table) -> PPRGraph:
    """Tablas CHUNKS, ENTITIES, EDGES -> PPRGraph. Aristas con extremos fuera del conjunto se descartan."""
    chunk_ids = chunks["chunk_id"].to_pylist()
    entity_ids = entities["entity_id"].to_pylist() if entities.num_rows else []
    nodes = list(chunk_ids) + list(entity_ids)
    index = {node: i for i, node in enumerate(nodes)}
    kind = {c: "chunk" for c in chunk_ids}
    kind.update({e: "entity" for e in entity_ids})

    by_article: dict[str, list[str]] = defaultdict(list)
    by_norm: dict[str, list[str]] = defaultdict(list)
    for cid, art, norm in zip(chunk_ids, chunks["article_id"].to_pylist(), chunks["norm_id"].to_pylist()):
        by_article[art].append(cid)
        by_norm[norm].append(cid)

    weights: dict[tuple[int, int], float] = defaultdict(float)
    for e in edges.to_pylist():
        src = e["src"]
        if src not in index:
            continue
        if e["dst_kind"] == "article":
            targets = by_article.get(e["dst"], [])
        elif e["dst_kind"] == "norm":
            targets = by_norm.get(e["dst"], [])
        else:
            targets = [e["dst"]] if e["dst"] in index else []
        if not targets:
            continue
        share = float(e["weight"]) / len(targets)
        i = index[src]
        for t in targets:
            j = index[t]
            if i == j:
                continue
            weights[(i, j)] += share
            weights[(j, i)] += share

    n = len(nodes)
    if weights:
        rows, cols = zip(*weights.keys())
        adj = sp.coo_matrix((np.fromiter(weights.values(), dtype=np.float64), (rows, cols)), shape=(n, n)).tocsc()
    else:
        adj = sp.csc_matrix((n, n), dtype=np.float64)
    degree = np.asarray(adj.sum(axis=0)).ravel()
    inv = np.where(degree > 0, 1.0 / np.where(degree > 0, degree, 1.0), 0.0)
    matrix = (adj @ sp.diags(inv)).tocsc()
    return PPRGraph(nodes, index, kind, matrix)


def personalized_pagerank(graph: PPRGraph, seeds: Mapping[str, float] | Iterable[str], alpha: float = 0.5,
                          iters: int = 30) -> dict[str, float]:
    """Vector estacionario aproximado r = alpha * p + (1 - alpha) * P r, con p = semillas normalizadas.

    Devuelve {nodo: puntaje} solo para los nodos con puntaje > 0. Semillas desconocidas se ignoran; sin semillas
    validas devuelve {}.
    """
    if not isinstance(seeds, Mapping):
        seeds = {s: 1.0 for s in seeds}
    p = np.zeros(graph.n, dtype=np.float64)
    for node, weight in seeds.items():
        if node in graph.index and weight > 0:
            p[graph.index[node]] += float(weight)
    total = p.sum()
    if total <= 0:
        return {}
    p /= total
    r = p.copy()
    for _ in range(iters):
        r = alpha * p + (1.0 - alpha) * (graph.matrix @ r)
        # La masa que cae en nodos sin salida vuelve a las semillas (sin ella r se desinfla).
        lost = 1.0 - r.sum()
        if lost > 0:
            r += lost * p
    return {graph.nodes[i]: float(r[i]) for i in np.flatnonzero(r > 0)}


def top(scores: Mapping[str, float], graph: PPRGraph, kind: str = "chunk", k: int = 20) -> list[tuple[str, float]]:
    """Los k nodos de un tipo con mayor puntaje."""
    items = [(node, s) for node, s in scores.items() if graph.kind.get(node) == kind]
    return sorted(items, key=lambda kv: -kv[1])[:k]
