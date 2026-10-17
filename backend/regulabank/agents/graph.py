"""`answer_graph`: el grafo 1 de `docs/09-agents.md`. LangGraph solo ordena; cada nodo es una funcion normal,
probada sin grafo (`route.py`, `grade.py`, `verify.py`, `risk.py`, `providers.py`). El modelo entra en dos
nodos (`judge_evidence`, `answer`); todo lo demas es codigo.

```
read -> retrieve -> grade -+- no_evidence --------------> abstain -> ledger
                            +- ambiguous -> judge_evidence -+- (siempre) -> answer
                            +- ok --------------------------+
answer -> verify -+- ok --------> risk -+- auto/notify --> deliver -> ledger
                   |                    +- approve -> human -+- accept -> deliver -> ledger
                   |                                          +- edit   -> verify (otra vez)
                   |                                          +- reject -> archive -> ledger
                   +- fail, fixes < MAX_FIXES -> retry -> answer (con el error a la vista)
                   +- fail, fixes = MAX_FIXES -> rejected -> ledger
```
"""

from __future__ import annotations

from datetime import date
from typing import Any

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.graph import END, StateGraph
from langgraph.types import interrupt

from regulabank.agents import ledger as ledger_mod
from regulabank.agents import retrieve_stub
from regulabank.agents import risk as risk_mod
from regulabank.agents import route as route_mod
from regulabank.agents import verify as verify_mod
from regulabank.agents.contracts import HumanResponse, State
from regulabank.agents.grade import grade as grade_fn
from regulabank.agents.providers import BaseProvider

MAX_FIXES = 2

# Los contratos de `agents/contracts.py` son Pydantic, no dataclasses nativas de LangGraph: el checkpointer
# necesita permiso explicito para guardarlos (si no, msgpack los bloqueara en una version futura). Si se pasa
# un checkpointer propio (p. ej. SqliteSaver en produccion), hay que darle el mismo `serde`.
ALLOWED_MSGPACK_MODULES: list[tuple[str, str]] = [
    ("regulabank.agents.contracts", name)
    for name in ("Hit", "RouteWeights", "GradeResult", "Claim", "Answer", "Fault", "HumanResponse")
]


def default_checkpointer() -> InMemorySaver:
    """Checkpointer de pruebas/demo, con los contratos del agente dados de alta. En produccion: SqliteSaver
    con el mismo `serde` (docs/09-agents.md: `SqliteSaver`, un `thread_id` por consulta)."""
    return InMemorySaver(serde=JsonPlusSerializer(allowed_msgpack_modules=ALLOWED_MSGPACK_MODULES))


