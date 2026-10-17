"""`verify`: cita literal, vigencia, numeros ajenos y lenguaje -- contra chunks reales de data/corpus_v0."""

from __future__ import annotations

from regulabank.agents.contracts import Answer, Claim
from regulabank.agents.verify import check_language, verify


def test_valid_claim_has_no_faults(liquidez_hit) -> None:
    answer = Answer(
        claims=[Claim(
            text="El reglamento de riesgo de liquidez fue aprobado por la SBS.",
            chunk_id=liquidez_hit.chunk_id,
            quote="Artículo Primero.- Aprobar el nuevo Reglamento para la Gestión\ndel Riesgo de Liquidez",
        )],
        as_of="2026-10-17",
    )
    assert verify(answer, [liquidez_hit], "2026-10-17") == []


def test_quote_not_literal_in_chunk_is_rejected(liquidez_hit) -> None:
    answer = Answer(
        claims=[Claim(
            text="El reglamento fue aprobado en segunda instancia.",
            chunk_id=liquidez_hit.chunk_id,
            quote="Aprobar el reglamento en segunda instancia",  # no existe en el chunk
        )],
        as_of="2026-10-17",
    )
    faults = verify(answer, [liquidez_hit], "2026-10-17")
    assert any(f.kind == "quote_missing" for f in faults)


def test_chunk_outside_seen_is_rejected(liquidez_hit) -> None:
    answer = Answer(
        claims=[Claim(text="x", chunk_id="c_no_visto", quote="x")],
        as_of="2026-10-17",
    )
    faults = verify(answer, [liquidez_hit], "2026-10-17")
    assert len(faults) == 1
    assert faults[0].kind == "not_seen"


def test_expired_norm_cited_as_if_current_is_rejected(expired_hit) -> None:
    answer = Answer(
        claims=[Claim(
            text="Rige el Reglamento para la Gestión del Riesgo de Liquidez.",
            chunk_id=expired_hit.chunk_id,
            quote="Aprobar el Reglamento para la Gestión del Riesgo\nde Liquidez",
        )],
        as_of="2026-10-17",  # expired_hit.valid_to = 2024-01-01
    )
    faults = verify(answer, [expired_hit], "2026-10-17")
    assert any(f.kind == "not_in_force" for f in faults)


def test_expired_norm_is_fine_for_a_past_as_of(expired_hit) -> None:
    answer = Answer(
        claims=[Claim(
            text="Rige el Reglamento para la Gestión del Riesgo de Liquidez.",
            chunk_id=expired_hit.chunk_id,
            quote="Aprobar el Reglamento para la Gestión del Riesgo\nde Liquidez",
        )],
        as_of="2023-01-01",  # antes de valid_to: si estaba vigente
    )
    faults = verify(answer, [expired_hit], "2023-01-01")
    assert not any(f.kind == "not_in_force" for f in faults)


def test_foreign_number_not_in_quote_is_rejected(prociclico_hit) -> None:
    answer = Answer(
        claims=[Claim(
            text="El componente procíclico será 0.5%.",  # 0.5% no esta en la cita (es 0.3%)
            chunk_id=prociclico_hit.chunk_id,
            quote="el componente procíclico será 0.3%",
        )],
        as_of="2026-10-17",
    )
    faults = verify(answer, [prociclico_hit], "2026-10-17")
    assert any(f.kind == "foreign_fact" for f in faults)


def test_number_present_in_quote_is_not_foreign(prociclico_hit) -> None:
    answer = Answer(
        claims=[Claim(
            text="El componente procíclico será 0.3%.",
            chunk_id=prociclico_hit.chunk_id,
            quote="el componente procíclico será 0.3%",
        )],
        as_of="2026-10-17",
    )
    faults = verify(answer, [prociclico_hit], "2026-10-17")
    assert not any(f.kind == "foreign_fact" for f in faults)


def test_abstained_answer_skips_verification(liquidez_hit) -> None:
    answer = Answer(claims=[], as_of="2026-10-17", abstain=True)
    assert verify(answer, [liquidez_hit], "2026-10-17") == []


# --- lenguaje -----------------------------------------------------------------------------------------------

def test_clean_text_has_no_language_fault() -> None:
    assert check_language("El reglamento establece un plazo de quince días hábiles.") is None


def test_blocked_word_is_flagged() -> None:
    fault = check_language("Esta norma es una mierda y no sirve para nada.")
    assert fault is not None
    assert fault.kind == "inappropriate_language"


def test_blocked_word_is_case_and_accent_insensitive() -> None:
    assert check_language("Qué MIÉRDA de reglamento.") is not None


def test_blocklist_match_is_whole_word_not_substring() -> None:
    """'puta' esta bloqueada, pero no debe disparar por aparecer dentro de 'disputa'."""
    assert check_language("Hay una disputa legal sobre la vigencia del artículo.") is None


def test_inappropriate_language_fault_surfaces_in_full_verify(liquidez_hit) -> None:
    answer = Answer(
        claims=[Claim(
            text="Este reglamento es una mierda.",
            chunk_id=liquidez_hit.chunk_id,
            quote="Artículo Primero.- Aprobar el nuevo Reglamento para la Gestión\ndel Riesgo de Liquidez",
        )],
        as_of="2026-10-17",
    )
    faults = verify(answer, [liquidez_hit], "2026-10-17")
    assert any(f.kind == "inappropriate_language" for f in faults)
