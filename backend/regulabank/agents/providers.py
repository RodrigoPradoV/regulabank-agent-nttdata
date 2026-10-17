"""Proveedor abstraido del modelo: `mock` | `anthropic` | `azure_openai` (docs/09-agents.md, docs/12-infra.md).

Todo el grafo se construye y se prueba con `FakeProvider`, guionado y sin red ni costo; el proveedor real
(`MODEL_PROVIDER=anthropic|azure_openai`) se enchufa al final sin tocar un solo nodo del grafo.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from regulabank.agents.contracts import Answer, Claim, Hit


class BaseProvider(ABC):
    """Los dos unicos lugares donde entra el modelo (docs/09-agents.md): juzgar evidencia y redactar."""

    name: str

    @abstractmethod
    def judge_evidence(self, question: str, hits: list[Hit]) -> list[str]:
        """Devuelve los `chunk_id` relevantes entre los mejores, solo de los que ya se vieron (`seen`)."""

    @abstractmethod
    def answer(self, question: str, hits: list[Hit], as_of: str, faults_seen: list[str]) -> Answer:
        """Redacta `Answer`; `faults_seen` es el error del intento anterior, visible, no oculto."""


class FakeProvider(BaseProvider):
    """Guionado: cita siempre la primera oracion del mejor `Hit`, literal. Sirve para probar el grafo entero."""

    name = "mock"

    def judge_evidence(self, question: str, hits: list[Hit]) -> list[str]:
        return [hit.chunk_id for hit in hits[:4]]

    def answer(self, question: str, hits: list[Hit], as_of: str, faults_seen: list[str]) -> Answer:
        if not hits:
            return Answer(claims=[], as_of=as_of, abstain=True, risk_hint="auto")
        best = hits[0]
        sentence = best.text.strip().split(".")[0].strip()
        if not sentence:
            return Answer(claims=[], as_of=as_of, abstain=True, risk_hint="auto")
        sentence = f"{sentence}."
        return Answer(
            claims=[Claim(text=sentence, chunk_id=best.chunk_id, quote=sentence)],
            as_of=as_of,
            abstain=False,
            risk_hint="auto",
        )
