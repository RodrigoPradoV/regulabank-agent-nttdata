"""Demo de `answer_graph` sin servidor ni modelo real: `FakeProvider` + `retrieve` lexico sobre data/corpus_v0.

Sirve para ver el grafo completo corriendo (lectura de escenario, grado de confianza, cita verificada, riesgo,
y la pausa humana) mientras el indice de embeddings no esta listo. Cuando lo este, solo cambia
`regulabank.agents.retrieve_stub`; el resto del grafo queda igual.

Uso: `python scripts/demo_answer_graph.py` (o `python scripts/demo_answer_graph.py "tu pregunta" [as_of]`)
"""

from __future__ import annotations

import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from langgraph.types import Command

from regulabank.agents.graph import build_answer_graph
from regulabank.agents.providers import FakeProvider

_DEFAULT_QUESTIONS = [
    "¿Cuál es el reglamento para la gestión del riesgo de liquidez?",
    "¿Nuestra política interna de riesgo de liquidez cumple con el reglamento?",
    "¿Qué dice la norma sobre pizza y fútbol?",
]


def _print_result(question: str, result: dict) -> None:
    print(f"\n--- {question} ---")
    print(f"escenario={result.get('scenario')} grade={result.get('grade')} risk={result.get('risk')}")
    answer = result.get("answer")
    if answer and answer.claims:
        for claim in answer.claims:
            print(f"  cita [{claim.chunk_id}]: {claim.quote!r}")
    if result.get("__interrupt__"):
        print("  >> pausado para revision humana (interrupt)")
    else:
        print(f"  status={result.get('status')}")


def main() -> None:
    graph = build_answer_graph(FakeProvider())
    args = sys.argv[1:]
    questions = [args[0]] if args else _DEFAULT_QUESTIONS
    as_of = args[1] if len(args) > 1 else None

    for i, question in enumerate(questions):
        cfg = {"configurable": {"thread_id": f"demo-{i}"}}
        payload = {"question": question}
        if as_of:
            payload["as_of"] = as_of
        result = graph.invoke(payload, cfg)
        _print_result(question, result)

        if result.get("__interrupt__"):
            resumed = graph.invoke(Command(resume={"type": "accept"}), cfg)
            print(f"  resumido: status={resumed.get('status')} (decision humana simulada: accept)")

    print(f"\nledger: {BACKEND_ROOT.parent / 'data' / 'ledger' / 'answer_graph.jsonl'}")


if __name__ == "__main__":
    main()
