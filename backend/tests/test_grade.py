"""`grade`: etiqueta + numero de confianza, estilo CRAG (docs/09-agents.md)."""

from __future__ import annotations

from regulabank.agents.contracts import Hit
from regulabank.agents.grade import grade

PARAMS = {"grade": {"rescue_floor": 0.3, "ambiguous_floor": 0.6}}


def _hit(score: float) -> Hit:
    return Hit(
        chunk_id=f"c_{score}", norm_id="n", norm_short="N", article_id="n#art-1",
        citation="N, art. 1", text="texto", valid_from=None, valid_to=None, score=score,
    )


def test_no_evidence_when_no_hits() -> None:
    result = grade([], params=PARAMS)
    assert result.label == "no_evidence"
    assert result.score == 0.0


def test_no_evidence_below_rescue_floor() -> None:
    result = grade([_hit(0.1), _hit(0.1)], params=PARAMS)
    assert result.label == "no_evidence"


def test_ambiguous_between_floors() -> None:
    result = grade([_hit(0.4)] * 6, params=PARAMS)
    assert result.label == "ambiguous"
    assert result.score == 0.4


def test_ok_above_ambiguous_floor() -> None:
    result = grade([_hit(0.9)] * 6, params=PARAMS)
    assert result.label == "ok"


def test_uses_only_top_six() -> None:
    hits = [_hit(0.9)] * 6 + [_hit(0.0)] * 10  # el resto no debe bajar el promedio
    result = grade(hits, params=PARAMS)
    assert result.score == 0.9
    assert result.label == "ok"


def test_real_params_file_loads() -> None:
    """Sin pasar params: debe leer `seeds/params.toml` real, no reventar."""
    result = grade([_hit(0.5)] * 6)
    assert result.label in {"ok", "ambiguous", "no_evidence"}
