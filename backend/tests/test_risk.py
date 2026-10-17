"""`risk`: tabla de reglas de seeds/risk_rules.csv -- nunca el modelo (docs/09-agents.md)."""

from __future__ import annotations

from regulabank.agents.contracts import Answer, Fault
from regulabank.agents.risk import classify_risk

_ANSWER = Answer(claims=[], as_of="2026-10-17")


def test_default_is_auto_with_no_faults() -> None:
    assert classify_risk("lookup", [], _ANSWER) == "auto"


def test_policy_vs_norm_is_always_approve() -> None:
    assert classify_risk("policy_vs_norm", [], _ANSWER) == "approve"


def test_impact_is_always_approve() -> None:
    assert classify_risk("impact", [], _ANSWER) == "approve"


def test_threshold_is_notify() -> None:
    assert classify_risk("threshold", [], _ANSWER) == "notify"


def test_not_in_force_fault_forces_approve_regardless_of_scenario() -> None:
    faults = [Fault(kind="not_in_force", detail="x")]
    assert classify_risk("lookup", faults, _ANSWER) == "approve"


def test_inappropriate_language_forces_approve() -> None:
    faults = [Fault(kind="inappropriate_language", detail="x")]
    assert classify_risk("lookup", faults, _ANSWER) == "approve"


def test_model_hint_can_raise_but_rule_floor_never_drops() -> None:
    """El modelo puede subir el riesgo; nunca puede bajar lo que ya impuso la regla."""
    risky_hint = Answer(claims=[], as_of="2026-10-17", risk_hint="approve")
    assert classify_risk("lookup", [], risky_hint) == "approve"  # lookup normal + hint alto -> gana el hint

    calm_hint = Answer(claims=[], as_of="2026-10-17", risk_hint="auto")
    assert classify_risk("policy_vs_norm", [], calm_hint) == "approve"  # la regla no se deja bajar
