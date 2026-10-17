"""`read`: escenario de la pregunta y pesos de busqueda por canal (docs/08-retrieval.md, docs/09-agents.md).

Puro: sin modelo, sin red. El escenario se clasifica por regex (version 0; afinar con golden set mas adelante,
docs/10-evaluation.md). Los pesos nunca excluyen un canal, solo lo pesan mas o menos (docs/README.md,
principio 2: "el grafo suma, no filtra") -- por eso `route()` siempre devuelve los cuatro canales con valor > 0.
"""

from __future__ import annotations

import re

from regulabank.agents.contracts import RouteWeights, Scenario
from regulabank.agents.params import load_params

# Orden importa: la primera que haga match gana. `negative` no se clasifica por forma de la pregunta -- la
# descubre `grade` cuando no hay evidencia, cualquiera sea el escenario detectado aqui.
_PATTERNS: list[tuple[Scenario, re.Pattern[str]]] = [
    ("policy_vs_norm", re.compile(r"pol[ií]ticas?\s+interna|procedimiento interno|manual interno|nuestra pol[ií]tica", re.IGNORECASE)),
    ("impact", re.compile(r"impacta|afecta(n)?\b|qu[eé] (normas?|pol[ií]ticas?) (cambia|modifica)", re.IGNORECASE)),
    ("crossref", re.compile(r"desarrolla|reglamenta|remite a|qu[eé] (norma|resoluci[oó]n) (desarrolla|implementa)", re.IGNORECASE)),
    ("validity", re.compile(r"vigente|derogad[ao]|modificad[ao]|sigue (aplicando|rigiendo)|desde cu[aá]ndo", re.IGNORECASE)),
    ("threshold", re.compile(r"plazo|monto m[aá]ximo|l[ií]mite|porcentaje|tasa m[ií]nima|d[ií]as h[aá]biles|cu[aá]nto(s)?\b", re.IGNORECASE)),
    ("procedure", re.compile(r"c[oó]mo (se debe|debo|hago)|pasos para|procedimiento para", re.IGNORECASE)),
    ("definition", re.compile(r"qu[eé] es\b|c[oó]mo se define|definici[oó]n de", re.IGNORECASE)),
]


def classify(question: str) -> Scenario:
    """Primer patron que hace match; si ninguno, `lookup` (busqueda directa, el caso por defecto)."""
    for scenario, pattern in _PATTERNS:
        if pattern.search(question):
            return scenario
    return "lookup"


def route(scenario: Scenario, params: dict | None = None) -> RouteWeights:
    """Pesos base de `seeds/params.toml`, con el override del escenario si existe."""
    params = params if params is not None else load_params()
    route_cfg = params.get("route", {})
    base = dict(route_cfg.get("base", {}))
    overrides = route_cfg.get("overrides", {}).get(scenario, {})
    base.update(overrides)
    return RouteWeights(**base) if base else RouteWeights()
