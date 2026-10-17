"""Nodos del agente como funciones: sin grafo, sin modelo y sin release (docs/09-agents.md, «Pruebas»)."""

from regulabank.agents.answer import NO_EVIDENCE, AnswerAgent, detect_scenario, numbers_in, parse_as_of, split_claims
from regulabank.agents.llm import FakeProvider
from regulabank.retrieval.search import Hit, verify_quote


def hit(i: int, text: str, current: bool = True, quote: str | None = None) -> Hit:
    return Hit(chunk_id=f"c{i}", norm_id="n", norm_short="Norma", article_no="1", path=None, citation=f"«{quote or text}» {{Norma, art. 1}}",
               text=text, quote=quote or text, quote_verified=verify_quote(quote or text, text), score=1.0, sources={},
               valid_from="2021-01-01", valid_to=None, is_current=current)


def agent() -> AnswerAgent:
    return AnswerAgent(retriever=None, provider=FakeProvider())  # type: ignore[arg-type]


def state(text: str, hits: list[Hit], scenario: str = "lookup") -> dict:
    return {"text": text, "hits": hits, "scenario": scenario, "as_of": "2026-10-17", "usage": {}}


def test_scenarios_y_fecha():
    assert detect_scenario("¿Qué es un incidente de ciberseguridad significativo?") == "definition"
    assert detect_scenario("¿Qué documentos internos se ven afectados por la derogación de la Circular?") == "impact"
    assert detect_scenario("¿El límite de la Política respeta la circular vigente?") == "policy_vs_norm"
    assert parse_as_of("¿Qué tasa fijaba al 15 de marzo de 2022?", "2026-10-17") == "2022-03-15"
    assert parse_as_of("¿Qué aplica hoy y desde el 1 de enero de 2027, y al 2 de abril de 2028?", "2026-10-17") == "2026-10-17"


def test_verify_acepta_respuesta_citada():
    out = agent().verify(state("El plazo es de 15 días [1].", [hit(1, "Se reporta dentro de 15 días hábiles.")]))
    assert out["faults"] == []


def test_verify_atrapa_cifra_inventada_cita_ajena_y_sin_cita():
    hits = [hit(1, "Se reporta dentro de 15 días hábiles.")]
    assert [f["kind"] for f in agent().verify(state("El plazo es de 30 días [1].", hits))["faults"]] == ["foreign_fact"]
    assert [f["kind"] for f in agent().verify(state("El plazo es largo [4].", hits))["faults"]] == ["foreign_citation"]
    assert [f["kind"] for f in agent().verify(state("El plazo es largo.", hits))["faults"]] == ["no_citation"]


def test_verify_cita_no_vigente_sin_decirlo():
    out = agent().verify(state("La tasa es 5 % [1].", [hit(1, "La tasa es 5 %.", current=False)]))
    assert [f["kind"] for f in out["faults"]] == ["stale_citation"]
    ok = agent().verify(state("La tasa era 5 % hasta el cambio, norma derogada [1].", [hit(1, "La tasa es 5 %.", current=False)]))
    assert ok["faults"] == []


def test_abstencion_literal_no_necesita_cita():
    assert agent().verify(state(f"{NO_EVIDENCE}: nada.", []))["faults"] == []


def test_deliver_renumera_y_deduplica_citas():
    hits = [hit(i, f"Texto {i} con 3 días.") for i in range(1, 6)]
    out = agent().deliver({**state("Uno [3]. Dos [5] y otra vez [3].", hits), "scenario": "lookup"})
    assert out["summary"] == "Uno [1]. Dos [2] y otra vez [1]."
    assert [c["chunk_id"] for c in out["claims"]] == ["c3", "c5"] and out["status"] == "ok"


def test_riesgo_por_tabla_y_por_version_vieja():
    a = AnswerAgent(retriever=None, provider=FakeProvider(), risk_rules={"policy_vs_norm": "approve"})  # type: ignore[arg-type]
    out = a.deliver(state("Se contradicen [1].", [hit(1, "x")], scenario="policy_vs_norm"))
    assert out["risk"] == "approve" and out["status"] == "pending_human"
    old = agent().deliver(state("Dice así [1].", [hit(1, "x", current=False)]))
    assert old["risk"] == "approve"


def test_split_claims_y_numeros():
    assert split_claims("Primera [1]. Segunda [2][3].")[1] == ("Segunda [2][3].", [2, 3])
    assert numbers_in("S/ 10 000 y 1,5 %") >= {"10000", "1.5"}


def test_nombre_de_norma_no_es_cifra_inventada():
    from regulabank.agents.answer import check
    hits = [hit(1, "Se reporta dentro de 24 horas.")]
    assert check("La Res. SBS 2660-2015 fija 24 horas [1].", hits, "lookup", "2026-10-17") == []
    assert [f["kind"] for f in check("La Res. SBS 2660-2015 fija 48 horas [1].", hits, "lookup", "2026-10-17")] == ["foreign_fact"]


def test_quita_el_preambulo_de_narracion():
    from regulabank.agents.answer import strip_preamble
    assert strip_preamble("Buscaré inconsistencias y reformularé.\n\nNo hay contradicción [1].") == "No hay contradicción [1]."
    assert strip_preamble("El plazo es de 24 horas [1].") == "El plazo es de 24 horas [1]."


def test_limpia_ligaturas_guion_blando_y_nul():
    from regulabank.retrieval.search import clean_text
    assert clean_text("eﬀective oﬀ-balance aﬃliate") == "effective off-balance affiliate"
    assert clean_text("utiliza­cion (\x00i)") == "utilizacion (i)"


def test_respuesta_que_solo_narra_no_pasa():
    from regulabank.agents.answer import check
    hits = [hit(1, "El plazo es de 24 horas.")]
    assert "narration_only" in [f["kind"] for f in check("Leeré el artículo 127 para ver las condiciones [1].", hits, "lookup", "2026-10-17")]
