"""RRF (Reciprocal Rank Fusion): `w / (60 + rango)`, igual formula que `docs/08-retrieval.md`.

Generico: funde cualquier cantidad de listas de ids ya rankeadas en un solo score. Hoy funde el canal
lexico (provisional, hace de "semantico" mientras no hay embeddings) con el de entidades; el dia que el
canal denso real entre, se reemplaza esa lista y esta funcion no cambia.
"""

from __future__ import annotations

K = 60


def rrf_fuse(ranked_lists: list[list[str]], weights: list[float] | None = None) -> dict[str, float]:
    """`ranked_lists[i]` ya viene ordenada de mejor a peor (por id). Devuelve `{id: score_fundido}`."""
    weights = weights if weights is not None else [1.0] * len(ranked_lists)
    scores: dict[str, float] = {}
    for ranked, weight in zip(ranked_lists, weights, strict=True):
        for rank, item_id in enumerate(ranked):
            scores[item_id] = scores.get(item_id, 0.0) + weight / (K + rank)
    return scores
