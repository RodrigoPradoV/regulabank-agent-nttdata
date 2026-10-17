"""`retrieve` (version provisional): busqueda lexica simple sobre `data/corpus_v0`, sin embeddings.

Mientras el modelo de embeddings este entrenandose, el grafo entero (`grade`, `judge_evidence`, `answer`,
`verify`, `risk`, `ledger`) se puede construir y probar igual, porque la forma de salida (`list[Hit]`) no
cambia -- solo cambia como se llena. Cuando el indice real (LanceDB denso + BM25 + PPR, docs/08-retrieval.md)
este listo, se reemplaza esta funcion por una que llame a ese indice; nada del resto del grafo se toca.

Puntaje = solape de palabras (Jaccard) entre la pregunta y el chunk. Es deliberadamente simple: no pretende
ser el retrieval final, solo dar `Hit` reales (con texto literal, vigencia y cita) para que el resto de los
nodos tenga algo verdadero contra lo que trabajar.
"""

from __future__ import annotations

import re
import unicodedata
from functools import lru_cache
from pathlib import Path

import pyarrow.parquet as pq

from regulabank.agents.contracts import Hit

CORPUS_PATH = Path(__file__).resolve().parents[3] / "data" / "corpus_v0" / "corpus_chunks.parquet"
_WORD = re.compile(r"[a-z0-9]+")

# Minimo necesario para que el solape no se infle con conectores (esta version no tiene BM25/idf todavia).
_STOPWORDS = frozenset([
    "de", "la", "el", "en", "y", "que", "los", "las", "un", "una", "para", "con", "sobre", "su", "es", "se",
    "del", "al", "lo", "como", "por", "no", "si", "o", "este", "esta", "estos", "estas", "cual", "cuales", "a",
])


def _normalize(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.lower())
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def _tokens(text: str) -> set[str]:
    return {w for w in _WORD.findall(_normalize(text)) if w not in _STOPWORDS}


@lru_cache(maxsize=1)
def load_corpus(path: Path = CORPUS_PATH) -> list[dict]:
    return pq.read_table(path).to_pylist()


def retrieve(question: str, as_of: str, top_k: int = 8, corpus: list[dict] | None = None) -> list[Hit]:
    """Los 8 mejores chunks por solape de palabras, vigentes a `as_of` o sin fecha de fin."""
    corpus = corpus if corpus is not None else load_corpus()
    q_tokens = _tokens(question)
    if not q_tokens:
        return []

    scored: list[tuple[float, dict]] = []
    for row in corpus:
        if row["valid_to"] and row["valid_to"] <= as_of:
            continue  # version no vigente a as_of; esta version provisional no muestra historia todavia
        c_tokens = _tokens(row["text"])
        if not c_tokens:
            continue
        overlap = len(q_tokens & c_tokens) / len(q_tokens | c_tokens)
        if overlap > 0:
            scored.append((overlap, row))

    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [
        Hit(
            chunk_id=row["chunk_id"],
            norm_id=row["norm_id"],
            norm_short=row["norm_short"],
            article_id=row["article_id"],
            citation=row["citation"],
            text=row["text"],
            valid_from=row["valid_from"],
            valid_to=row["valid_to"],
            score=round(score, 4),
        )
        for score, row in scored[:top_k]
    ]
