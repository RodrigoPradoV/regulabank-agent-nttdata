"""`read`/`route`: escenario por regex y pesos por canal (docs/08-retrieval.md, docs/09-agents.md)."""

from __future__ import annotations

from regulabank.agents import route


def test_classify_scenarios() -> None:
    cases = {
        "¿Qué es el riesgo operacional?": "definition",
        "¿Cuál es el plazo máximo para remitir el reporte?": "threshold",
        "¿Cómo se debe clasificar a un deudor?": "procedure",
        "¿Sigue vigente el artículo 12 de la Res. SBS 11356-2008?": "validity",
        "¿Qué norma desarrolla el artículo 20 de la Ley 26702?": "crossref",
        "¿Nuestra política interna de riesgo de liquidez cumple con el reglamento?": "policy_vs_norm",
        "¿Qué políticas afecta la nueva resolución sobre encaje?": "impact",
        "¿Cuál es el artículo 5 de la Res. SBS 2660-2015?": "lookup",
    }
    for question, expected in cases.items():
        assert route.classify(question) == expected, question


def test_route_never_zeroes_a_channel() -> None:
    """Principio 2 (docs/README.md): el grafo suma, no filtra -- ningun canal llega a 0."""
    for scenario in ("lookup", "definition", "threshold", "procedure", "validity", "crossref", "policy_vs_norm", "impact"):
        weights = route.route(scenario)
        assert weights.dense > 0
        assert weights.bm25 > 0
        assert weights.entities > 0
        assert weights.ppr > 0


def test_route_overrides_graph_weight_for_crossref_and_impact() -> None:
    base = route.route("lookup")
    crossref = route.route("crossref")
    impact = route.route("impact")
    assert crossref.ppr > base.ppr
    assert impact.ppr > base.ppr


def test_route_overrides_dense_weight_down_for_definition() -> None:
    base = route.route("lookup")
    definition = route.route("definition")
    assert definition.dense < base.dense
