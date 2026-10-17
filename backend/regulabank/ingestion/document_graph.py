from __future__ import annotations

import csv
import hashlib
import json
import re
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import fitz
import pyarrow as pa
import pyarrow.parquet as pq


PARSER_VERSION = "0.1.0"


@dataclass(frozen=True)
class SourceMeta:
    source_id: int
    norm_id: str
    kind: str
    issuer: str
    jurisdiction: str
    authority_tier: str
    authority_order: int | None
    binding: str
    topics: tuple[str, ...]
    page_start: int | None = None
    page_end: int | None = None
    end_marker: str | None = None


SOURCE_META: dict[int, SourceMeta] = {
    1: SourceMeta(1, "pe-congreso-ley-26702-1996", "law", "Congreso de la República", "PE", "pe-law", 400, "binding", ("financial-system", "prudential-regulation")),
    2: SourceMeta(2, "pe-ejecutivo-dleg-1531-2022", "legislative_decree", "Poder Ejecutivo", "PE", "pe-law", 400, "binding", ("capital-adequacy", "basel-iii"), 5, 10, "DECRETO LEGISLATIVO\nNº 1532"),
    3: SourceMeta(3, "pe-sbs-res-9075-2012", "sbs_resolution", "SBS", "PE", "pe-supervisor-resolution", 200, "repealed", ("liquidity-risk",)),
    4: SourceMeta(4, "pe-sbs-res-3296-2022", "sbs_resolution", "SBS", "PE", "pe-supervisor-resolution", 200, "historical", ("liquidity-risk",)),
    5: SourceMeta(5, "pe-sbs-res-4221-2023", "sbs_resolution", "SBS", "PE", "pe-supervisor-resolution", 200, "binding", ("liquidity-risk",)),
    6: SourceMeta(6, "pe-sbs-res-11356-2008", "sbs_resolution", "SBS", "PE", "pe-supervisor-resolution", 200, "binding", ("credit-risk", "provisions")),
    7: SourceMeta(7, "pe-sbs-res-6328-2009", "sbs_resolution", "SBS", "PE", "pe-supervisor-resolution", 200, "binding", ("market-risk",)),
    8: SourceMeta(8, "pe-sbs-res-2116-2009", "sbs_resolution", "SBS", "PE", "pe-supervisor-resolution", 200, "binding", ("operational-risk",)),
    9: SourceMeta(9, "pe-sbs-res-2660-2015", "sbs_resolution", "SBS", "PE", "pe-supervisor-resolution", 200, "binding", ("aml-cft",)),
    10: SourceMeta(10, "pe-congreso-ley-29733-2011", "law", "Congreso de la República", "PE", "pe-law", 400, "binding", ("data-protection",)),
    11: SourceMeta(11, "pe-minjus-ds-016-2024-jus", "supreme_decree", "MINJUSDH", "PE", "pe-executive-regulation", 300, "binding", ("data-protection",)),
    12: SourceMeta(12, "pe-sbs-res-504-2021", "sbs_resolution", "SBS", "PE", "pe-supervisor-resolution", 200, "binding", ("information-security", "cybersecurity")),
    13: SourceMeta(13, "pe-sbs-res-272-2017", "sbs_resolution", "SBS", "PE", "pe-supervisor-resolution", 200, "binding", ("corporate-governance", "outsourcing", "risk-management")),
    14: SourceMeta(14, "pe-congreso-ley-29440-2009", "law", "Congreso de la República", "PE", "pe-law", 400, "binding", ("payment-systems",)),
    15: SourceMeta(15, "pe-sbs-res-6523-2013", "sbs_resolution", "SBS", "PE", "pe-supervisor-resolution", 200, "binding", ("payment-cards", "authentication")),
    16: SourceMeta(16, "pe-sbs-res-789-2018", "sbs_resolution", "SBS/UIF-Perú", "PE", "pe-supervisor-resolution", 200, "binding", ("aml-cft", "suspicious-transaction-reporting")),
    18: SourceMeta(18, "int-bcbs-basel-framework-2026", "international_standard", "BCBS/BIS", "INT", "international-reference", None, "non_binding_reference", ("basel-iii", "prudential-regulation")),
    19: SourceMeta(19, "int-bcbs-oprisk-principles-2021", "international_guideline", "BCBS/BIS", "INT", "international-reference", None, "non_binding_reference", ("operational-risk",)),
    20: SourceMeta(20, "int-fatf-recommendations-2025", "international_standard", "FATF/GAFILAT", "INT", "international-reference", None, "non_binding_reference", ("aml-cft",), 1, 169),
    21: SourceMeta(21, "int-iso-iec-27001-2022", "commercial_standard", "ISO/IEC", "INT", "commercial-standard", None, "licensed_reference", ("information-security",)),
    22: SourceMeta(22, "int-iso-22301-2019", "commercial_standard", "ISO", "INT", "commercial-standard", None, "licensed_reference", ("business-continuity",)),
    23: SourceMeta(23, "eu-reg-2024-1689", "eu_regulation", "European Union", "EU", "eu-regulation", 400, "binding_in_eu", ("artificial-intelligence", "data-governance")),
}


