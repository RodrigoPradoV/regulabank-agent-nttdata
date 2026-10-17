"""`retrieve` provisional: lexico puro sobre data/corpus_v0, mientras no haya embeddings (ver docstring del modulo).

Corre contra el release real -- si estos tests fallan por falta de archivo, es que `data/corpus_v0/corpus_chunks.parquet`
no existe en este checkout (correr `backend/scripts/build_corpus_chunks.py` primero).
"""

from __future__ import annotations

from regulabank.agents import retrieve_stub


def test_corpus_file_exists() -> None:
    assert retrieve_stub.CORPUS_PATH.exists(), f"falta {retrieve_stub.CORPUS_PATH}; correr build_corpus_chunks.py"


def test_retrieve_finds_liquidity_chunks() -> None:
    hits = retrieve_stub.retrieve("reglamento de gestion del riesgo de liquidez", "2026-10-17", top_k=8)
    assert hits, "deberia encontrar algo sobre riesgo de liquidez en el corpus real"
    assert all(hit.score > 0 for hit in hits)
    assert all(hit.valid_to is None or hit.valid_to > "2026-10-17" for hit in hits)


def test_retrieve_empty_question_returns_nothing() -> None:
    assert retrieve_stub.retrieve("", "2026-10-17") == []


def test_retrieve_unrelated_question_returns_nothing_or_weak_hits() -> None:
    hits = retrieve_stub.retrieve("xyzxyz asdasd preguntasinsentido", "2026-10-17")
    assert hits == []


def test_retrieve_rescues_weak_lexical_match_via_exact_entity_match() -> None:
    """Una pregunta que nombra una norma puntual (`norm_ref`) debe subir de confianza aunque el solape
    lexico sea flojo -- esta es la razon de ser del canal de entidades (docs/04-entities.md)."""
    hits_without_norm = retrieve_stub.retrieve("cual es el componente prociclico", "2026-10-17")
    hits_with_norm = retrieve_stub.retrieve(
        "cual es el componente prociclico de la res sbs 11356-2008", "2026-10-17"
    )
    mean6_without = sum(h.score for h in hits_without_norm[:6]) / 6
    mean6_with = sum(h.score for h in hits_with_norm[:6]) / 6
    assert mean6_with > mean6_without


def test_retrieve_excludes_versions_expired_before_as_of() -> None:
    """Si todas las filas de un corpus de prueba estan vencidas a `as_of`, no debe devolver nada de ahi."""
    corpus = [{
        "chunk_id": "c_x", "norm_id": "n", "norm_short": "N", "article_id": "n#art-1",
        "citation": "N, art. 1", "text": "texto de prueba sobre riesgo de liquidez", "valid_from": None,
        "valid_to": "2020-01-01",
    }]
    hits = retrieve_stub.retrieve("riesgo de liquidez", "2026-10-17", corpus=corpus)
    assert hits == []
    hits_past = retrieve_stub.retrieve("riesgo de liquidez", "2019-01-01", corpus=corpus)
    assert hits_past  # a esa fecha si estaba vigente
