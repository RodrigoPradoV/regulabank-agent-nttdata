"""`entities.py`: las cinco entidades estructuradas por regex (docs/04-entities.md), sin modelo."""

from __future__ import annotations

from regulabank.agents import entities as E


def test_extracts_percentage() -> None:
    mentions = E.extract("el componente procíclico será 0.3%.")
    assert E.Mention(type="percentage", key="0.3", raw="0.3%") in mentions


def test_extracts_numeric_article_ref() -> None:
    mentions = E.extract("conforme al artículo 12 del reglamento")
    assert any(m.type == "article_ref" and m.key == "12" for m in mentions)


def test_extracts_spelled_ordinal_article_ref() -> None:
    """El corpus usa 'Artículo Primero.-' en vez de 'Artículo 1' en varias resoluciones SBS."""
    mentions = E.extract("Artículo Primero.- Aprobar el nuevo Reglamento")
    assert any(m.type == "article_ref" and m.key == "1" for m in mentions)


def test_numeric_and_ordinal_article_ref_compare_equal() -> None:
    a = E.extract("artículo 1 del reglamento")
    b = E.extract("Artículo Primero.- Aprobar")
    assert {m.key for m in a if m.type == "article_ref"} == {m.key for m in b if m.type == "article_ref"}


def test_extracts_deadline_with_parenthetical_digit() -> None:
    """Forma comun del corpus: 'quince (15) días hábiles' -- el ancla es el digito, no la palabra."""
    mentions = E.extract("dentro de los quince (15) días hábiles siguientes")
    assert E.Mention(type="deadline", key="15_habiles", raw="15) días hábiles") in mentions


def test_extracts_amount_in_soles() -> None:
    mentions = E.extract("un monto de S/ 1,500.00 por operación")
    assert any(m.type == "amount" for m in mentions)


def test_extracts_norm_ref() -> None:
    mentions = E.extract("conforme a la Res. SBS N° 11356-2008 y sus modificatorias")
    assert any(m.type == "norm_ref" and m.key == "11356-2008" for m in mentions)


def test_no_entities_in_plain_text() -> None:
    assert E.extract("el banco debe informar a sus clientes oportunamente") == []


# --- score_overlap -------------------------------------------------------------------------------------------

def test_exact_match_scores_higher_than_type_only_match() -> None:
    query = E.extract("¿cuál es el plazo en la Res. SBS 11356-2008?")
    same_norm = E.extract("conforme a la Res. SBS 11356-2008")
    other_norm = E.extract("conforme a la Res. SBS 9075-2012")  # mismo tipo (norm_ref), otro numero

    assert E.score_overlap(query, same_norm) > E.score_overlap(query, other_norm)
    assert E.score_overlap(query, other_norm) > 0  # el tipo igual algo suma
    assert E.score_overlap(query, []) == 0.0


def test_no_mentions_means_no_overlap() -> None:
    assert E.score_overlap([], E.extract("artículo 12")) == 0.0
    assert E.score_overlap(E.extract("artículo 12"), []) == 0.0
