"""`answer_graph` de punta a punta, con `FakeProvider` -- sin red, sin modelo real (docs/09-agents.md).

Cubre las tres salidas posibles del grafo 1: entrega directa, abstencion por falta de evidencia, y pausa
humana por riesgo alto, con su reanudacion (`Command(resume=...)`).
"""

from __future__ import annotations

import json

from langgraph.types import Command

from regulabank.agents.graph import build_answer_graph
from regulabank.agents.providers import FakeProvider


def _graph():
    return build_answer_graph(FakeProvider())


def test_ok_path_delivers_with_a_real_citation() -> None:
    graph = _graph()
    cfg = {"configurable": {"thread_id": "t-ok"}}
    out = graph.invoke({"question": "reglamento de gestion del riesgo de liquidez"}, cfg)

    assert out["status"] == "ok"
    assert out["risk"] == "auto"
    assert out["grade"].label == "ok"
    assert out["faults"] == []
    assert len(out["answer"].claims) == 1
    assert out["answer"].claims[0].chunk_id in out["seen"]


def test_no_evidence_path_abstains() -> None:
    graph = _graph()
    cfg = {"configurable": {"thread_id": "t-abstain"}}
    out = graph.invoke({"question": "xyzxyz asdasd preguntasinsentido"}, cfg)

    assert out["status"] == "abstained"
    assert out["grade"].label == "no_evidence"
    assert out.get("answer") is None


def test_policy_vs_norm_pauses_for_a_human_and_resumes_on_accept() -> None:
    graph = _graph()
    cfg = {"configurable": {"thread_id": "t-human"}}
    out = graph.invoke(
        {"question": "Nuestra política interna de riesgo de liquidez cumple con el reglamento"}, cfg
    )

    assert out["__interrupt__"], "policy_vs_norm con regla approve debe pausar en `human`"
    assert graph.get_state(cfg).next == ("human",)

    resumed = graph.invoke(Command(resume={"type": "accept"}), cfg)
    assert resumed["status"] == "ok"
    assert resumed["human"].type == "accept"


def test_policy_vs_norm_archived_on_human_reject() -> None:
    graph = _graph()
    cfg = {"configurable": {"thread_id": "t-reject"}}
    graph.invoke(
        {"question": "Nuestra política interna de riesgo de liquidez cumple con el reglamento"}, cfg
    )
    resumed = graph.invoke(Command(resume={"type": "reject"}), cfg)
    assert resumed["status"] == "rejected"


def test_ledger_gets_one_line_per_run(tmp_path, monkeypatch) -> None:
    ledger_file = tmp_path / "answer_graph.jsonl"
    monkeypatch.setattr("regulabank.agents.graph.ledger_mod.DEFAULT_LEDGER_PATH", ledger_file)

    graph = _graph()
    graph.invoke({"question": "reglamento de gestion del riesgo de liquidez"}, {"configurable": {"thread_id": "t-ledger"}})

    lines = ledger_file.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1


def test_ledger_line_carries_question_as_of_and_latency(tmp_path, monkeypatch) -> None:
    ledger_file = tmp_path / "answer_graph.jsonl"
    monkeypatch.setattr("regulabank.agents.graph.ledger_mod.DEFAULT_LEDGER_PATH", ledger_file)

    graph = _graph()
    graph.invoke(
        {"question": "reglamento de gestion del riesgo de liquidez", "as_of": "2024-06-01"},
        {"configurable": {"thread_id": "t-ledger-fields"}},
    )

    entry = json.loads(ledger_file.read_text(encoding="utf-8").strip())
    assert entry["question"] == "reglamento de gestion del riesgo de liquidez"
    assert entry["as_of"] == "2024-06-01"
    assert isinstance(entry["latency_ms"], int)
    assert entry["latency_ms"] >= 0
