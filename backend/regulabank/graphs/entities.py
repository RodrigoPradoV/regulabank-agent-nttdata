"""Extractores de menciones: regex para lo formulaico, gazetteer para el catalogo (docs/04-entities.md).

Regla de oro: lo que tiene forma fija (referencias, plazos, montos, porcentajes, definiciones) sale por regex y
se verifica literal (`text[start:end] == mention`); el catalogo (`seeds/catalog.csv`) resuelve reguladores,
tipos de institucion, riesgos y productos por nombre o alias; `seeds/norms.csv` (columnas `short` y `aliases`)
resuelve los nombres cortos de las normas del corpus («Ley General», «Circular sintética C-2018»). El modelo
abierto vive aparte en `gliner2.py`.

Referencias a articulos: «artículos 8 al 12» produce una mencion por numero explicito (8 y 12) y el rango viaja en
`value` (`range_from`) para que la etapa edges lo expanda; sin norma nombrada en la oracion, el destino es la misma
norma del chunk.
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

import pyarrow as pa

from regulabank.shared import schema

SEEDS_DIR = Path(__file__).resolve().parents[2] / "seeds"
CATALOG_PATH = SEEDS_DIR / "catalog.csv"
NORMS_PATH = SEEDS_DIR / "norms.csv"


# ----------------------------------------------------------------------------------------------------------
# Normalizacion y numeros en palabras
# ----------------------------------------------------------------------------------------------------------

_LEADING_ARTICLES = ("el ", "la ", "los ", "las ", "un ", "una ", "unos ", "unas ")
_EDGE_PUNCT = " .,;:()[]«»\"'-°º¿?¡!"


def norm_key(text: str) -> str:
    """Clave canonica: minusculas, sin tildes (conserva la ñ), sin puntuacion en bordes, sin articulo inicial."""
    s = text.lower().replace("ñ", "\x00")
    s = unicodedata.normalize("NFD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = s.replace("\x00", "ñ")
    s = re.sub(r"\s+", " ", s).strip().strip(_EDGE_PUNCT).strip()
    for article in _LEADING_ARTICLES:
        if s.startswith(article):
            s = s[len(article):]
            break
    return s


_UNITS = {
    "cero": 0, "un": 1, "uno": 1, "una": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5, "seis": 6, "siete": 7,
    "ocho": 8, "nueve": 9, "diez": 10, "once": 11, "doce": 12, "trece": 13, "catorce": 14, "quince": 15,
    "dieciseis": 16, "diecisiete": 17, "dieciocho": 18, "diecinueve": 19, "veinte": 20, "veintiun": 21,
    "veintiuno": 21, "veintidos": 22, "veintitres": 23, "veinticuatro": 24, "veinticinco": 25, "veintiseis": 26,
    "veintisiete": 27, "veintiocho": 28, "veintinueve": 29, "treinta": 30, "cuarenta": 40, "cincuenta": 50,
    "sesenta": 60, "setenta": 70, "ochenta": 80, "noventa": 90,
}
_HUNDREDS = {
    "cien": 100, "ciento": 100, "doscientos": 200, "trescientos": 300, "cuatrocientos": 400, "quinientos": 500,
    "seiscientos": 600, "setecientos": 700, "ochocientos": 800, "novecientos": 900,
}
_WORD_FORMS = sorted(
    set(_UNITS) | set(_HUNDREDS) | {"mil", "millon", "millones", "y", "dieciséis", "veintiún", "veintidós",
                                     "veintitrés", "veintiséis", "millón"},
    key=len, reverse=True,
)
_NUM_WORD = "(?:" + "|".join(re.escape(w) for w in _WORD_FORMS) + ")"
NUM_WORDS = rf"(?<!\w)(?!y\b){_NUM_WORD}(?:\s+{_NUM_WORD})*(?!\w)"


def words_to_number(phrase: str) -> int | None:
    """«diez mil» -> 10000; «veinticinco» -> 25; None si alguna palabra no es numero."""
    tokens = [t for t in norm_key(phrase).split(" ") if t and t != "y"]
    if not tokens:
        return None
    total, current = 0, 0
    for tok in tokens:
        if tok in _UNITS:
            current += _UNITS[tok]
        elif tok in _HUNDREDS:
            current += _HUNDREDS[tok]
        elif tok == "mil":
            total += (current or 1) * 1000
            current = 0
        elif tok in ("millon", "millones"):
            total += (current or 1) * 1_000_000
            current = 0
        else:
            return None
    return total + current


_NUM = r"\d{1,3}(?:[   .,]\d{3})+(?:[.,]\d{1,2})?|\d+(?:[.,]\d+)?"


def parse_number(raw: str) -> float:
    """«10 000», «10,000», «10.000,50», «10.5» -> float. Separador de miles = el que deja 3 digitos."""
    s = re.sub(r"[   ]", "", raw)
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".") if s.rfind(",") > s.rfind(".") else s.replace(",", "")
    elif "," in s:
        head, tail = s.rsplit(",", 1)
        s = s.replace(",", "") if len(tail) == 3 else f"{head}.{tail}"
    elif "." in s:
        head, tail = s.rsplit(".", 1)
        s = s.replace(".", "") if len(tail) == 3 else s
    return float(s)


def _clean_number(value: float) -> int | float:
    return int(value) if float(value).is_integer() else value


# ----------------------------------------------------------------------------------------------------------
# Mencion
# ----------------------------------------------------------------------------------------------------------


@dataclass
class Mention:
    chunk_id: str
    entity_id: str
    type: str
    mention: str
    start: int
    end: int
    score: float = 1.0
    method: str = "regex"
    value: dict[str, Any] | None = None

    @property
    def mention_id(self) -> str:
        return "m_" + hashlib.sha1(f"{self.chunk_id}:{self.type}:{self.start}:{self.end}".encode()).hexdigest()[:16]

    def row(self) -> dict[str, Any]:
        return {
            "mention_id": self.mention_id, "chunk_id": self.chunk_id, "entity_id": self.entity_id,
            "type": self.type, "mention": self.mention, "start": self.start, "end": self.end,
            "score": float(self.score), "method": self.method,
            "value": json.dumps(self.value, ensure_ascii=False) if self.value is not None else None,
        }


def to_table(mentions: Iterable[Mention]) -> pa.Table:
    rows = [m.row() for m in mentions]
    return pa.Table.from_pylist(rows, schema=schema.MENTIONS)


# ----------------------------------------------------------------------------------------------------------
# Referencias normativas
# ----------------------------------------------------------------------------------------------------------

# N.° N° Nº N.º N ° No. Nro.
_NO = r"(?:N\.?\s?[°º]|Nro\.?|No\.)"

# Patrones resolubles: (regex, funcion match -> norm_id). El orden importa: lo especifico antes de lo generico.
_NORM_RESOLVERS: list[tuple[re.Pattern[str], Any]] = [
    (re.compile(rf"Resoluci[oó]n\s+(?:S\.?B\.?S\.?|SBS)\s+{_NO}\s?(?P<num>\d{{1,6}})-(?P<year>\d{{4}})(?:-SBS)?", re.I),
     lambda m: f"pe-sbs-res-{int(m['num'])}-{m['year']}"),
    (re.compile(rf"Circular\s+{_NO}\s?(?P<num>\d{{3,5}})-(?P<year>\d{{4}})-BCRP", re.I),
     lambda m: f"pe-bcrp-cir-{m['num']}-{m['year']}"),
    (re.compile(rf"Circular\s+(?:SBS\s+)?{_NO}\s?(?P<series>[A-Z]{{1,4}})-(?P<num>\d{{3,5}})-(?P<year>\d{{4}})", re.I),
     lambda m: f"pe-sbs-cir-{m['series'].lower()}-{m['num']}-{m['year']}"),
    (re.compile(rf"Ley\s+{_NO}\s?(?P<num>\d{{4,6}})", re.I),
     lambda m: f"pe-congreso-ley-{m['num']}"),
    # Nombre convencional de la Ley 26702 en todo texto SBS.
    (re.compile(r"Ley General(?: del Sistema Financiero(?: y del Sistema de Seguros(?: y Org[aá]nica de la "
                r"Superintendencia de Banca y Seguros)?)?)?", re.I),
     lambda m: "pe-congreso-ley-26702"),
    (re.compile(rf"Decreto\s+Legislativo\s+{_NO}\s?(?P<num>\d{{3,5}})", re.I),
     lambda m: f"pe-ejecutivo-dleg-{m['num']}"),
    (re.compile(rf"Decreto\s+Supremo\s+{_NO}\s?(?P<num>\d{{3,4}})-(?P<year>\d{{4}})-(?P<suffix>[A-Z]{{2,6}})", re.I),
     lambda m: f"pe-{m['suffix'].lower()}-ds-{m['num']}-{m['year']}"),
]
# Referencia con numero que no se pudo resolver: se guarda cruda.
_NORM_GENERIC = re.compile(
    rf"(?:Resoluci[oó]n|Circular|Ley|Decreto|Reglamento|Directiva|Oficio)\s+(?:[A-ZÁÉÍÓÚ][\w.]*\s+){{0,3}}{_NO}\s?"
    r"[\w./-]*\d[\w./-]*"
)


class NormAliases:
    """Nombres cortos de las normas del corpus (seeds/norms.csv: `short`, `title`, `aliases`) -> norm_id.

    Alternancia de mas largo a mas corto, sin distinguir mayusculas, con espacios flexibles y «N.°» tolerante.
    """

    def __init__(self, mapping: dict[str, str]):
        self.mapping = {k.strip(): v for k, v in mapping.items() if k.strip()}
        self.by_key = {norm_key(k): v for k, v in self.mapping.items()}
        variants = sorted(self.mapping, key=len, reverse=True)
        self.pattern = re.compile(
            "(?<!\\w)(?:" + "|".join(self._flexible(v) for v in variants) + ")(?!\\w)", re.I
        ) if variants else None

    @staticmethod
    def _flexible(variant: str) -> str:
        out = re.escape(variant)
        out = re.sub(r"\\\s+|\\ ", r"\\s+", out)
        out = out.replace("N\\.°", "N\\.?\\s?[°º]").replace("N°", "N\\.?\\s?[°º]")
        return out

    @classmethod
    def from_csv(cls, path: Path = NORMS_PATH) -> "NormAliases":
        mapping: dict[str, str] = {}
        if not Path(path).exists():
            return cls(mapping)
        with open(path, encoding="utf-8", newline="") as fh:
            for row in csv.DictReader(fh):
                names = [row.get("short") or "", row.get("title") or "", *(row.get("aliases") or "").split("|")]
                for name in names:
                    if name.strip():
                        mapping.setdefault(name.strip(), row["norm_id"])
        return cls(mapping)

    def extract(self, text: str, chunk_id: str = "") -> list[Mention]:
        if self.pattern is None:
            return []
        found: list[Mention] = []
        for m in self.pattern.finditer(text):
            norm_id = self.by_key.get(norm_key(m.group(0)))
            if norm_id is None:
                continue
            found.append(Mention(chunk_id, f"norm_ref:{norm_id}", "norm_ref", m.group(0), m.start(), m.end(),
                                 value={"norm_id": norm_id, "raw": m.group(0)}))
        return found


def extract_norm_refs(text: str, chunk_id: str = "", aliases: NormAliases | None = None) -> list[Mention]:
    """«Resolución SBS N.° 11356-2008» -> norm_ref:pe-sbs-res-11356-2008; alias del corpus primero; lo no
    resoluble queda crudo."""
    found: list[Mention] = []
    taken: list[tuple[int, int]] = []
    if aliases is not None:
        for m in aliases.extract(text, chunk_id):
            if any(m.start < e and m.end > s for s, e in taken):
                continue
            taken.append((m.start, m.end))
            found.append(m)
    for pattern, resolve in _NORM_RESOLVERS:
        for m in pattern.finditer(text):
            if any(m.start() < e and m.end() > s for s, e in taken):
                continue
            norm_id = resolve(m)
            taken.append((m.start(), m.end()))
            found.append(Mention(chunk_id, f"norm_ref:{norm_id}", "norm_ref", m.group(0), m.start(), m.end(),
                                 value={"norm_id": norm_id, "raw": m.group(0)}))
    for m in _NORM_GENERIC.finditer(text):
        if any(m.start() < e and m.end() > s for s, e in taken):
            continue
        taken.append((m.start(), m.end()))
        found.append(Mention(chunk_id, f"norm_ref:{norm_key(m.group(0))}", "norm_ref", m.group(0), m.start(),
                             m.end(), value={"norm_id": None, "raw": m.group(0)}))
    return sorted(found, key=lambda m: (m.start, m.end))


# ----------------------------------------------------------------------------------------------------------
# Referencias a articulos
# ----------------------------------------------------------------------------------------------------------

_ART_NO = r"\d{1,4}(?:-[A-Z])?"
# «artículo 8», «artículos 16 y 17», «artículos 8 al 12», «arts. 3, 4 y 5»: el primer numero y la cola de la lista.
_ARTICLE = re.compile(
    rf"(?<!\w)(?:art[ií]culos?|arts?\.)\s*(?P<first>{_ART_NO})\s?[°º]?"
    rf"(?P<rest>(?:\s*(?:,|y|e|al|a|hasta)\s+(?:el\s+)?{_ART_NO}\s?[°º]?(?!\w))*)",
    re.I,
)
_ART_ITEM = re.compile(rf"(?P<conn>,|y|e|al|a|hasta)\s+(?:el\s+)?(?P<no>{_ART_NO})", re.I)
_RANGE_CONN = {"al", "a", "hasta"}
_HEADER_TAIL = re.compile(r"\s*[°º]?\s*\.-")
_SENTENCE_SPLIT = re.compile(r"(?<=[.;])\s+(?=[A-ZÁÉÍÓÚÑ«(])")
# «artículo 8 de la Resolución…», «artículos 16 y 17, numeral 3.2, de la Ley…»: entre la lista y la norma solo
# puede haber un numeral/literal y la preposicion.
_LINK_AFTER = re.compile(
    r"^(?:\s*,?\s*(?:numeral|literal|inciso|p[aá]rrafo)\s+[\w.)]+)*"
    r"\s*,?\s*(?:de|del)\s+(?:la\s+|el\s+|los\s+|las\s+)?(?:citada\s+|mencionada\s+|referida\s+|presente\s+)?$",
    re.I,
)
# «la Resolución SBS N.° X, en su artículo 8», «…, con excepción de su artículo 10»: posesivo o articulo justo antes.
_LINK_BEFORE = re.compile(r"(?:^|\W)(?:su|sus|el|los|cuyo|cuyos)\s*$", re.I)
_NEAR_BEFORE = 40


def _sentence_bounds(text: str) -> list[tuple[int, int]]:
    bounds, start = [], 0
    for m in _SENTENCE_SPLIT.finditer(text):
        bounds.append((start, m.start()))
        start = m.end()
    bounds.append((start, len(text)))
    return bounds


def expand_range(range_from: str, article_no: str) -> list[str]:
    """«8 al 12» -> ["8", "9", "10", "11", "12"]; si algun extremo no es numero puro, solo los extremos."""
    if range_from.isdigit() and article_no.isdigit() and int(range_from) < int(article_no):
        return [str(n) for n in range(int(range_from), int(article_no) + 1)]
    return [range_from, article_no]


def extract_article_refs(text: str, chunk_id: str = "", norm_id: str | None = None,
                         article_id: str | None = None, norm_refs: list[Mention] | None = None,
                         aliases: NormAliases | None = None) -> list[Mention]:
    """«artículo 8 de la Resolución SBS N.° X» -> {norm_id: X, article_no: 8}; sin norma en la oracion, la misma
    norma del chunk (`norm_id`). Listas («16 y 17») dan una mencion por numero; rangos («8 al 12») marcan
    `range_from` en la mencion del extremo final.

    Se omiten el encabezado del propio articulo («Artículo 12.-») y las autorreferencias.
    """
    norm_refs = norm_refs if norm_refs is not None else extract_norm_refs(text, chunk_id, aliases)
    resolved = [m for m in norm_refs if m.value and m.value.get("norm_id")]
    bounds = _sentence_bounds(text)
    found: list[Mention] = []
    for m in _ARTICLE.finditer(text):
        if _HEADER_TAIL.match(text, m.end()):
            continue
        sent = next((b for b in bounds if b[0] <= m.start() < b[1]), (0, len(text)))
        after = [r for r in resolved if m.end() <= r.start < sent[1] and _LINK_AFTER.match(text[m.end():r.start])]
        before = [r for r in resolved if sent[0] <= r.end <= m.start() and m.start() - r.end <= _NEAR_BEFORE
                  and _LINK_BEFORE.search(text[r.end:m.start()])]
        ref_norm = after[0].value["norm_id"] if after else (before[-1].value["norm_id"] if before else None)
        target_norm = ref_norm or norm_id
        # (span_start, span_end, numero, range_from)
        items: list[tuple[int, int, str, str | None]] = [(m.start(), m.end("first"), m["first"].upper(), None)]
        rest_offset = m.start("rest")
        for item in _ART_ITEM.finditer(m["rest"]):
            prev_no = items[-1][2]
            conn = item["conn"].lower()
            items.append((rest_offset + item.start("no"), rest_offset + item.end("no"), item["no"].upper(),
                          prev_no if conn in _RANGE_CONN else None))
        for start, end, no, range_from in items:
            target = f"{target_norm}#art-{no}" if target_norm else f"art-{no}"
            if article_id and target == article_id and range_from is None:
                continue
            value: dict[str, Any] = {"norm_id": ref_norm, "article_no": no}
            if range_from is not None:
                value["range_from"] = range_from
            found.append(Mention(chunk_id, f"article_ref:{target}", "article_ref", text[start:end], start, end,
                                 value=value))
    return found


# ----------------------------------------------------------------------------------------------------------
# Plazos, montos, porcentajes
# ----------------------------------------------------------------------------------------------------------

_DEADLINE = re.compile(
    rf"(?P<num>{NUM_WORDS}|(?<!\w)\d{{1,4}})\s*(?:\(\s*(?P<digits>\d{{1,4}})\s*\))?\s+"
    r"(?P<unit>d[ií]as?\s+(?:h[aá]biles?|calendario|naturales?|[uú]tiles)|d[ií]as?|meses|mes|a[ñn]os?)(?!\w)",
    re.I,
)
_UNIT_MAP = (
    ("habil", "business_day"), ("util", "business_day"), ("calendario", "calendar_day"),
    ("natural", "calendar_day"), ("dia", "calendar_day"), ("mes", "month"), ("año", "year"),
)


def extract_deadlines(text: str, chunk_id: str = "") -> list[Mention]:
    """«quince (15) días hábiles» -> {n: 15, unit: business_day}; palabras y digitos, el parentesis manda."""
    found: list[Mention] = []
    for m in _DEADLINE.finditer(text):
        if m["digits"]:
            n: int | None = int(m["digits"])
        elif m["num"].strip().isdigit():
            n = int(m["num"])
        else:
            n = words_to_number(m["num"])
        if n is None:
            continue
        unit_text = norm_key(m["unit"])
        unit = next(u for k, u in _UNIT_MAP if k in unit_text)
        found.append(Mention(chunk_id, f"deadline:{n}-{unit}", "deadline", m.group(0), m.start(), m.end(),
                             value={"n": n, "unit": unit}))
    return found


_AMOUNT_SYMBOL = re.compile(rf"(?P<cur>S/\.?|US\$|USD|U\.S\.\$|\$)\s?(?P<num>{_NUM})(?!\w)")
_AMOUNT_WORDS = re.compile(
    rf"(?P<num>{_NUM}|{NUM_WORDS})\s+(?P<cur>nuevos soles|soles|d[oó]lares(?: americanos| de los Estados Unidos"
    r"(?: de Am[eé]rica)?)?)(?!\w)",
    re.I,
)


def _currency(raw: str) -> str:
    r = norm_key(raw)
    return "PEN" if r.startswith("s/") or "soles" in r else "USD"


def extract_amounts(text: str, chunk_id: str = "") -> list[Mention]:
    """«S/ 10 000», «USD 10,000», «diez mil dólares» -> {value, currency}."""
    found: list[Mention] = []
    for pattern in (_AMOUNT_SYMBOL, _AMOUNT_WORDS):
        for m in pattern.finditer(text):
            num = m["num"].strip()
            value = parse_number(num) if re.match(r"\d", num) else words_to_number(num)
            if value is None:
                continue
            value = _clean_number(value)
            cur = _currency(m["cur"])
            found.append(Mention(chunk_id, f"amount:{value}-{cur.lower()}", "amount", m.group(0), m.start(),
                                 m.end(), value={"value": value, "currency": cur}))
    return found


_PERCENT = re.compile(
    rf"(?P<num>{_NUM})\s?%|(?P<words>{NUM_WORDS})\s+por\s+ciento(?:\s*\(\s*(?P<pnum>{_NUM})\s?%\s*\))?",
    re.I,
)


def extract_percentages(text: str, chunk_id: str = "") -> list[Mention]:
    """«10 %», «diez por ciento (10%)» -> {value: 10}."""
    found: list[Mention] = []
    for m in _PERCENT.finditer(text):
        if m["num"]:
            value: float | int | None = parse_number(m["num"])
        elif m["pnum"]:
            value = parse_number(m["pnum"])
        else:
            value = words_to_number(m["words"])
        if value is None:
            continue
        value = _clean_number(value)
        found.append(Mention(chunk_id, f"percentage:{value}", "percentage", m.group(0), m.start(), m.end(),
                             value={"value": value}))
    return found


# ----------------------------------------------------------------------------------------------------------
# Terminos definidos
# ----------------------------------------------------------------------------------------------------------

_DEF_INLINE = re.compile(r"se\s+entiende\s+por\s+(?P<term>[^:;.,\n]{3,80}?)\s*:", re.I)
_DEF_LINE = re.compile(
    r"(?m)^[ \t]*(?:[a-z]\)|\d{1,2}\.(?:\d{1,2}\.?)?|[-•])?[ \t]*(?P<term>[A-ZÁÉÍÓÚÑ][^:\n]{2,60}?)[ \t]*:[ \t]+(?=\S)"
)
_DEF_CONTEXT = re.compile(r"definici[oó]n|se\s+entiende\s+por|para\s+(?:los\s+)?efectos|los siguientes t[eé]rminos", re.I)
_DEF_EXCLUDE = re.compile(r"^(?:art[ií]culo|anexo|cap[ií]tulo|t[ií]tulo|nota|ejemplo|secci[oó]n)\b", re.I)


def extract_defined_terms(text: str, chunk_id: str = "", path: str = "", article_id: str | None = None) -> list[Mention]:
    """«se entiende por Deudor minorista:» en cualquier parte; «X: aquella...» solo en articulos de definiciones."""
    found: list[Mention] = []
    seen: set[tuple[int, int]] = set()

    def add(m: re.Match[str]) -> None:
        term = m["term"].strip()
        span = (m.start("term"), m.start("term") + len(term))
        if span in seen or _DEF_EXCLUDE.match(term) or len(term.split()) > 6:
            return
        seen.add(span)
        found.append(Mention(chunk_id, f"defined_term:{norm_key(term)}", "defined_term", term, span[0], span[1],
                             value={"term": term, "defined_in": article_id}))

    for m in _DEF_INLINE.finditer(text):
        add(m)
    if _DEF_CONTEXT.search(path) or _DEF_CONTEXT.search(text):
        for m in _DEF_LINE.finditer(text):
            add(m)
    return found


# ----------------------------------------------------------------------------------------------------------
# Gazetteer (seeds/catalog.csv)
# ----------------------------------------------------------------------------------------------------------


@dataclass
class CatalogEntry:
    catalog_id: str
    type: str
    name: str
    aliases: list[str] = field(default_factory=list)


class Gazetteer:
    """Alternancia de nombres y alias del catalogo; siglas en mayusculas se comparan tal cual, el resto sin caso."""

    def __init__(self, entries: list[CatalogEntry]):
        self.entries = entries
        self.by_exact: dict[str, CatalogEntry] = {}
        self.by_lower: dict[str, CatalogEntry] = {}
        exact, loose = [], []
        for e in entries:
            for variant in [e.name, *e.aliases]:
                variant = variant.strip()
                if not variant:
                    continue
                if variant.isupper() and len(variant) >= 2:
                    self.by_exact[variant] = e
                    exact.append(variant)
                else:
                    self.by_lower[variant.lower()] = e
                    loose.append(variant)
        self.re_exact = self._compile(exact, 0)
        self.re_loose = self._compile(loose, re.I)

    @staticmethod
    def _compile(variants: list[str], flags: int) -> re.Pattern[str] | None:
        if not variants:
            return None
        alt = "|".join(re.escape(v) for v in sorted(set(variants), key=len, reverse=True))
        return re.compile(rf"(?<!\w)(?:{alt})(?!\w)", flags)

    @classmethod
    def from_csv(cls, path: Path = CATALOG_PATH) -> "Gazetteer":
        entries = []
        with open(path, encoding="utf-8", newline="") as fh:
            for row in csv.DictReader(fh):
                aliases = [a for a in (row.get("aliases") or "").split("|") if a.strip()]
                entries.append(CatalogEntry(row["catalog_id"], row["type"], row["name"], aliases))
        return cls(entries)

    def extract(self, text: str, chunk_id: str = "") -> list[Mention]:
        found: list[Mention] = []
        for pattern, lookup, key in ((self.re_exact, self.by_exact, False), (self.re_loose, self.by_lower, True)):
            if pattern is None:
                continue
            for m in pattern.finditer(text):
                surface = m.group(0)
                entry = lookup.get(surface.lower() if key else surface)
                if entry is None:
                    continue
                found.append(Mention(chunk_id, f"{entry.type}:{norm_key(entry.name)}", entry.type, surface,
                                     m.start(), m.end(), method="gazetteer",
                                     value={"catalog_id": entry.catalog_id, "name": entry.name}))
        return found


# ----------------------------------------------------------------------------------------------------------
# Orquestacion por chunk
# ----------------------------------------------------------------------------------------------------------

_PRIORITY = {"norm_ref": 0, "article_ref": 1, "deadline": 2, "amount": 3, "percentage": 4, "defined_term": 5}


def resolve_overlaps(mentions: list[Mention]) -> list[Mention]:
    """Entre tramos solapados gana el mas largo; a igual largo, el extractor mas formulaico."""
    ordered = sorted(mentions, key=lambda m: (-(m.end - m.start), m.start, _PRIORITY.get(m.type, 9)))
    kept: list[Mention] = []
    for m in ordered:
        if any(m.start < k.end and m.end > k.start for k in kept):
            continue
        kept.append(m)
    return sorted(kept, key=lambda m: (m.start, m.end))


def extract_text(text: str, chunk_id: str = "c_test", norm_id: str | None = None, article_id: str | None = None,
                 path: str = "", gazetteer: Gazetteer | None = None,
                 aliases: NormAliases | None = None) -> list[Mention]:
    """Todos los extractores sobre un texto; verifica `text[start:end] == mention` antes de devolver."""
    norm_refs = extract_norm_refs(text, chunk_id, aliases)
    candidates = [
        *norm_refs,
        *extract_article_refs(text, chunk_id, norm_id, article_id, norm_refs, aliases),
        *extract_deadlines(text, chunk_id),
        *extract_amounts(text, chunk_id),
        *extract_percentages(text, chunk_id),
        *extract_defined_terms(text, chunk_id, path, article_id),
    ]
    if gazetteer is not None:
        candidates.extend(gazetteer.extract(text, chunk_id))
    kept = resolve_overlaps(candidates)
    for m in kept:
        if text[m.start:m.end] != m.mention:
            raise ValueError(f"tramo inconsistente en {chunk_id}: {m!r}")
    return kept


def defined_terms_gazetteer(mentions: Iterable[Mention]) -> Gazetteer:
    """Los terminos definidos en el corpus, como catalogo: asi se detectan tambien donde se usan."""
    entries: dict[str, CatalogEntry] = {}
    for m in mentions:
        if m.type == "defined_term" and m.entity_id not in entries:
            entries[m.entity_id] = CatalogEntry(m.entity_id, "defined_term", m.mention)
    return Gazetteer(list(entries.values()))


def extract_chunks(chunks: pa.Table, gazetteer: Gazetteer | None = None,
                   aliases: NormAliases | None = None) -> pa.Table:
    """Tabla CHUNKS -> tabla MENTIONS (regex + gazetteer + alias de normas + usos de los terminos definidos)."""
    gazetteer = gazetteer or Gazetteer.from_csv()
    aliases = aliases if aliases is not None else NormAliases.from_csv()
    rows = chunks.select(["chunk_id", "text", "norm_id", "article_id", "parent_path"]).to_pylist()
    per_chunk: list[list[Mention]] = [
        extract_text(r["text"], r["chunk_id"], r["norm_id"], r["article_id"], r["parent_path"] or "", gazetteer,
                     aliases)
        for r in rows
    ]
    terms = defined_terms_gazetteer(m for ms in per_chunk for m in ms)
    mentions: list[Mention] = []
    for r, found in zip(rows, per_chunk):
        usages = [u for u in terms.extract(r["text"], r["chunk_id"])
                  if not any(u.start < k.end and u.end > k.start for k in found)]
        for u in usages:
            u.value = {"term": u.value["name"], "defined_in": None}
        mentions.extend(sorted(found + usages, key=lambda m: (m.start, m.end)))
    return to_table(mentions)
