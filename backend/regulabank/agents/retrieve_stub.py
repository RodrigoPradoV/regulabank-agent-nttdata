"""`retrieve` (version provisional): dos canales fundidos por RRF, sobre `data/corpus_v0`, sin embeddings.

Canal 1, lexico: solape de palabras (Jaccard). Hace de reemplazo del canal semantico real mientras el
transformer de embeddings no este listo -- el dia que lo este, se cambia solo esta lista por la del indice
denso; el resto (RRF, canal de entidades, el grafo entero) no se toca.

Canal 2, entidades (`entities.py`): cuanto se parecen las entidades estructuradas (plazos, montos, normas,
articulos, porcentajes) de la pregunta y del chunk -- este si es real, no un placeholder, porque no depende
de ningun modelo entrenado (docs/04-entities.md: "regex para deadline, amount, norm_ref").

Los dos se funden con la misma formula de `docs/08-retrieval.md` (RRF, `w/(60+rango)`), con el mismo peso
relativo que ahi se usa para el canal de entidades frente al denso (0,3 contra 1,0) -- pero el RRF solo decide
el ORDEN final, no el `score` que se reporta. RRF puntua por rango, no por magnitud: una pregunta sin ninguna
relacion real con el corpus puede terminar en el puesto 1 de un canal flojo y sacar el mismo score fundido que
una pregunta con una coincidencia fuerte. `Hit.score` guarda la magnitud cruda del canal lexico (0 si el chunk
solo entro por el canal de entidades) justamente para que `grade` pueda seguir midiendo confianza real.
"""

from __future__ import annotations

import re
import unicodedata
from functools import lru_cache
from pathlib import Path

import pyarrow.parquet as pq

from regulabank.agents import entities
from regulabank.agents.contracts import Hit
from regulabank.agents.fuse import rrf_fuse
from regulabank.agents.params import load_params

CORPUS_PATH = Path(__file__).resolve().parents[3] / "data" / "corpus_v0" / "corpus_chunks.parquet"
_WORD = re.compile(r"[a-z0-9]+")

# Minimo necesario para que el solape no se infle con conectores (esta version no tiene BM25/idf todavia).
_STOPWORDS = frozenset([
    "de", "la", "el", "en", "y", "que", "los", "las", "un", "una", "para", "con", "sobre", "su", "es", "se",
    "del", "al", "lo", "como", "por", "no", "si", "o", "este", "esta", "estos", "estas", "cual", "cuales", "a",
])

LEXICAL_WEIGHT = 1.0   # sustituto provisional del canal denso
ENTITY_WEIGHT = 0.3    # mismo peso relativo que `entities` en docs/08-retrieval.md


def _normalize(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.lower())
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def _tokens(text: str) -> set[str]:
    return {w for w in _WORD.findall(_normalize(text)) if w not in _STOPWORDS}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


@lru_cache(maxsize=1)
def load_corpus(path: Path = CORPUS_PATH) -> list[dict]:
    return pq.read_table(path).to_pylist()


def _ranked_ids(scored: list[tuple[float, str]], top_n: int) -> list[str]:
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [chunk_id for _, chunk_id in scored[:top_n]]


def _entity_confidence(raw_overlap: float) -> float:
    """Reescala `entities.score_overlap` (0, 0.5, 2.0, 2.5...) a 0-1, comparable con el Jaccard lexico.

    Un match exacto (mismo tipo y mismo valor, p. ej. el mismo numero de norma) es evidencia especifica y
    verificable por si sola -- no necesita que ademas haya solape lexico para contar como "hay evidencia".
    """
    if raw_overlap >= 2.0:
        return 1.0  # al menos un match exacto tipo+valor
    if raw_overlap > 0:
        return 0.3  # solo coincide el tipo (p. ej. ambos mencionan un plazo, pero no el mismo numero)
    return 0.0


def retrieve(
    question: str, as_of: str, top_k: int = 8, corpus: list[dict] | None = None, params: dict | None = None
) -> list[Hit]:
    """Los `top_k` mejores chunks por RRF(lexico, entidades), vigentes a `as_of` o sin fecha de fin."""
    corpus = corpus if corpus is not None else load_corpus()
    params = params if params is not None else load_params()
    cand_k = params.get("retrieval", {}).get("cand_k", 50)

    candidates = [row for row in corpus if not (row["valid_to"] and row["valid_to"] <= as_of)]
    if not candidates:
        return []

    q_tokens = _tokens(question)
    q_mentions = entities.extract(question)

    lexical_scored: list[tuple[float, str]] = []
    entity_scored: list[tuple[float, str]] = []
    magnitude_by_id: dict[str, float] = {}
    by_id: dict[str, dict] = {}
    for row in candidates:
        by_id[row["chunk_id"]] = row
        lexical = _jaccard(q_tokens, _tokens(row["text"]))
        if lexical > 0:
            lexical_scored.append((lexical, row["chunk_id"]))

        entity_raw = entities.score_overlap(q_mentions, entities.extract(row["text"])) if q_mentions else 0.0
        if entity_raw > 0:
            entity_scored.append((entity_raw, row["chunk_id"]))

        # dos senales independientes para la confianza: una coincidencia exacta de entidad alcanza por si
        # sola, igual que un buen solape lexico -- ninguna de las dos necesita a la otra.
        magnitude_by_id[row["chunk_id"]] = max(lexical, _entity_confidence(entity_raw))

    lexical_rank = _ranked_ids(lexical_scored, cand_k)
    entity_rank = _ranked_ids(entity_scored, cand_k)
    if not lexical_rank and not entity_rank:
        return []

    # RRF decide el orden (asi un chunk que las entidades respaldan fuerte puede subir aunque el lexico lo
    # tenga mas abajo); el score que se reporta es la magnitud cruda (lexico o entidad), no el valor de RRF.
    fused = rrf_fuse([lexical_rank, entity_rank], weights=[LEXICAL_WEIGHT, ENTITY_WEIGHT])
    ranked_ids = sorted(fused, key=fused.__getitem__, reverse=True)[:top_k]

    return [
        Hit(
            chunk_id=cid,
            norm_id=by_id[cid]["norm_id"],
            norm_short=by_id[cid]["norm_short"],
            article_id=by_id[cid]["article_id"],
            citation=by_id[cid]["citation"],
            text=by_id[cid]["text"],
            valid_from=by_id[cid]["valid_from"],
            valid_to=by_id[cid]["valid_to"],
            score=round(magnitude_by_id.get(cid, 0.0), 4),
        )
        for cid in ranked_ids
    ]