HEADING_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("title", re.compile(r"^(T[IÍ]TULO|TITLE|PART[E]?)\s+([IVXLCDM]+|\d+|PRELIMINAR)\b\s*(.*)$", re.I)),
    ("subchapter", re.compile(r"^SUBCAP[IÍ]TULO\s+([IVXLCDM]+|\d+)\b\s*(.*)$", re.I)),
    ("chapter", re.compile(r"^(CAP[IÍ]TULO|CHAPTER)\s+([IVXLCDM]+|\d+)\b\s*(.*)$", re.I)),
    ("section", re.compile(r"^(SECCI[ÓO]N|SECTION)\s+([IVXLCDM]+|\d+)\b\s*(.*)$", re.I)),
    ("article", re.compile(r"^ART[IÍ]CULO\s+([0-9]+(?:\s*(?:BIS|TER|QUATER)|-[A-Z])?|PRIMERO|SEGUNDO|TERCERO|CUARTO|QUINTO|SEXTO|S[EÉ](?:P)?TIMO|OCTAVO|NOVENO|D[EÉ]CIMO|[IVXLCDM]+)\s*[°º.]?\s*(?:[-–—.:]+\s*)?(.*)$", re.I)),
    ("principle", re.compile(r"^PRINCIP(?:IO|LE)\s+([0-9]+)\s*[:.–-]?\s*(.*)$", re.I)),
    ("recommendation", re.compile(r"^RECOMENDACI[ÓO]N\s+([0-9]+)\s*[:.–-]?\s*(.*)$", re.I)),
    ("interpretive_note", re.compile(r"^NOTA\s+INTERPRETATIVA\s+DE\s+LA\s+RECOMENDACI[ÓO]N\s+([0-9]+)\s*(.*)$", re.I)),
    ("lettered_section", re.compile(r"^([A-H])\s*[–—-]\s+([A-ZÁÉÍÓÚÜÑ].+)$")),
    ("annex", re.compile(r"^(ANEXO|ANNEX)\s*(?:N[°º.]?\s*)?([A-Z0-9IVXLCDM.-]+)?\s*[:.–-]?\s*(.*)$", re.I)),
    ("provisions", re.compile(r"^(DISPOSICIONES(?:\s+COMPLEMENTARIAS)?(?:\s+FINALES)?(?:\s+TRANSITORIAS)?(?:\s+DEROGATORIAS)?(?:\s+Y\s+TRANSITORIAS)?|DISPOSICI[ÓO]N\s+(?:COMPLEMENTARIA\s+)?(?:FINAL|TRANSITORIA|DEROGATORIA).*)$", re.I)),
)

NUMBERED_HEADING_RE = re.compile(r"^(\d+(?:\.\d+){0,3})[.)]?\s+(.+)$")
DECIMAL_NUMERAL_RE = re.compile(r"^(\d+\.\d+(?:\.\d+)*)[.)]?\s+(.+)$")


REFERENCE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("sbs_resolution", re.compile(r"Resoluci[oó]n\s+(?:S\.?\s*B\.?\s*S\.?\s*)?(?:N[°º.\s]*|Nro\.?\s*)?0*(?P<number>\d{2,5})\s*[-–]\s*(?P<year>\d{4})", re.I)),
    ("legislative_decree", re.compile(r"Decreto\s+Legislativo\s+(?:N[°º.\s]*)?0*(?P<number>\d{2,5})(?:\s*[-–]\s*(?P<year>\d{4}))?", re.I)),
    ("supreme_decree", re.compile(r"Decreto\s+Supremo\s+(?:N[°º.\s]*)?0*(?P<number>\d{2,4})\s*[-–]\s*(?P<year>\d{4})(?:-[A-Z]+)?", re.I)),
    ("law", re.compile(r"Ley(?:\s+General)?\s+(?:N[°º.\s]*)?(?P<number>\d{4,5})(?:\s*[-–]\s*(?P<year>\d{4}))?", re.I)),
    ("iso", re.compile(r"ISO(?:/IEC)?\s+(?P<number>27001|22301)(?::(?P<year>\d{4}))?", re.I)),
    ("eu_regulation", re.compile(r"Reglamento\s*\(UE\)\s*(?P<year>\d{4})/(?P<number>\d{3,4})", re.I)),
)

PASSIVE_RELATIONS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("REPEALS", re.compile(r"(?:derogad[oa]|dejado\s+sin\s+efecto)\s+por(?:\s+la)?\s*$", re.I)),
    ("ADDS", re.compile(r"incorporad[oa]\s+por(?:\s+la)?\s*$", re.I)),
    ("MODIFIES", re.compile(r"(?:modificad[oa]|sustituid[oa]|actualizad[oa])\s+por(?:\s+la)?\s*$", re.I)),
)

ACTIVE_RELATIONS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("REPEALS", re.compile(r"\b(?:deroga(?:r|se)?|d[eé]jese\s+sin\s+efecto)\b", re.I)),
    ("ADDS", re.compile(r"\b(?:incorp[oó]rese|incorpora(?:r|n|se)?)\b", re.I)),
    ("MODIFIES", re.compile(r"\b(?:modif[ií]quese|modifica(?:r|n|se)?|sustit[uú]yase|sustituye)\b", re.I)),
    ("IMPLEMENTS", re.compile(r"\breglamenta(?:r|se)?\b", re.I)),
)

INTERVENING_LEGAL_REFERENCE_RE = re.compile(
    r"\b(?:Resoluci[oó]n(?:\s+SBS)?|Decreto(?:\s+Supremo|\s+Legislativo)?|Ley|Directiva|Reglamento\s*\([A-Z]{1,4}\))\b",
    re.I,
)
LEGAL_RELATION_TYPES = {"MODIFIES", "REPEALS", "ADDS", "IMPLEMENTS", "REPLACES", "REFERS_TO"}


