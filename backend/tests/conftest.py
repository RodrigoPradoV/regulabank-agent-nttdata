"""Fixtures compartidas. Los `Hit` de abajo son filas reales de `data/corpus_v0/corpus_chunks.parquet`
(no inventadas) para que `verify` se pruebe contra texto que de verdad existe en el release."""

from __future__ import annotations

import pytest

from regulabank.agents.contracts import Hit

LIQUIDEZ_HIT = Hit(
    chunk_id="c_142ee651498853ca",
    norm_id="pe-sbs-res-4221-2023",
    norm_short="Res. SBS 4221-2023",
    article_id="pe-sbs-res-4221-2023#art-primero",
    citation="Res. SBS 4221-2023, art. Primero, p. 2",
    text=(
        "Artículo Primero.- Aprobar el nuevo Reglamento para la Gestión\n"
        "del Riesgo de Liquidez, de acuerdo con lo siguiente:\n"
        "REGLAMENTO PARA LA GESTIÓN DEL RIESGO DE LIQUIDEZ"
    ),
    valid_from=None,
    valid_to=None,
    score=0.9,
)

PROCICLICO_HIT = Hit(
    chunk_id="c_be05126e836cfa60",
    norm_id="pe-sbs-res-11356-2008",
    norm_short="Res. SBS 11356-2008",
    article_id="pe-sbs-res-11356-2008#chap-iii",
    citation="Res. SBS 11356-2008, cap. III, p. 3",
    text=(
        "Capítulo III del Reglamento para la Evaluación y Clasificación del Deudor y la Exigencia de\n"
        "Provisiones, el componente procíclico será 0.3%. Para dicho efecto se deberá considerar la\n"
        "subcuenta analítica 1401.03.06.04 “Préstamos no revolventes otorgados bajo convenios\n"
        "elegibles”."
    ),
    valid_from=None,
    valid_to=None,
    score=0.8,
)

EXPIRED_HIT = Hit(
    chunk_id="c_75e05ad4b1e7517f",
    norm_id="pe-sbs-res-9075-2012",
    norm_short="Res. SBS 9075-2012",
    article_id="pe-sbs-res-9075-2012#art-primero",
    citation="Res. SBS 9075-2012, art. Primero, p. 2",
    text=(
        "Artículo Primero.- Aprobar el Reglamento para la Gestión del Riesgo\n"
        "de Liquidez, en los siguientes términos:\n"
        "“REGLAMENTO PARA LA GESTIÓN DEL RIESGO DE LIQUIDEZ"
    ),
    valid_from=None,
    valid_to="2024-01-01",  # reemplazada por Res. SBS 4221-2023 (LIQUIDEZ_HIT)
    score=0.7,
)


@pytest.fixture
def liquidez_hit() -> Hit:
    return LIQUIDEZ_HIT


@pytest.fixture
def prociclico_hit() -> Hit:
    return PROCICLICO_HIT


@pytest.fixture
def expired_hit() -> Hit:
    return EXPIRED_HIT
