"""`FakeProvider`: guionado, sin red -- pero su cita debe pasar `verify` igual que una real."""

from __future__ import annotations

from regulabank.agents.providers import FakeProvider
from regulabank.agents.verify import verify


def test_fake_provider_abstains_without_hits() -> None:
    answer = FakeProvider().answer("pregunta", [], "2026-10-17", [])
    assert answer.abstain is True
    assert answer.claims == []


def test_fake_provider_cites_the_best_hit(liquidez_hit) -> None:
    answer = FakeProvider().answer("pregunta", [liquidez_hit], "2026-10-17", [])
    assert len(answer.claims) == 1
    assert answer.claims[0].chunk_id == liquidez_hit.chunk_id


def test_fake_provider_quote_passes_verify(liquidez_hit) -> None:
    """Contrato minimo de cualquier proveedor (real o falso): lo que cita debe sobrevivir a `verify`."""
    answer = FakeProvider().answer("pregunta", [liquidez_hit], "2026-10-17", [])
    faults = verify(answer, [liquidez_hit], "2026-10-17")
    assert faults == []


def test_fake_provider_judge_evidence_keeps_only_seen_ids(liquidez_hit, prociclico_hit) -> None:
    relevant = FakeProvider().judge_evidence("pregunta", [liquidez_hit, prociclico_hit])
    assert set(relevant) <= {liquidez_hit.chunk_id, prociclico_hit.chunk_id}