KNOWN_RELATIONS: tuple[tuple[str, str, str, str], ...] = (
    ("pe-ejecutivo-dleg-1531-2022", "pe-congreso-ley-26702-1996", "MODIFIES", "El DL 1531 modifica expresamente la Ley 26702."),
    ("pe-sbs-res-3296-2022", "pe-sbs-res-9075-2012", "MODIFIES", "La Resolución SBS 3296-2022 modifica el reglamento aprobado por la Resolución SBS 9075-2012."),
    ("pe-sbs-res-4221-2023", "pe-sbs-res-9075-2012", "REPEALS", "La Resolución SBS 4221-2023 deroga el reglamento aprobado por la Resolución SBS 9075-2012."),
    ("pe-minjus-ds-016-2024-jus", "pe-congreso-ley-29733-2011", "IMPLEMENTS", "El DS 016-2024-JUS aprueba el Reglamento de la Ley 29733."),
    ("int-bcbs-oprisk-principles-2021", "external:bcbs195-2011", "REPLACES", "La revisión BCBS de 2021 sustituye los principios publicados como BCBS 195 en 2011."),
)


def _slug(value: str, max_length: int = 72) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii").lower()
    ascii_value = re.sub(r"[^a-z0-9]+", "-", ascii_value).strip("-")
    return (ascii_value or "node")[:max_length].rstrip("-")


def _clean_text(value: str) -> str:
    return (
        value.replace("\ufb01", "fi")
        .replace("\ufb02", "fl")
        .replace("\u00a0", " ")
        .replace("\x92", "'")
    )


def _clean_line(value: str) -> str:
    return re.sub(r"\s+", " ", _clean_text(value)).strip()


def _uppercase_ratio(value: str) -> float:
    letters = [character for character in value if character.isalpha()]
    if not letters:
        return 0.0
    return sum(character.isupper() for character in letters) / len(letters)


def _node_level(node_type: str, number: str = "") -> int:
    if node_type in {"annex", "provisions"}:
        return 1
    if node_type == "title":
        return 1
    if node_type in {"chapter", "lettered_section", "recommendation", "principle"}:
        return 2
    if node_type in {"subchapter", "section", "interpretive_note"}:
        return 3
    if node_type == "article":
        return 4
    if node_type in {"numbered_section", "numeral"}:
        return 3 + number.count(".")
    return 2


def _heading_type_from_toc(label: str) -> tuple[str, str]:
    clean = _clean_line(label)
    for node_type, pattern in HEADING_PATTERNS:
        match = pattern.match(clean)
        if match:
            groups = match.groups()
            if node_type == "subchapter":
                number = groups[0]
            else:
                number = groups[1] if node_type in {"title", "chapter", "section"} else groups[0]
            return node_type, str(number or "")
    standard = re.match(r"^([A-Z]{2,5})(?:\s+|$)", clean)
    if standard:
        return "standard_section", standard.group(1)
    numeric = re.match(r"^(\d+(?:\.\d+)*)\s+", clean)
    if numeric:
        return "numbered_section", numeric.group(1)
    return "section", ""


def _make_node_id(norm_id: str, node_type: str, number: str, title: str, seen: Counter[str]) -> str:
    token = _slug(number or title)
    key = f"{node_type}:{token}"
    seen[key] += 1
    suffix = "" if seen[key] == 1 else f"-occ{seen[key]}"
    prefix = {
        "article": "art",
        "chapter": "chap",
        "title": "title",
        "section": "sec",
        "subchapter": "subchap",
        "annex": "annex",
        "provisions": "prov",
        "numbered_section": "nsec",
        "numeral": "num",
        "recommendation": "rec",
        "principle": "principle",
        "interpretive_note": "note",
        "standard_section": "std",
        "lettered_section": "lsec",
    }.get(node_type, node_type)
    return f"{norm_id}#{prefix}-{token}{suffix}"


def _edge_id(source_id: str, target_id: str, edge_type: str) -> str:
    digest = hashlib.sha1(f"{source_id}|{target_id}|{edge_type}".encode("utf-8")).hexdigest()[:18]
    return f"e_{digest}"


def _read_manifest(root: Path) -> list[dict[str, Any]]:
    manifest_path = root / "manifest.json"
    return json.loads(manifest_path.read_text(encoding="utf-8-sig"))


def _select_source_rows(root: Path) -> list[tuple[SourceMeta, dict[str, Any], Path]]:
    rows = []
    for item in _read_manifest(root):
        source_id = int(item["id"])
        if source_id not in SOURCE_META:
            continue
        meta = SOURCE_META[source_id]
        rows.append((meta, item, root / item["archivo"]))
    return sorted(rows, key=lambda entry: entry[0].source_id)


