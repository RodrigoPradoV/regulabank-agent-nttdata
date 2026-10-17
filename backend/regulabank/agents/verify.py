"""`verify`: codigo, nunca modelo. Cita literal, vigencia, numeros ajenos y lenguaje (docs/09-agents.md).

El chequeo de lenguaje es una ampliacion sobre el blueprint original: la lista de terminos bloqueados vive en
`seeds/blocklist_es.csv` -- dato revisable por una persona de cumplimiento, no una regla escondida en Python.
Una falta de `inappropriate_language` no se reintenta como las demas: `risk` la sube directo a `approve`
(ver `seeds/risk_rules.csv`), porque en un contexto bancario no conviene arriesgar un segundo intento "casi".
"""

from __future__ import annotations

import csv
import re
import unicodedata
from functools import lru_cache
from pathlib import Path

from regulabank.agents.contracts import Answer, Claim, Fault, Hit

BLOCKLIST_PATH = Path(__file__).resolve().parents[2] / "seeds" / "blocklist_es.csv"
_NUMBER = re.compile(r"\d+(?:[.,]\d+)?\s*%?")
_WHITESPACE = re.compile(r"\s+")
_NON_WORD = re.compile(r"[^a-z0-9\s]")


@lru_cache(maxsize=1)
def load_blocklist(path: Path = BLOCKLIST_PATH) -> frozenset[str]:
    with open(path, newline="", encoding="utf-8") as fh:
        return frozenset(row["term"].strip().lower() for row in csv.DictReader(fh) if row["term"].strip())


def _strip_accents(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.lower())
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def _normalize_words(text: str) -> str:
    """minusculas, sin tildes, solo letras/numeros -- para no dejar pasar variantes triviales."""
    return _NON_WORD.sub(" ", _strip_accents(text))


def _normalize_quote(text: str) -> str:
    """solo colapsa espacios; se usa para comparar citas literales, no para buscar palabras bloqueadas."""
    return _WHITESPACE.sub(" ", text).strip()


def check_language(text: str, blocklist: frozenset[str] | None = None) -> Fault | None:
    blocklist = blocklist if blocklist is not None else load_blocklist()
    words = set(_normalize_words(text).split())
    hit = next((term for term in blocklist if term in words), None)
    if hit:
        return Fault(kind="inappropriate_language", detail=f"termino bloqueado: {hit}")
    return None


def check_claim(claim: Claim, seen: dict[str, Hit], as_of: str) -> list[Fault]:
    faults: list[Fault] = []
    hit = seen.get(claim.chunk_id)
    if hit is None:
        faults.append(Fault(kind="not_seen", detail=f"chunk_id {claim.chunk_id} no esta en seen"))
        return faults  # sin el chunk no hay nada mas que verificar contra el

    if _normalize_quote(claim.quote) not in _normalize_quote(hit.text):
        faults.append(Fault(kind="quote_missing", detail=f"la cita no aparece literal en {claim.chunk_id}"))

    if hit.valid_to and hit.valid_to <= as_of:
        faults.append(Fault(kind="not_in_force", detail=f"{hit.citation} no vigente a {as_of}"))

    claim_numbers = set(_NUMBER.findall(claim.text))
    quote_numbers = set(_NUMBER.findall(claim.quote))
    foreign = claim_numbers - quote_numbers
    if foreign:
        faults.append(Fault(kind="foreign_fact", detail=f"numeros fuera de la cita: {sorted(foreign)}"))

    return faults


def verify(answer: Answer, hits: list[Hit], as_of: str, blocklist: frozenset[str] | None = None) -> list[Fault]:
    if answer.abstain:
        return []
    seen = {hit.chunk_id: hit for hit in hits}
    faults: list[Fault] = []
    for claim in answer.claims:
        faults.extend(check_claim(claim, seen, as_of))
        if (fault := check_language(claim.text, blocklist)) is not None:
            faults.append(fault)
    return faults
