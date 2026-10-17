"""`/answer` ya corre `answer_graph` sobre el corpus real, no la maqueta de palabras clave (`mock.answer`)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from regulabank.api.app import app

client = TestClient(app)


def test_answer_cites_a_real_chunk_from_the_corpus() -> None:
    res = client.post("/answer", json={"question": "reglamento de gestión del riesgo de liquidez"})
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ok"
    assert body["claims"], body
    assert body["trace"]["confidence_label"] == "ok"
    assert body["trace"]["route_weights"]  # el enrutador por escenario llego al contrato HTTP


def test_answer_abstains_cleanly_without_evidence() -> None:
    res = client.post("/answer", json={"question": "xyzxyz asdasd preguntasinsentido"})
    body = res.json()
    assert body["status"] == "abstained"
    assert body["claims"] == []
    assert body["trace"]["confidence_label"] == "no_evidence"


def test_answer_pauses_for_human_on_policy_vs_norm() -> None:
    res = client.post("/answer", json={
        "question": "Nuestra política interna de riesgo de liquidez cumple con el reglamento",
    })
    body = res.json()
    assert body["status"] == "pending_human"
    assert body["risk"] == "approve"
