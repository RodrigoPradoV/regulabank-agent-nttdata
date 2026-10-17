"""Entidades estructuradas por regex (docs/04-entities.md): `norm_ref`, `article_ref`, `deadline`, `amount`,
`percentage`. Sin modelo -- a diferencia de las entidades abiertas (GLiNER2), estas cinco se extraen igual de
la pregunta y de un chunk, asi que sirven para puntuar cuanto se parecen sin esperar al transformer.

No es el `MENTIONS` final de `docs/04-entities.md` (eso vive en la ingesta, con start/end sobre el original);
esto es lo minimo para comparar pregunta vs. chunk en tiempo de consulta.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass

EntityType = str  # "norm_ref" | "article_ref" | "deadline" | "amount" | "percentage"

_ORDINALS = {
    "primero": "1", "segundo": "2", "tercero": "3", "cuarto": "4", "quinto": "5",
    "sexto": "6", "septimo": "7", "setimo": "7", "octavo": "8", "noveno": "9", "decimo": "10",
}


@dataclass(frozen=True)
class Mention:
    """Una ocurrencia normalizada: `key` es lo que se compara, `raw` es lo que se encontro en el texto."""

    type: EntityType
    key: str
    raw: str


def _strip_accents(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.lower())
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def _article_key(raw: str) -> str:
    word = _strip_accents(raw.strip())
    return _ORDINALS.get(word, word)


_PATTERNS: list[tuple[EntityType, re.Pattern[str], Callable[[str], str] | None]] = [
    (
        "norm_ref",
        re.compile(
            r"(?:ley|resoluci[oó]n|res\.?|decreto(?:\s+legislativo)?|d\.?\s*leg\.?|circular)\s*"
            r"(?:sbs|bcrp)?\s*n?[°º.]?\s*(\d{2,5}(?:-\d{4})?)",
            re.IGNORECASE,
        ),
        lambda raw: re.sub(r"[^0-9-]", "", raw),
    ),
    (
        "article_ref",
        re.compile(
            r"art[ií]culo\s+(\d+|primero|segundo|tercero|cuarto|quinto|sexto|s[eé]ptimo|setimo|octavo|noveno|d[eé]cimo)\b",
            re.IGNORECASE,
        ),
        _article_key,
    ),
    (
        # el corpus suele escribir el numero dos veces ("quince (15) dias habiles"); el regex se ancla al
        # digito mas cercano a "dias", este sea el principal o el que esta entre parentesis.
        "deadline",
        re.compile(r"(\d+)\s*\)?\s*d[ií]as?\s+(h[aá]biles|calendario)", re.IGNORECASE),
        None,  # dos grupos; se maneja aparte
    ),
    (
        "amount",
        re.compile(r"(?:s\/\.?|us\$|usd)\s*([\d]+(?:[.,]\d+)*)", re.IGNORECASE),
        lambda raw: re.sub(r"[^0-9.]", "", raw.replace(",", "")),
    ),
    (
        "percentage",
        re.compile(r"(\d+(?:[.,]\d+)?)\s*(?:%|por\s+ciento)", re.IGNORECASE),
        lambda raw: raw.replace(",", "."),
    ),
]


def extract(text: str) -> list[Mention]:
    """Las cinco entidades estructuradas de `docs/04-entities.md` presentes en `text`, normalizadas."""
    mentions: list[Mention] = []
    for entity_type, pattern, normalize in _PATTERNS:
        for match in pattern.finditer(text):
            if entity_type == "deadline":
                n, unit = match.group(1), _strip_accents(match.group(2))
                key = f"{n}_{unit}"
            else:
                key = normalize(match.group(1))
            if key:
                mentions.append(Mention(type=entity_type, key=key, raw=match.group(0)))
    return mentions


def score_overlap(query_mentions: list[Mention], chunk_mentions: list[Mention]) -> float:
    """Cuanto se parecen dos conjuntos de menciones: match exacto (tipo+valor) pesa mas que match de tipo solo."""
    if not query_mentions or not chunk_mentions:
        return 0.0
    exact = {(m.type, m.key) for m in query_mentions} & {(m.type, m.key) for m in chunk_mentions}
    query_types = {m.type for m in query_mentions}
    chunk_types = {m.type for m in chunk_mentions}
    type_only = (query_types & chunk_types) - {t for t, _ in exact}
    return 2.0 * len(exact) + 0.5 * len(type_only)