def build_answer_graph(provider: BaseProvider, checkpointer: Any | None = None):
    """Compila `answer_graph` con el proveedor dado. `FakeProvider` para probar; el real al final (docs/09)."""
    if checkpointer is None:
        checkpointer = default_checkpointer()

    def node_read(state: State) -> dict:
        as_of = state.get("as_of") or date.today().isoformat()
        scenario = route_mod.classify(state["question"])
        return {"as_of": as_of, "scenario": scenario, "route_weights": route_mod.route(scenario)}

    def node_retrieve(state: State) -> dict:
        hits = retrieve_stub.retrieve(state["question"], state["as_of"])
        return {"hits": hits, "seen": [hit.chunk_id for hit in hits]}

    def node_grade(state: State) -> dict:
        return {"grade": grade_fn(state["hits"])}

    def node_judge_evidence(state: State) -> dict:
        relevant = set(provider.judge_evidence(state["question"], state["hits"]))
        kept = [hit for hit in state["hits"] if hit.chunk_id in relevant]
        hits = kept or state["hits"][:4]  # el juez solo filtra adentro de `seen`; nunca lo deja vacio
        return {"hits": hits, "seen": [hit.chunk_id for hit in hits]}

    def node_answer(state: State) -> dict:
        faults_seen = [fault.kind for fault in state.get("faults", [])]
        answer = provider.answer(state["question"], state["hits"], state["as_of"], faults_seen)
        return {"answer": answer}

    def node_verify(state: State) -> dict:
        answer = state["answer"]
        faults = verify_mod.verify(answer, state["hits"], state["as_of"]) if answer is not None else []
        return {"faults": faults}

    def node_retry(state: State) -> dict:
        return {"fixes": state.get("fixes", 0) + 1}

    def node_risk(state: State) -> dict:
        level = risk_mod.classify_risk(state["scenario"], state.get("faults", []), state["answer"])
        return {"risk": level}

    def node_human(state: State) -> dict:
        answer = state["answer"]
        payload = interrupt({
            "question": state["question"],
            "as_of": state["as_of"],
            "answer": answer.model_dump() if answer is not None else None,
            "risk": state["risk"],
            "faults": [fault.model_dump() for fault in state.get("faults", [])],
        })
        decision = HumanResponse.model_validate(payload)
        return {"human": decision}

    def node_deliver(state: State) -> dict:
        return {"status": "ok"}

    def node_abstain(state: State) -> dict:
        return {"status": "abstained"}

    def node_rejected(state: State) -> dict:
        return {"status": "rejected"}

    def node_archive(state: State) -> dict:
        return {"status": "rejected"}

    def node_ledger(state: State) -> dict:
        answer = state.get("answer")
        ledger_mod.append(path=ledger_mod.DEFAULT_LEDGER_PATH, entry={
            "scenario": state.get("scenario"),
            "seen": state.get("seen", []),
            "claims": len(answer.claims) if answer else 0,
            "faults": [fault.kind for fault in state.get("faults", [])],
            "fixes": state.get("fixes", 0),
            "risk": state.get("risk"),
            "human_decision": (state.get("human") or HumanResponse(type="accept")).type if state.get("human") else None,
            "status": state.get("status"),
            "model": provider.name,
        })
        return {}

    def route_after_grade(state: State) -> str:
        label = state["grade"].label
        return {"no_evidence": "abstain", "ambiguous": "judge_evidence", "ok": "answer"}[label]

    def route_after_verify(state: State) -> str:
        if not state.get("faults"):
            return "risk"
        return "retry" if state.get("fixes", 0) < MAX_FIXES else "rejected"

    def route_after_risk(state: State) -> str:
        return "human" if state["risk"] == "approve" else "deliver"

    def route_after_human(state: State) -> str:
        human = state.get("human")
        return {"accept": "deliver", "edit": "verify", "reject": "archive"}.get(
            human.type if human else "reject", "archive"
        )

    graph = StateGraph(State)
    for name, fn in (
        ("read", node_read), ("retrieve", node_retrieve), ("grade", node_grade),
        ("judge_evidence", node_judge_evidence), ("answer", node_answer), ("retry", node_retry),
        ("verify", node_verify), ("risk", node_risk), ("human", node_human),
        ("deliver", node_deliver), ("abstain", node_abstain), ("rejected", node_rejected),
        ("archive", node_archive), ("ledger", node_ledger),
    ):
        graph.add_node(name, fn)

    graph.set_entry_point("read")
    graph.add_edge("read", "retrieve")
    graph.add_edge("retrieve", "grade")
    graph.add_conditional_edges(
        "grade", route_after_grade, {"abstain": "abstain", "judge_evidence": "judge_evidence", "answer": "answer"}
    )
    graph.add_edge("judge_evidence", "answer")
    graph.add_edge("answer", "verify")
    graph.add_conditional_edges("verify", route_after_verify, {"risk": "risk", "retry": "retry", "rejected": "rejected"})
    graph.add_edge("retry", "answer")
    graph.add_conditional_edges("risk", route_after_risk, {"human": "human", "deliver": "deliver"})
    graph.add_conditional_edges("human", route_after_human, {"deliver": "deliver", "verify": "verify", "archive": "archive"})
    graph.add_edge("deliver", "ledger")
    graph.add_edge("abstain", "ledger")
    graph.add_edge("rejected", "ledger")
    graph.add_edge("archive", "ledger")
    graph.add_edge("ledger", END)

    return graph.compile(checkpointer=checkpointer)