def _sample_text_quality(document: fitz.Document, start: int, end: int) -> tuple[int, int]:
    page_indexes = list(range(start, min(end, start + 5)))
    if end - start > 5:
        page_indexes.extend([start + (end - start) // 2, end - 1])
    page_indexes = sorted(set(index for index in page_indexes if start <= index < end))
    chars = sum(len(_clean_text(document[index].get_text("text"))) for index in page_indexes)
    return chars, len(page_indexes)


def _extract_pages(document: fitz.Document, meta: SourceMeta) -> list[dict[str, Any]]:
    start = max(0, (meta.page_start or 1) - 1)
    end = min(len(document), meta.page_end or len(document))
    pages: list[dict[str, Any]] = []
    for page_index in range(start, end):
        text = _clean_text(document[page_index].get_text("text"))
        if meta.end_marker and meta.end_marker in text:
            text = text.split(meta.end_marker, 1)[0]
        lines = [_clean_line(line) for line in text.splitlines()]
        lines = [line for line in lines if line]
        pages.append({"page": page_index + 1, "text": text, "lines": lines})
        if meta.end_marker and meta.end_marker in _clean_text(document[page_index].get_text("text")):
            break
    return pages


def _detect_index_pages(pages: list[dict[str, Any]]) -> set[int]:
    index_position = next(
        (position for position, page in enumerate(pages) if any(re.fullmatch(r"[ÍI]NDICE|CONTENIDO", line, re.I) for line in page["lines"])),
        None,
    )
    if index_position is None:
        return set()

    anchor_key = None
    for line in pages[index_position]["lines"]:
        heading = _parse_heading(line, "")
        if heading and heading[0] in {"chapter", "article", "recommendation", "title"}:
            anchor_key = _slug(f"{heading[0]}-{heading[1]}")
            break

    if not anchor_key:
        return {pages[index_position]["page"]}

    for later in range(index_position + 1, len(pages)):
        for line in pages[later]["lines"]:
            heading = _parse_heading(line, "")
            if heading and _slug(f"{heading[0]}-{heading[1]}") == anchor_key:
                return {page["page"] for page in pages[index_position:later]}
    return {pages[index_position]["page"]}


def _parse_heading(line: str, next_line: str) -> tuple[str, str, str, float] | None:
    clean = _clean_line(line)
    if not clean or len(clean) > 280:
        return None
    if re.fullmatch(r"\d+\s+NORMAS\s+LEGALES", clean, re.I):
        return None

    for node_type, pattern in HEADING_PATTERNS:
        match = pattern.match(clean)
        if not match:
            continue
        groups = [str(value or "").strip() for value in match.groups()]
        if node_type in {"title", "chapter", "section"}:
            number = groups[1]
            trailing = groups[2]
        elif node_type == "subchapter":
            number = groups[0]
            trailing = groups[1]
        elif node_type == "annex":
            number = groups[1]
            trailing = groups[2]
        elif node_type == "provisions":
            number = ""
            trailing = groups[0]
        elif node_type == "lettered_section":
            number = groups[0]
            trailing = groups[1]
        else:
            number = groups[0]
            trailing = groups[1] if len(groups) > 1 else ""
        if node_type in {"title", "chapter", "section", "subchapter"} and number == "l":
            number = "I"
        if node_type == "article" and trailing and trailing[0].islower():
            escaped_number = re.escape(number)
            has_heading_delimiter = re.match(
                rf"^ART[IÍ]CULO\s+{escaped_number}\s*[°º.]?\s*[-–—.:]+",
                clean,
                re.I,
            )
            if not has_heading_delimiter:
                return None
        if not trailing and next_line and len(next_line) <= 220 and _uppercase_ratio(next_line) >= 0.65:
            trailing = next_line
        title = clean if not trailing else f"{clean} {trailing}" if trailing not in clean else clean
        return node_type, number, title, 0.98

    decimal = DECIMAL_NUMERAL_RE.match(clean)
    if decimal and len(decimal.group(2)) <= 220 and _uppercase_ratio(decimal.group(2)) >= 0.55:
        return "numeral", decimal.group(1), clean, 0.91

    numbered = NUMBERED_HEADING_RE.match(clean)
    if numbered and len(numbered.group(2)) <= 220 and _uppercase_ratio(numbered.group(2)) >= 0.72:
        return "numbered_section", numbered.group(1), clean, 0.88

    if re.fullmatch(r"\d+(?:\.\d+){0,3}[.)]?", clean) and next_line and _uppercase_ratio(next_line) >= 0.72:
        number = clean.rstrip(".)")
        return "numbered_section", number, f"{clean} {next_line}", 0.84
    return None


def _finalize_hierarchy(norm_id: str, candidates: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    seen: Counter[str] = Counter()
    stack: list[tuple[int, str]] = []
    sibling_previous: dict[str, str] = {}
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []

    for ordinal, candidate in enumerate(candidates, start=1):
        node_type = candidate["node_type"]
        number = candidate.get("number", "")
        level = int(candidate.get("level") or _node_level(node_type, number))
        while stack and stack[-1][0] >= level:
            stack.pop()
        parent_id = stack[-1][1] if stack else norm_id
        node_id = _make_node_id(norm_id, node_type, number, candidate["title"], seen)
        node = {
            "node_id": node_id,
            "node_type": node_type,
            "label": candidate["title"],
            "norm_id": norm_id,
            "subtype": node_type,
            "number": number,
            "title": candidate["title"],
            "parent_id": parent_id,
            "ordinal": ordinal,
            "level": level,
            "page_start": candidate.get("page_start"),
            "page_end": candidate.get("page_start"),
            "char_start": candidate.get("char_start"),
            "char_end": None,
            "source_path": candidate["source_path"],
            "method": candidate["method"],
            "confidence": candidate["confidence"],
            "metadata_json": json.dumps(candidate.get("metadata", {}), ensure_ascii=False, sort_keys=True),
        }
        nodes.append(node)
        edges.append(_edge_row(node_id, parent_id, "PARENT", norm_id, node["page_start"], node["title"], node["method"], node["confidence"], True))
        if parent_id in sibling_previous:
            edges.append(_edge_row(sibling_previous[parent_id], node_id, "NEXT_SIBLING", norm_id, node["page_start"], "", "structure", 1.0, True))
        sibling_previous[parent_id] = node_id
        stack.append((level, node_id))

    for index, node in enumerate(nodes):
        end_page = node["page_start"]
        end_char = None
        for following in nodes[index + 1 :]:
            if following["level"] <= node["level"]:
                end_page = max(node["page_start"] or 0, (following["page_start"] or node["page_start"] or 1) - 1)
                end_char = following["char_start"]
                break
        else:
            if nodes:
                end_page = max(entry["page_start"] or 0 for entry in nodes)
        node["page_end"] = end_page
        node["char_end"] = end_char
    return nodes, edges


def _hierarchy_from_bookmarks(norm_id: str, source_path: str, document: fitz.Document, meta: SourceMeta) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    toc = document.get_toc(simple=True)
    if not toc:
        return [], []
    page_counts = Counter(page for _, _, page in toc)
    min_page = min(page_counts)
    max_page = max(page_counts)
    candidates: list[dict[str, Any]] = []
    for level, label, page in toc:
        if page_counts[page] >= 5 and page <= min_page + 2 and max_page > page + 2:
            continue
        if meta.page_start and page < meta.page_start:
            continue
        if meta.page_end and page > meta.page_end:
            continue
        node_type, number = _heading_type_from_toc(label)
        candidates.append({
            "node_type": node_type,
            "number": number,
            "title": _clean_line(label),
            "level": level,
            "page_start": page,
            "char_start": None,
            "source_path": source_path,
            "method": "pdf_bookmark",
            "confidence": 0.99,
            "metadata": {},
        })
    return _finalize_hierarchy(norm_id, candidates)


def _hierarchy_from_regex(norm_id: str, source_path: str, pages: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    index_pages = _detect_index_pages(pages)
    candidates: list[dict[str, Any]] = []
    offset = 0
    for page in pages:
        lines = page["lines"]
        for line_index, line in enumerate(lines):
            next_line = lines[line_index + 1] if line_index + 1 < len(lines) else ""
            is_page_number = bool(re.fullmatch(r"\d+", line)) and int(line) == page["page"]
            heading = None if is_page_number else _parse_heading(line, next_line)
            line_offset = offset
            offset += len(line) + 1
            if not heading or page["page"] in index_pages:
                continue
            node_type, number, title, confidence = heading
            candidates.append({
                "node_type": node_type,
                "number": number,
                "title": title,
                "level": _node_level(node_type, number),
                "page_start": page["page"],
                "char_start": line_offset,
                "source_path": source_path,
                "method": "regex",
                "confidence": confidence,
                "metadata": {"index_pages_skipped": sorted(index_pages)},
            })
        offset += 1
    return _finalize_hierarchy(norm_id, candidates)


def _edge_row(
    source_id: str,
    target_id: str,
    edge_type: str,
    norm_id: str,
    page: int | None,
    evidence: str,
    method: str,
    confidence: float,
    resolved: bool,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    review_status = (
        "candidate"
        if method == "regex" and edge_type in LEGAL_RELATION_TYPES
        else "accepted"
    )
    return {
        "edge_id": _edge_id(source_id, target_id, edge_type),
        "source_id": source_id,
        "target_id": target_id,
        "edge_type": edge_type,
        "norm_id": norm_id,
        "page": page,
        "evidence": evidence[:500],
        "method": method,
        "confidence": confidence,
        "resolved": resolved,
        "review_status": review_status,
        "metadata_json": json.dumps(metadata or {}, ensure_ascii=False, sort_keys=True),
    }


def _reference_index() -> dict[tuple[str, str, str], str]:
    index: dict[tuple[str, str, str], str] = {}
    for meta in SOURCE_META.values():
        if meta.kind == "sbs_resolution":
            match = re.search(r"res-(\d+)-(\d{4})$", meta.norm_id)
            if match:
                index[("sbs_resolution", str(int(match.group(1))), match.group(2))] = meta.norm_id
        elif meta.kind == "law":
            match = re.search(r"ley-(\d+)-(\d{4})$", meta.norm_id)
            if match:
                index[("law", str(int(match.group(1))), "")] = meta.norm_id
        elif meta.kind == "legislative_decree":
            match = re.search(r"dleg-(\d+)-(\d{4})$", meta.norm_id)
            if match:
                index[("legislative_decree", str(int(match.group(1))), match.group(2))] = meta.norm_id
                index[("legislative_decree", str(int(match.group(1))), "")] = meta.norm_id
        elif meta.kind == "supreme_decree":
            match = re.search(r"ds-(\d+)-(\d{4})", meta.norm_id)
            if match:
                index[("supreme_decree", str(int(match.group(1))), match.group(2))] = meta.norm_id
        elif meta.kind == "commercial_standard":
            if "27001" in meta.norm_id:
                index[("iso", "27001", "")] = meta.norm_id
            if "22301" in meta.norm_id:
                index[("iso", "22301", "")] = meta.norm_id
        elif meta.kind == "eu_regulation":
            index[("eu_regulation", "1689", "2024")] = meta.norm_id
    return index


def _relation_type(context_before: str, context: str) -> tuple[str, bool, float]:
    for relation, pattern in PASSIVE_RELATIONS:
        if pattern.search(context_before[-100:]):
            return relation, True, 0.96
    for relation, pattern in ACTIVE_RELATIONS:
        window = context_before[-140:]
        matches = list(pattern.finditer(window))
        if not matches:
            continue
        tail_after_verb = window[matches[-1].end() :]
        if INTERVENING_LEGAL_REFERENCE_RE.search(tail_after_verb):
            continue
        return relation, False, 0.91
    return "REFERS_TO", False, 0.84


def _source_node_for_page(norm_id: str, page: int, hierarchy_nodes: list[dict[str, Any]]) -> str:
    candidates = [
        node for node in hierarchy_nodes
        if node["norm_id"] == norm_id
        and node["page_start"] is not None
        and node["page_end"] is not None
        and node["page_start"] <= page <= node["page_end"]
    ]
    if not candidates:
        return norm_id
    return max(candidates, key=lambda node: (node["level"], node["page_start"], node["ordinal"]))["node_id"]


def _extract_norm_relations(meta: SourceMeta, pages: list[dict[str, Any]], hierarchy_nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    reference_index = _reference_index()
    aggregated: dict[tuple[str, str, str], dict[str, Any]] = {}
    for page in pages:
        text = _clean_text(page["text"])
        for kind, pattern in REFERENCE_PATTERNS:
            for match in pattern.finditer(text):
                number = str(int(match.group("number")))
                year = match.groupdict().get("year") or ""
                key = (kind, number, year)
                target_id = reference_index.get(key) or reference_index.get((kind, number, ""))
                if target_id is None:
                    target_id = f"unresolved:{kind}:{number}{('-' + year) if year else ''}"
                if target_id == meta.norm_id:
                    continue
                before = text[max(0, match.start() - 140) : match.start()]
                context = text[max(0, match.start() - 140) : min(len(text), match.end() + 140)]
                relation, reverse, confidence = _relation_type(before, context)
                source_node = meta.norm_id
                source_id, final_target = (target_id, source_node) if reverse else (source_node, target_id)
                aggregate_key = (source_id, final_target, relation)
                evidence = _clean_line(context)
                if aggregate_key not in aggregated:
                    aggregated[aggregate_key] = _edge_row(
                        source_id, final_target, relation, meta.norm_id, page["page"], evidence,
                        "regex", confidence, not target_id.startswith("unresolved:"),
                        {"mentions": 1, "pages": [page["page"]]},
                    )
                else:
                    payload = json.loads(aggregated[aggregate_key]["metadata_json"])
                    payload["mentions"] += 1
                    if page["page"] not in payload["pages"]:
                        payload["pages"].append(page["page"])
                    aggregated[aggregate_key]["metadata_json"] = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return list(aggregated.values())


def _root_node(meta: SourceMeta, manifest_row: dict[str, Any], source_path: str) -> dict[str, Any]:
    return {
        "node_id": meta.norm_id,
        "node_type": "norm",
        "label": manifest_row["titulo"],
        "norm_id": meta.norm_id,
        "subtype": meta.kind,
        "number": "",
        "title": manifest_row["titulo"],
        "parent_id": "",
        "ordinal": 0,
        "level": 0,
        "page_start": meta.page_start,
        "page_end": meta.page_end,
        "char_start": None,
        "char_end": None,
        "source_path": source_path,
        "method": "catalog",
        "confidence": 1.0,
        "metadata_json": json.dumps({
            "source_id": meta.source_id,
            "kind": meta.kind,
            "issuer": meta.issuer,
            "jurisdiction": meta.jurisdiction,
            "authority_tier": meta.authority_tier,
            "authority_order": meta.authority_order,
            "binding": meta.binding,
            "status": manifest_row["vigencia"],
            "source_sha256": manifest_row["sha256"],
            "url": manifest_row["url_validada"],
        }, ensure_ascii=False, sort_keys=True),
    }


def _write_parquet(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    row_list = list(rows)
    if not row_list:
        return
    table = pa.Table.from_pylist(row_list)
    pq.write_table(table, path, compression="zstd")


def build_document_graph(source_root: Path, output_root: Path) -> dict[str, Any]:
    source_root = source_root.resolve()
    output_root.mkdir(parents=True, exist_ok=True)

    graph_nodes: list[dict[str, Any]] = []
    graph_edges: list[dict[str, Any]] = []
    hierarchy_nodes: list[dict[str, Any]] = []
    report_rows: list[dict[str, Any]] = []
    auxiliary_nodes: dict[str, dict[str, Any]] = {}

    for meta, manifest_row, artifact_path in _select_source_rows(source_root):
        relative_path = str(artifact_path.relative_to(source_root.parent))
        root_node = _root_node(meta, manifest_row, relative_path)
        graph_nodes.append(root_node)

        issuer_id = f"issuer:{_slug(meta.issuer)}"
        auxiliary_nodes.setdefault(issuer_id, {
            "node_id": issuer_id, "node_type": "issuer", "label": meta.issuer, "norm_id": "", "subtype": "issuer",
            "number": "", "title": meta.issuer, "parent_id": "", "ordinal": 0, "level": 0,
            "page_start": None, "page_end": None, "char_start": None, "char_end": None, "source_path": "",
            "method": "catalog", "confidence": 1.0, "metadata_json": "{}",
        })
        graph_edges.append(_edge_row(meta.norm_id, issuer_id, "ISSUED_BY", meta.norm_id, None, "", "catalog", 1.0, True))

        tier_id = f"authority-tier:{meta.authority_tier}"
        auxiliary_nodes.setdefault(tier_id, {
            "node_id": tier_id, "node_type": "authority_tier", "label": meta.authority_tier, "norm_id": "", "subtype": "authority_tier",
            "number": "", "title": meta.authority_tier, "parent_id": "", "ordinal": 0, "level": 0,
            "page_start": None, "page_end": None, "char_start": None, "char_end": None, "source_path": "",
            "method": "catalog", "confidence": 1.0,
            "metadata_json": json.dumps({"jurisdiction": meta.jurisdiction, "authority_order": meta.authority_order}, sort_keys=True),
        })
        graph_edges.append(_edge_row(meta.norm_id, tier_id, "HAS_AUTHORITY_TIER", meta.norm_id, None, "", "catalog", 1.0, True))

        for topic in meta.topics:
            topic_id = f"topic:{topic}"
            auxiliary_nodes.setdefault(topic_id, {
                "node_id": topic_id, "node_type": "topic", "label": topic.replace("-", " "), "norm_id": "", "subtype": "topic",
                "number": "", "title": topic.replace("-", " "), "parent_id": "", "ordinal": 0, "level": 0,
                "page_start": None, "page_end": None, "char_start": None, "char_end": None, "source_path": "",
                "method": "catalog", "confidence": 1.0, "metadata_json": "{}",
            })
            graph_edges.append(_edge_row(meta.norm_id, topic_id, "REGULATES", meta.norm_id, None, "", "catalog", 1.0, True))

        if artifact_path.suffix.lower() != ".pdf":
            report_rows.append({
                "source_id": meta.source_id, "norm_id": meta.norm_id, "title": manifest_row["titulo"],
                "source_path": relative_path, "pages": 0, "sample_chars": 0, "toc_entries": 0,
                "hierarchy_nodes": 0, "explicit_relations": 0, "parse_status": "URL_ONLY",
                "gate": "BLOCKED_NO_PUBLIC_TEXT", "notes": "Referencia oficial sin texto redistribuible o colección dinámica.",
            })
            continue

        document = fitz.open(artifact_path)
        scope_start = max(0, (meta.page_start or 1) - 1)
        scope_end = min(len(document), meta.page_end or len(document))
        sample_chars, sampled_pages = _sample_text_quality(document, scope_start, scope_end)
        average_sample_chars = sample_chars / max(1, sampled_pages)
        toc_entries = len(document.get_toc(simple=True))

        if average_sample_chars < 80:
            report_rows.append({
                "source_id": meta.source_id, "norm_id": meta.norm_id, "title": manifest_row["titulo"],
                "source_path": relative_path, "pages": scope_end - scope_start, "sample_chars": sample_chars,
                "toc_entries": toc_entries, "hierarchy_nodes": 0, "explicit_relations": 0,
                "parse_status": "OCR_REQUIRED", "gate": "QUARANTINE_OCR",
                "notes": "PDF de imagen sin capa de texto suficiente; no entra al gold estructural.",
            })
            continue

        pages: list[dict[str, Any]] = []
        if toc_entries >= 8:
            nodes, edges = _hierarchy_from_bookmarks(meta.norm_id, relative_path, document, meta)
            parse_status = "PARSED_BOOKMARKS"
            if scope_end - scope_start <= 500:
                pages = _extract_pages(document, meta)
        else:
            pages = _extract_pages(document, meta)
            nodes, edges = _hierarchy_from_regex(meta.norm_id, relative_path, pages)
            parse_status = "PARSED_REGEX"

        relations = _extract_norm_relations(meta, pages, nodes) if pages else []
        hierarchy_nodes.extend(nodes)
        graph_nodes.extend(nodes)
        graph_edges.extend(edges)
        graph_edges.extend(relations)

        gate = "PASS" if nodes else "QUARANTINE_NO_STRUCTURE"
        report_rows.append({
            "source_id": meta.source_id, "norm_id": meta.norm_id, "title": manifest_row["titulo"],
            "source_path": relative_path, "pages": scope_end - scope_start, "sample_chars": sample_chars,
            "toc_entries": toc_entries, "hierarchy_nodes": len(nodes), "explicit_relations": len(relations),
            "parse_status": parse_status, "gate": gate,
            "notes": "" if nodes else "No se detectaron encabezados estructurales; requiere revisión de reglas.",
        })

    for source_id, target_id, edge_type, evidence in KNOWN_RELATIONS:
        graph_edges.append(_edge_row(
            source_id, target_id, edge_type, source_id, None, evidence,
            "validated_catalog", 1.0, not target_id.startswith("external:"),
        ))

    graph_nodes.extend(auxiliary_nodes.values())

    existing_node_ids = {node["node_id"] for node in graph_nodes}
    missing_endpoint_ids = {
        endpoint
        for edge in graph_edges
        for endpoint in (edge["source_id"], edge["target_id"])
        if endpoint not in existing_node_ids
    }
    for endpoint in sorted(missing_endpoint_ids):
        graph_nodes.append({
            "node_id": endpoint,
            "node_type": "external_norm",
            "label": endpoint.replace("unresolved:", "").replace("external:", ""),
            "norm_id": "",
            "subtype": "unresolved" if endpoint.startswith("unresolved:") else "external",
            "number": "",
            "title": endpoint,
            "parent_id": "",
            "ordinal": 0,
            "level": 0,
            "page_start": None,
            "page_end": None,
            "char_start": None,
            "char_end": None,
            "source_path": "",
            "method": "relation_placeholder",
            "confidence": 1.0,
            "metadata_json": json.dumps({"requires_catalog_resolution": endpoint.startswith("unresolved:")}, sort_keys=True),
        })

    edge_by_key: dict[tuple[str, str, str], dict[str, Any]] = {}
    for edge in graph_edges:
        key = (edge["source_id"], edge["target_id"], edge["edge_type"])
        current = edge_by_key.get(key)
        if current is None:
            edge_by_key[key] = edge
            continue
        candidate_score = (edge["review_status"] == "accepted", edge["confidence"])
        current_score = (current["review_status"] == "accepted", current["confidence"])
        if candidate_score > current_score:
            edge_by_key[key] = edge
    graph_edges = list(edge_by_key.values())

    node_ids = [node["node_id"] for node in graph_nodes]
    duplicate_node_ids = [node_id for node_id, count in Counter(node_ids).items() if count > 1]
    if duplicate_node_ids:
        raise ValueError(f"Duplicate graph node ids: {duplicate_node_ids[:10]}")
    node_id_set = set(node_ids)
    dangling_edges = [
        edge for edge in graph_edges
        if edge["source_id"] not in node_id_set or edge["target_id"] not in node_id_set
    ]
    if dangling_edges:
        raise ValueError(f"Dangling graph edges: {dangling_edges[:3]}")

    _write_parquet(output_root / "graph_nodes.parquet", graph_nodes)
    _write_parquet(output_root / "graph_edges.parquet", graph_edges)
    _write_parquet(output_root / "hierarchy_nodes.parquet", hierarchy_nodes)
    relation_edges = [edge for edge in graph_edges if edge["edge_type"] in LEGAL_RELATION_TYPES]
    _write_parquet(
        output_root / "relation_candidates.parquet",
        [edge for edge in relation_edges if edge["review_status"] == "candidate"],
    )
    _write_parquet(
        output_root / "validated_relation_edges.parquet",
        [edge for edge in relation_edges if edge["review_status"] == "accepted"],
    )

    report_path = output_root / "extraction_report.csv"
    with report_path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(report_rows[0].keys()))
        writer.writeheader()
        writer.writerows(report_rows)

    node_types = Counter(node["node_type"] for node in graph_nodes)
    edge_types = Counter(edge["edge_type"] for edge in graph_edges)
    relation_statuses = Counter(edge["review_status"] for edge in relation_edges)
    gate_counts = Counter(row["gate"] for row in report_rows)
    manifest = {
        "parser_version": PARSER_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_manifest": str((source_root / "manifest.json").resolve()),
        "counts": {
            "source_records": len(report_rows),
            "graph_nodes": len(graph_nodes),
            "hierarchy_nodes": len(hierarchy_nodes),
            "graph_edges": len(graph_edges),
            "node_types": dict(sorted(node_types.items())),
            "edge_types": dict(sorted(edge_types.items())),
            "relation_statuses": dict(sorted(relation_statuses.items())),
            "gates": dict(sorted(gate_counts.items())),
        },
        "policy": {
            "hierarchy_parser": "deterministic_regex_or_pdf_bookmarks",
            "transformer_used": False,
            "regex_relations_enter_production": False,
            "ocr_content_enters_gold": False,
            "unresolved_references_retained": True,
        },
    }
    (output_root / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    readme = f"""# Extracción estructural GraphRAG v0

Este directorio contiene una primera extracción **determinista** de la jerarquía y las relaciones explícitas de las fuentes regulatorias.

## Resultado

- Fuentes regulatorias catalogadas: {len(report_rows)}
- Nodos estructurales: {len(hierarchy_nodes)}
- Nodos totales del grafo: {len(graph_nodes)}
- Aristas totales: {len(graph_edges)}
- Relaciones jurídicas validadas/candidatas: {relation_statuses.get("accepted", 0)}/{relation_statuses.get("candidate", 0)}
- Gates: {dict(sorted(gate_counts.items()))}

## Archivos

- `graph_nodes.parquet`: normas, títulos, capítulos, artículos/secciones, emisores, niveles de autoridad y temas.
- `graph_edges.parquet`: `PARENT`, `NEXT_SIBLING`, `ISSUED_BY`, `HAS_AUTHORITY_TIER`, `REGULATES` y relaciones normativas explícitas.
- `hierarchy_nodes.parquet`: vista especializada de la estructura interna de cada documento.
- `relation_candidates.parquet`: relaciones jurídicas detectadas por reglas que requieren validación.
- `validated_relation_edges.parquet`: relaciones jurídicas validadas para consumo directo.
- `extraction_report.csv`: cobertura y gate por fuente.
- `manifest.json`: conteos, versión del parser y política de uso de modelos.

## Decisión de arquitectura

La jerarquía no se extrae con un transformer. Los marcadores PDF y las reglas jurídicas son más precisos y auditables. Los transformers se reservan para embeddings, entidades abiertas y clasificación de relaciones ambiguas. Los PDF sin capa de texto quedan en `QUARANTINE_OCR` hasta pasar OCR y revisión.

## Limitaciones de esta versión

- Es una extracción de estructura, no el release final de artículos/versiones/chunks.
- Las relaciones regex se marcan como `candidate`; solo las de `validated_relation_edges.parquet` deben entrar al grafo de producción sin revisión adicional.
- Las referencias no resueltas se conservan como nodos externos para completar el catálogo sin inventar destinos.
- Las fuentes comerciales ISO solo tienen nodo de catálogo y acceso oficial; no se ingiere texto sin licencia.
- Antes del `gold` debe revisarse una muestra estratificada y medirse recall del parser contra artículos reales.
"""
    (output_root / "README.md").write_text(readme, encoding="utf-8")
    return manifest
