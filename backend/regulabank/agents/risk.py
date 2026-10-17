"""`risk`: tabla de reglas, nunca el modelo (docs/09-agents.md). "Si el modelo sugiere menos riesgo, gana la regla".

La tabla vive en `seeds/risk_rules.csv` -- una fila por regla, auditable sin leer Python. `classify_risk` toma
el maximo entre lo que disparan las reglas y lo que sugirio el modelo (`answer.risk_hint`): el modelo puede
subir el riesgo si detecta algo, pero nunca lo baja.
"""

from __future__ import annotations

import csv
from functools import lru_cache
from pathlib import Path

from regulabank.agents.contracts import Answer, Fault, RiskLevel, Scenario

RISK_RULES_PATH = Path(__file__).resolve().parents[2] / "seeds" / "risk_rules.csv"
_ORDER: dict[RiskLevel, int] = {"auto": 0, "notify": 1, "approve": 2}


@lru_cache(maxsize=1)
def load_rules(path: Path = RISK_RULES_PATH) -> list[dict[str, str]]:
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _matches(rule: dict[str, str], faults: list[Fault]) -> bool:
    condition = rule["condition"]
    if condition == "always":
        return True
    if condition == "scenario_is":
        return True  # el filtro por `scenario` ya se aplico antes de llamar aqui
    if condition == "fault_kind":
        return any(fault.kind == rule["value"] for fault in faults)
    return False


def _max_level(a: RiskLevel, b: RiskLevel) -> RiskLevel:
    return a if _ORDER[a] >= _ORDER[b] else b


def classify_risk(
    scenario: Scenario, faults: list[Fault], answer: Answer, rules: list[dict[str, str]] | None = None
) -> RiskLevel:
    rules = rules if rules is not None else load_rules()
    level: RiskLevel = "auto"
    for rule in rules:
        if rule["scenario"] not in ("*", scenario):
            continue
        if _matches(rule, faults):
            level = _max_level(level, rule["level"])  # type: ignore[arg-type]
    return _max_level(level, answer.risk_hint)
