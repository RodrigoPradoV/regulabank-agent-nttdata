"""Corpus de fragmentos v0: un chunk por artículo, sección o numeral, sin modelos.

Reutiliza la jerarquía de `data/graph_ingest_v0` y reconstruye el texto con la misma lógica de
`document_graph`, de modo que los `char_start` de los nodos regex apuntan exactamente al mismo texto.
Los nodos de bookmarks (sin offset) se anclan buscando su título en la página indicada.
"""

from __future__ import annotations

import bisect
import csv
import hashlib
import io
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import fitz
import pyarrow as pa
import pyarrow.parquet as pq

from .document_graph import (
    SOURCE_META, SourceMeta, _clean_text, _detect_index_pages, _extract_pages, _read_manifest, _uppercase_ratio,
)


CORPUS_VERSION = "0.1.0"

SPLIT_THRESHOLD_CHARS = 3000   # por encima, el fragmento se divide por numerales
TARGET_CHUNK_CHARS = 2500      # empaquetado de numerales consecutivos del mismo artículo
LONG_UNSPLIT_CHARS = 8000      # fragmento largo sin numerales: se conserva entero y se marca para revisión
MAX_HEADING_LINES = 3

CHUNK_COLUMNS = (
    "chunk_id", "norm_id", "norm_short", "title", "issuer", "jurisdiction", "norm_kind", "status",
    "published", "valid_from", "valid_to", "source_url", "source_path", "source_sha256", "article_id",
    "article_no", "node_type", "parent_path", "page_start", "page_end", "text", "citation",
    "extraction_method", "confidence", "review_required", "review_reason",
)

CHUNK_SCHEMA = pa.schema([
    (name, pa.int32() if name in {"page_start", "page_end"}
     else pa.float64() if name == "confidence"
     else pa.bool_() if name == "review_required"
     else pa.string())
    for name in CHUNK_COLUMNS
])

# Abreviaturas de catálogo; no se derivan del texto.
NORM_SHORT: dict[str, str] = {
    "pe-congreso-ley-26702-1996": "Ley 26702",
    "pe-ejecutivo-dleg-1531-2022": "D. Leg. 1531",
    "pe-sbs-res-9075-2012": "Res. SBS 9075-2012",
    "pe-sbs-res-3296-2022": "Res. SBS 3296-2022",
    "pe-sbs-res-4221-2023": "Res. SBS 4221-2023",
    "pe-sbs-res-11356-2008": "Res. SBS 11356-2008",
    "pe-sbs-res-6328-2009": "Res. SBS 6328-2009",
    "pe-sbs-res-2116-2009": "Res. SBS 2116-2009",
    "pe-sbs-res-2660-2015": "Res. SBS 2660-2015",
    "pe-congreso-ley-29733-2011": "Ley 29733",
    "pe-minjus-ds-016-2024-jus": "D.S. 016-2024-JUS",
    "pe-sbs-res-504-2021": "Res. SBS 504-2021",
    "pe-sbs-res-272-2017": "Res. SBS 272-2017",
    "pe-congreso-ley-29440-2009": "Ley 29440",
    "pe-sbs-res-6523-2013": "Res. SBS 6523-2013",
    "pe-sbs-res-789-2018": "Res. SBS 789-2018",
    "int-bcbs-basel-framework-2026": "Basel Framework",
    "int-bcbs-oprisk-principles-2021": "BCBS PSMOR 2021",
    "int-fatf-recommendations-2025": "Recomendaciones GAFI 2025",
    "int-iso-iec-27001-2022": "ISO/IEC 27001:2022",
    "int-iso-22301-2019": "ISO 22301:2019",
    "eu-reg-2024-1689": "Reglamento (UE) 2024/1689",
}

CONTENT_NODE_TYPES = {
    "article", "numeral", "numbered_section", "recommendation", "interpretive_note", "principle",
    "annex", "provisions", "standard_section", "lettered_section",
}
CONTAINER_NODE_TYPES = {"title", "chapter", "subchapter", "section"}
MULTI_LEVEL_NUMERAL_RE = re.compile(r"^(\d+(?:\.\d+)+)\.?(?:\s+\S.*)?$")
SINGLE_LEVEL_NUMERAL_RE = re.compile(r"^(\d{1,3})[.)](?:\s+\S.*)?$")
DATE_RE = r"(\d{4}-\d{2}-\d{2})"
# Encabezado que en realidad continúa una cita: "artículo 187, o modelos..." / "Recomendación 10, a las..."
REFERENCE_LIKE_HEADING_RE = re.compile(
    r"^(?:ART[IÍ]CULO|RECOMENDACI[ÓO]N|PRINCIPIO|PRINCIPLE)\s+[\w-]+(?:\s+bis)?\s*[,;]", re.I,
)


@dataclass
class DocText:
    text: str
    lines: list[tuple[int, int, int, str]]          # (start, end, page, line)
    line_by_start: dict[int, int]
    page_spans: dict[int, tuple[int, int]]          # page -> (start, end)
    furniture: set[int] = field(default_factory=set)  # índices de línea de encabezado/pie repetido
    index_lines: set[int] = field(default_factory=set)

    @property
    def line_starts(self) -> list[int]:
        if not hasattr(self, "_line_starts"):
            self._line_starts = [start for start, *_rest in self.lines]
        return self._line_starts


@dataclass
class Anchor:
    start: int
    node: dict[str, Any] | None                    # None = preámbulo
    method: str
    anchored: bool


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _squash(value: str) -> str:
    return "".join(character.lower() for character in _clean_text(value) if not character.isspace())


def _short(value: str, limit: int = 80) -> str:
    value = re.sub(r"\s+", " ", value or "").strip()
    return value if len(value) <= limit else value[: limit - 1].rstrip() + "…"


def _build_doc_text(pages: list[dict[str, Any]]) -> DocText:
    """Mismo texto que `_hierarchy_from_regex`: líneas limpias + '\\n', y un '\\n' extra por página."""
    parts: list[str] = []
    lines: list[tuple[int, int, int, str]] = []
    page_spans: dict[int, tuple[int, int]] = {}
    offset = 0
    for page in pages:
        page_start = offset
        for line in page["lines"]:
            lines.append((offset, offset + len(line), page["page"], line))
            parts.append(line + "\n")
            offset += len(line) + 1
        parts.append("\n")
        offset += 1
        page_spans[page["page"]] = (page_start, offset)
    return DocText("".join(parts), lines, {start: index for index, (start, *_rest) in enumerate(lines)}, page_spans)


def _mark_furniture(doc: DocText) -> None:
    """Encabezados y pies repetidos: misma línea en el borde de al menos la mitad de las páginas."""
    by_page: dict[int, list[int]] = defaultdict(list)
    for index, (_start, _end, page, _line) in enumerate(doc.lines):
        by_page[page].append(index)
    threshold = max(3, len(by_page) // 2)
    exact: Counter[str] = Counter()
    digit_normalized: Counter[str] = Counter()
    edges: list[int] = []
    for indexes in by_page.values():
        edge = indexes[:3] + indexes[-3:]
        edges.extend(edge)
        exact.update({doc.lines[index][3] for index in edge})
        digit_normalized.update({re.sub(r"\d", "#", doc.lines[index][3]) for index in edge})
    for index in edges:
        _start, _end, page, line = doc.lines[index]
        letters = sum(character.isalpha() for character in line)
        is_page_number = bool(re.fullmatch(r"[\d\s/|-]+", line)) and str(page) in re.findall(r"\d+", line)
        if (
            (exact[line] >= threshold and len(line) >= 8)
            or (digit_normalized[re.sub(r"\d", "#", line)] >= threshold and letters >= 3 and len(line) <= 150)
            or is_page_number
        ):
            doc.furniture.add(index)


def _find_line_index(doc: DocText, offset: int) -> int:
    return max(0, bisect.bisect_right(doc.line_starts, offset) - 1)


def _anchor_bookmark(doc: DocText, node: dict[str, Any], floor: int) -> Anchor:
    """Busca el título del bookmark en su página (o la siguiente), sin retroceder del ancla previa."""
    page = int(node["page_start"])
    if page not in doc.page_spans:
        return Anchor(floor, node, "pymupdf+bookmark_page_fallback", False)
    window_start = max(floor, doc.page_spans[page][0])
    window_end = doc.page_spans.get(page + 1, doc.page_spans[page])[1]
    window = doc.text[window_start:window_end]
    squashed, positions = [], []
    for position, character in enumerate(window):
        if not character.isspace():
            lowered = character.lower()
            squashed.append(lowered if len(lowered) == 1 else character)
            positions.append(position)
    haystack = "".join(squashed)
    title = _squash(node["title"])
    for length in (80, 40, 20, 10):
        needle = title[:length]
        if len(needle) < 6:
            continue
        found = haystack.find(needle)
        if found >= 0:
            offset = window_start + positions[found]
            line_start = doc.lines[_find_line_index(doc, offset)][0]
            return Anchor(max(floor, line_start), node, "pymupdf+bookmark_title_match", True)
    return Anchor(window_start, node, "pymupdf+bookmark_page_fallback", False)


def _anchors(doc: DocText, nodes: list[dict[str, Any]]) -> list[Anchor]:
    anchors: list[Anchor] = []
    floor = 0
    for node in sorted(nodes, key=lambda item: item["ordinal"]):
        if node["method"] == "regex" and node["char_start"] is not None:
            start = int(node["char_start"])
            line_index = doc.line_by_start.get(start)
            anchored = line_index is not None and _squash(node["title"]).startswith(_squash(doc.lines[line_index][3]))
            if line_index is None:
                start = doc.lines[_find_line_index(doc, start)][0]
            anchors.append(Anchor(start, node, "pymupdf+regex_offset", anchored))
        else:
            anchor = _anchor_bookmark(doc, node, floor)
            anchors.append(anchor)
            floor = anchor.start
    anchors.sort(key=lambda anchor: (anchor.start, anchor.node["ordinal"]))
    first = anchors[0].start if anchors else len(doc.text)
    if first > 0:
        anchors.insert(0, Anchor(0, None, "pymupdf+preamble", True))
    return anchors


def _segment_lines(doc: DocText, start: int, end: int) -> list[int]:
    first = bisect.bisect_left(doc.line_starts, start)
    last = bisect.bisect_left(doc.line_starts, end)
    return [index for index in range(first, last) if index not in doc.furniture and index not in doc.index_lines]


def _has_text(line: str) -> bool:
    return any(character.isalnum() for character in line)


def _size(doc: DocText, line_indexes: list[int]) -> int:
    return sum(len(doc.lines[index][3]) + 1 for index in line_indexes)


def _heading_line_count(doc: DocText, line_indexes: list[int], node: dict[str, Any]) -> int:
    """Líneas iniciales que forman el encabezado: están en el título o, en contenedores, son mayúsculas cortas."""
    squashed_title = _squash(node["title"])
    container = node["node_type"] in CONTAINER_NODE_TYPES
    count, consumed = 1, len(_squash(doc.lines[line_indexes[0]][3]))
    for index in line_indexes[1:MAX_HEADING_LINES]:
        line = doc.lines[index][3]
        piece = _squash(line)
        in_title = len(piece) >= 4 and piece in squashed_title and consumed + len(piece) <= len(squashed_title) + 8
        upper_continuation = container and len(line) <= 120 and _uppercase_ratio(line) >= 0.65
        if not (in_title or upper_continuation):
            break
        consumed += len(piece)
        count += 1
    return count


def _numeral_boundaries(doc: DocText, body: list[int], node_number: str) -> list[tuple[int, str]]:
    """Posiciones dentro de `body` donde empieza un numeral del mismo artículo."""
    multi: list[tuple[int, str]] = []
    for position, index in enumerate(body):
        match = MULTI_LEVEL_NUMERAL_RE.match(doc.lines[index][3])
        if not match:
            continue
        numeral = match.group(1)
        if node_number.isdigit() and numeral.split(".")[0] != node_number:
            continue
        multi.append((position, numeral))
    if multi:
        return multi
    single: list[tuple[int, str]] = []
    expected = 1
    for position, index in enumerate(body):
        match = SINGLE_LEVEL_NUMERAL_RE.match(doc.lines[index][3])
        if match and int(match.group(1)) == expected:
            single.append((position, match.group(1)))
            expected += 1
    return single if len(single) >= 2 else []


def _split_by_page(doc: DocText, line_indexes: list[int]) -> list[list[int]]:
    """Respaldo para tramos largos sin numerales: cortes en salto de página, nunca dentro de una página."""
    groups: list[list[int]] = []
    for index in line_indexes:
        if groups and doc.lines[groups[-1][-1]][2] == doc.lines[index][2]:
            groups[-1].append(index)
        else:
            groups.append([index])
    packed: list[list[int]] = []
    for group in groups:
        if packed and _size(doc, packed[-1]) + _size(doc, group) <= SPLIT_THRESHOLD_CHARS:
            packed[-1].extend(group)
        else:
            packed.append(list(group))
    return packed


def _pack(doc: DocText, line_indexes: list[int], heading_count: int, node_number: str) -> list[tuple[list[int], list[str], bool]]:
    """Divide un fragmento largo por numerales y empaqueta numerales consecutivos hasta el tamaño objetivo.

    Devuelve (líneas, numerales, es_continuación_por_página).
    """
    if _size(doc, line_indexes) <= SPLIT_THRESHOLD_CHARS:
        return [(line_indexes, [], False)]
    body = line_indexes[heading_count:]
    boundaries = _numeral_boundaries(doc, body, node_number)
    packed: list[tuple[list[int], list[str]]] = []
    if boundaries:
        intro = body[: boundaries[0][0]]
        pieces: list[tuple[list[int], list[str]]] = []
        for number, (position, numeral) in enumerate(boundaries):
            stop = boundaries[number + 1][0] if number + 1 < len(boundaries) else len(body)
            pieces.append((body[position:stop], [numeral]))
        head = line_indexes[:heading_count] + intro
        if any(_has_text(doc.lines[index][3]) for index in intro):
            pieces.insert(0, (head, []))
        else:
            pieces[0] = (head + pieces[0][0], pieces[0][1])  # el encabezado solo no es un fragmento
        for lines, numerals in pieces:
            if packed and _size(doc, packed[-1][0]) + _size(doc, lines) <= TARGET_CHUNK_CHARS:
                packed[-1] = (packed[-1][0] + lines, packed[-1][1] + numerals)
            else:
                packed.append((list(lines), list(numerals)))
    else:
        packed = [(line_indexes, [])]
    result: list[tuple[list[int], list[str], bool]] = []
    for lines, numerals in packed:
        if _size(doc, lines) > LONG_UNSPLIT_CHARS:
            result.extend((part, numerals, position > 0) for position, part in enumerate(_split_by_page(doc, lines)))
        else:
            result.append((lines, numerals, False))
    return result


def _locator(node: dict[str, Any] | None, nodes_by_id: dict[str, dict[str, Any]]) -> str:
    if node is None:
        return "preámbulo"
    node_type, number = node["node_type"], node["number"] or ""
    parent = nodes_by_id.get(node["parent_id"])
    if node_type == "article":
        return f"art. {number}"
    if node_type in {"numeral", "numbered_section"}:
        if parent and parent["node_type"] == "standard_section":
            return f"{parent['number']}{number}"
        return f"num. {number}"
    if node_type == "standard_section":
        return number
    if node_type == "recommendation":
        return f"Recomendación {number}"
    if node_type == "interpretive_note":
        return f"Nota interpretativa a la Recomendación {number}"
    if node_type == "principle":
        return f"Principio {number}"
    if node_type == "title" and number:
        return f"tít. {number}"
    if node_type == "chapter" and number:
        return f"cap. {number}"
    if node_type == "subchapter" and number:
        return f"subcap. {number}"
    return _short(node["title"], 60)


def _parent_path(node: dict[str, Any] | None, nodes_by_id: dict[str, dict[str, Any]]) -> list[str]:
    path: list[str] = []
    current = node
    while current is not None:
        path.append(_short(current["title"]))
        current = nodes_by_id.get(current["parent_id"])
    return list(reversed(path))


def _pages_label(start: int, end: int) -> str:
    return f"p. {start}" if start == end else f"pp. {start}-{end}"


def _norm_metadata(meta: SourceMeta, item: dict[str, Any], source_path: str) -> dict[str, Any]:
    vigencia = item.get("vigencia") or ""
    lowered = vigencia.lower()
    repealed = meta.binding in {"repealed", "historical"} or "derogada" in lowered
    valid_from = re.search(r"(?:vigente|vigor)\D*desde\s+" + DATE_RE, lowered)
    valid_to = re.search(r"derogad[ao]\s+desde\s+" + DATE_RE, lowered)
    return {
        "norm_id": meta.norm_id,
        "norm_short": NORM_SHORT.get(meta.norm_id, meta.norm_id),
        "title": item["titulo"],
        "issuer": meta.issuer,
        "jurisdiction": meta.jurisdiction,
        "norm_kind": meta.kind,
        "status": "repealed" if repealed else "in_force",
        "published": None,
        "valid_from": valid_from.group(1) if valid_from else None,
        "valid_to": valid_to.group(1) if valid_to else None,
        "source_url": item.get("url_descarga") or item.get("url_validada") or None,
        "source_path": source_path,
        "source_sha256": item.get("sha256") or None,
    }


def _chunks_for_norm(
    meta: SourceMeta,
    item: dict[str, Any],
    source_path: str,
    document: fitz.Document,
    nodes: list[dict[str, Any]],
    amending_norms: set[str],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    pages = _extract_pages(document, meta)
    doc = _build_doc_text(pages)
    _mark_furniture(doc)
    if any(node["method"] == "regex" for node in nodes):
        index_pages = _detect_index_pages(pages)
        doc.index_lines = {index for index, line in enumerate(doc.lines) if line[2] in index_pages}

    nodes_by_id = {node["node_id"]: node for node in nodes}
    anchors = _anchors(doc, nodes)
    base = _norm_metadata(meta, item, source_path)

    segments: list[tuple[Anchor, list[int], int]] = []
    has_body: dict[str, bool] = {}
    for position, anchor in enumerate(anchors):
        end = anchors[position + 1].start if position + 1 < len(anchors) else len(doc.text)
        line_indexes = _segment_lines(doc, anchor.start, end)
        if anchor.node is not None and anchor.node["node_id"] in has_body:
            continue
        heading_count = 0
        if line_indexes and anchor.node is not None and anchor.anchored:
            heading_count = _heading_line_count(doc, line_indexes, anchor.node)
        body = any(_has_text(doc.lines[index][3]) for index in line_indexes[heading_count:])
        if anchor.node is not None:
            has_body[anchor.node["node_id"]] = body
        segments.append((anchor, line_indexes, heading_count))

    children: dict[str, list[str]] = defaultdict(list)
    for node in nodes:
        children[node["parent_id"]].append(node["node_id"])

    def descendant_has_body(node_id: str) -> bool:
        return any(has_body.get(child) or descendant_has_body(child) for child in children.get(node_id, []))

    rows: list[dict[str, Any]] = []
    stats = Counter()
    for anchor, line_indexes, heading_count in segments:
        node = anchor.node
        if not line_indexes:
            stats["empty_segments"] += 1
            continue
        reasons: list[str] = []
        body = any(_has_text(doc.lines[index][3]) for index in line_indexes[heading_count:])
        if node is None:
            reasons.append("preamble_unstructured")
        elif not body:
            if descendant_has_body(node["node_id"]):
                continue
            if node["node_type"] not in CONTENT_NODE_TYPES:
                stats["empty_headings"] += 1
                continue
            reasons.append("heading_only")
            if node["node_type"] == "article":
                stats["articles_without_text"] += 1
        if node is not None and not anchor.anchored:
            reasons.append("heading_not_anchored")
        first_line = doc.lines[line_indexes[0]][3]
        if node is not None and anchor.anchored and (first_line[:1].islower() or REFERENCE_LIKE_HEADING_RE.match(first_line)):
            reasons.append("heading_looks_like_reference")
        if node is not None and node["node_type"] == "article" and "-occ" in node["node_id"]:
            reasons.append("repeated_article_number")
        if node is not None and float(node["confidence"]) < 0.9:
            reasons.append("heuristic_heading")
        if meta.norm_id in amending_norms and node is not None:
            reasons.append("amending_norm_may_quote_target_text")

        number = (node["number"] or "") if node else ""
        packed = _pack(doc, line_indexes, max(heading_count, 1), number)
        locator = _locator(node, nodes_by_id)
        path = _parent_path(node, nodes_by_id)
        confidence = float(node["confidence"]) if node else 0.5
        if not anchor.anchored:
            confidence = min(confidence, 0.6)
        split_kinds = ("+numeral_split" if any(numerals for _lines, numerals, _cont in packed) else "") + (
            "+page_split" if any(continuation for *_rest, continuation in packed) else ""
        )
        for piece_lines, numerals, continuation in packed:
            text = "\n".join(doc.lines[index][3] for index in piece_lines).strip()
            if not text:
                continue
            piece_reasons = list(reasons)
            if len(text) > LONG_UNSPLIT_CHARS:
                piece_reasons.append("long_unsplit")
            page_start = doc.lines[piece_lines[0]][2]
            page_end = doc.lines[piece_lines[-1]][2]
            numeral_label = ""
            if numerals:
                numeral_label = numerals[0] if len(numerals) == 1 else f"{numerals[0]}-{numerals[-1]}"
            article_id = node["node_id"] if node else f"{meta.norm_id}#preamble"
            chunk_locator = f"{locator}, num. {numeral_label}" if numeral_label else locator
            chunk_locator += " (cont.)" if continuation else ""
            chunk_path = path + ([f"num. {numeral_label}"] if numeral_label else [])
            method = anchor.method + split_kinds
            rows.append({
                "chunk_id": "c_" + hashlib.sha1(
                    f"{meta.norm_id}|{article_id}|{page_start}|{text}".encode("utf-8")
                ).hexdigest()[:16],
                **base,
                "article_id": article_id,
                "article_no": number or None,
                "node_type": node["node_type"] if node else "preamble",
                "parent_path": " > ".join(chunk_path) if chunk_path else base["norm_short"],
                "page_start": page_start,
                "page_end": page_end,
                "text": text,
                "citation": f"{base['norm_short']}, {chunk_locator}, {_pages_label(page_start, page_end)}",
                "extraction_method": method,
                "confidence": round(confidence, 3),
                "review_required": bool(piece_reasons),
                "review_reason": ";".join(piece_reasons) or None,
            })

    content_lines = [index for index in range(len(doc.lines)) if index not in doc.furniture and index not in doc.index_lines]
    content_chars = sum(len(doc.lines[index][3]) for index in content_lines)
    chunk_chars = sum(len(row["text"].replace("\n", "")) for row in rows)
    stats.update({
        "pages_processed": len(pages),
        "page_count": len(document),
        "furniture_lines_removed": len(doc.furniture),
        "index_lines_removed": len(doc.index_lines - doc.furniture),
        "headings_unanchored": sum(1 for anchor in anchors if anchor.node is not None and not anchor.anchored),
        "chars_covered_pct": round(100 * chunk_chars / max(1, content_chars), 2),
    })
    return rows, dict(stats)


def _validate(rows: list[dict[str, Any]], page_counts: dict[str, int], file_hashes: dict[str, str]) -> dict[str, dict[str, Any]]:
    ids = Counter(row["chunk_id"] for row in rows)
    fragments = Counter((row["norm_id"], row["article_id"], row["text"]) for row in rows)
    invalid_pages = [
        row["chunk_id"] for row in rows
        if row["page_start"] is None or row["page_end"] is None
        or not 1 <= row["page_start"] <= row["page_end"] <= page_counts.get(row["norm_id"], 0)
    ]
    hash_mismatch = sorted({
        row["norm_id"] for row in rows
        if row["source_sha256"] and file_hashes.get(row["norm_id"]) != row["source_sha256"]
    })

    def result(failures: list[Any]) -> dict[str, Any]:
        return {"passed": not failures, "failures": len(failures), "examples": failures[:5]}

    return {
        "chunk_id_unique": result([key for key, count in ids.items() if count > 1]),
        "norm_id_not_null": result([row["chunk_id"] for row in rows if not row["norm_id"]]),
        "text_not_empty": result([row["chunk_id"] for row in rows if not (row["text"] or "").strip()]),
        "page_start_le_page_end": result(invalid_pages),
        "source_sha256_present": result([row["chunk_id"] for row in rows if not row["source_sha256"]]),
        "source_sha256_matches_file": result(hash_mismatch),
        "citation_present": result([row["chunk_id"] for row in rows if not row["citation"]]),
        "no_duplicate_fragments": result([f"{article}: {text[:60]}" for (_norm, article, text), count in fragments.items() if count > 1]),
        "source_and_page_preserved": result([
            row["chunk_id"] for row in rows if not row["source_path"] or not row["source_url"] or row["page_start"] is None
        ]),
    }


def _csv_text(rows: list[dict[str, Any]]) -> str:
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=list(CHUNK_COLUMNS), quoting=csv.QUOTE_ALL, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({
            key: ("true" if value else "false") if isinstance(value, bool) else ("" if value is None else value)
            for key, value in row.items()
        })
    return buffer.getvalue()


def _csv_roundtrip_ok(rows: list[dict[str, Any]], content: str) -> dict[str, Any]:
    parsed = list(csv.DictReader(io.StringIO(content, newline="")))
    mismatches = [
        row["chunk_id"] for row, back in zip(rows, parsed)
        if back["chunk_id"] != row["chunk_id"] or back["text"] != row["text"] or back["citation"] != row["citation"]
    ]
    if len(parsed) != len(rows):
        mismatches.append(f"rows {len(parsed)} != {len(rows)}")
    return {"passed": not mismatches, "failures": len(mismatches), "examples": mismatches[:5]}


def build_corpus_chunks(source_root: Path, graph_root: Path, output_root: Path) -> dict[str, Any]:
    source_root = source_root.resolve()
    graph_root = graph_root.resolve()
    hierarchy = pq.read_table(graph_root / "hierarchy_nodes.parquet").to_pylist()
    validated = pq.read_table(graph_root / "validated_relation_edges.parquet").to_pylist()
    with (graph_root / "extraction_report.csv").open(encoding="utf-8-sig", newline="") as handle:
        gates = {int(row["source_id"]): row for row in csv.DictReader(handle)}
    amending_norms = {edge["source_id"] for edge in validated if edge["edge_type"] in {"MODIFIES", "ADDS"}}

    nodes_by_norm: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for node in hierarchy:
        nodes_by_norm[node["norm_id"]].append(node)

    rows: list[dict[str, Any]] = []
    report: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    page_counts: dict[str, int] = {}
    file_hashes: dict[str, str] = {}

    for item in _read_manifest(source_root):
        source_id = int(item["id"])
        source_path = item["archivo"].replace("\\", "/")
        meta = SOURCE_META.get(source_id)
        gate_row = gates.get(source_id)
        if meta is None or gate_row is None or gate_row["gate"] != "PASS":
            reason = "fuera_del_catalogo_normativo" if meta is None else (gate_row or {}).get("gate", "sin_reporte_de_ingesta")
            excluded.append({"source_id": source_id, "norm_id": meta.norm_id if meta else "", "title": item["titulo"], "reason": reason})
            report.append({
                "source_id": source_id, "norm_id": meta.norm_id if meta else "", "norm_short": NORM_SHORT.get(meta.norm_id, "") if meta else "",
                "gate": reason, "included": False, "source_path": source_path, "hash_present": bool(item.get("sha256")),
                "hash_matches_file": None, "notes": item.get("observacion", ""),
            })
            continue

        artifact = source_root / item["archivo"]
        file_hashes[meta.norm_id] = _sha256(artifact)
        repo_relative = f"{source_root.name}/{source_path}"
        with fitz.open(artifact) as document:
            page_counts[meta.norm_id] = len(document)
            norm_rows, stats = _chunks_for_norm(meta, item, repo_relative, document, nodes_by_norm[meta.norm_id], amending_norms)
        rows.extend(norm_rows)
        report.append({
            "source_id": source_id, "norm_id": meta.norm_id, "norm_short": NORM_SHORT[meta.norm_id], "gate": "PASS",
            "included": True, "source_path": repo_relative, "hierarchy_nodes": len(nodes_by_norm[meta.norm_id]),
            "chunks": len(norm_rows), "review_required": sum(row["review_required"] for row in norm_rows),
            **stats,
            "hash_present": bool(item.get("sha256")), "hash_matches_file": file_hashes[meta.norm_id] == item.get("sha256"),
            "notes": "",
        })

    validations = _validate(rows, page_counts, file_hashes)
    csv_content = _csv_text(rows)
    validations["csv_roundtrip"] = _csv_roundtrip_ok(rows, csv_content)
    failed = [name for name, outcome in validations.items() if not outcome["passed"]]
    if failed:
        raise ValueError(f"Validaciones fallidas, no se escriben archivos: {json.dumps({name: validations[name] for name in failed}, ensure_ascii=False)}")

    ids = Counter(row["chunk_id"] for row in rows)
    fragments = Counter((row["norm_id"], row["article_id"], row["text"]) for row in rows)
    # Texto legal repetido en artículos distintos (p. ej. Res. 789-2018 arts. 43 y 44) no es duplicado de extracción.
    identical_across_articles = sum(count - 1 for count in Counter(row["text"] for row in rows).values() if count > 1)
    for entry in report:
        if not entry["included"]:
            continue
        norm_rows = [row for row in rows if row["norm_id"] == entry["norm_id"]]
        entry["duplicate_fragments"] = sum(fragments[(row["norm_id"], row["article_id"], row["text"])] > 1 for row in norm_rows)
        entry["duplicate_ids"] = sum(ids[row["chunk_id"]] > 1 for row in norm_rows)
        entry["invalid_page_ranges"] = len(validations["page_start_le_page_end"]["examples"])  # 0 si pasó
        entry["review_reasons"] = json.dumps(
            Counter(reason for row in norm_rows for reason in (row["review_reason"] or "").split(";") if reason),
            ensure_ascii=False, sort_keys=True,
        )

    included = [entry for entry in report if entry["included"]]
    totals = {
        "source_records_in_manifest": len(report),
        "sources_processed": len(included),
        "documents_excluded": len(excluded),
        "total_chunks": len(rows),
        "pages_processed": sum(entry["pages_processed"] for entry in included),
        "articles_without_text": sum(entry.get("articles_without_text", 0) for entry in included),
        "review_required_chunks": sum(row["review_required"] for row in rows),
        "duplicate_fragments": sum(count - 1 for count in fragments.values() if count > 1),
        "identical_text_across_articles": identical_across_articles,
        "invalid_page_ranges": validations["page_start_le_page_end"]["failures"],
        "duplicate_ids": sum(count - 1 for count in ids.values() if count > 1),
        "missing_hashes": sum(1 for row in rows if not row["source_sha256"]),
        "hash_mismatches": validations["source_sha256_matches_file"]["failures"],
        "chunks_by_norm": {entry["norm_id"]: entry["chunks"] for entry in included},
        "chunks_by_node_type": dict(sorted(Counter(row["node_type"] for row in rows).items())),
    }

    output_root.mkdir(parents=True, exist_ok=True)
    table = pa.Table.from_pylist(rows, schema=CHUNK_SCHEMA)
    pq.write_table(table, output_root / "corpus_chunks.parquet", compression="zstd")
    (output_root / "corpus_chunks.csv").write_text(csv_content, encoding="utf-8-sig", newline="")
    written_schema = pq.read_schema(output_root / "corpus_chunks.parquet")
    validations["parquet_schema_types"] = {
        "passed": written_schema.remove_metadata().equals(CHUNK_SCHEMA), "failures": 0, "examples": [],
    }

    report_columns = [
        "source_id", "norm_id", "norm_short", "gate", "included", "source_path", "hierarchy_nodes", "pages_processed",
        "page_count", "chunks", "review_required", "articles_without_text", "empty_headings", "headings_unanchored",
        "furniture_lines_removed", "index_lines_removed", "chars_covered_pct", "duplicate_fragments", "duplicate_ids",
        "invalid_page_ranges", "hash_present", "hash_matches_file", "review_reasons", "notes",
    ]
    total_row = {
        "source_id": "", "norm_id": "__TOTAL__", "norm_short": "", "gate": "", "included": len(included),
        "source_path": "", "hierarchy_nodes": sum(entry.get("hierarchy_nodes", 0) for entry in included),
        "pages_processed": totals["pages_processed"], "page_count": "", "chunks": totals["total_chunks"],
        "review_required": totals["review_required_chunks"], "articles_without_text": totals["articles_without_text"],
        "empty_headings": sum(entry.get("empty_headings", 0) for entry in included),
        "headings_unanchored": sum(entry.get("headings_unanchored", 0) for entry in included),
        "furniture_lines_removed": sum(entry.get("furniture_lines_removed", 0) for entry in included),
        "index_lines_removed": sum(entry.get("index_lines_removed", 0) for entry in included),
        "chars_covered_pct": "", "duplicate_fragments": totals["duplicate_fragments"],
        "duplicate_ids": totals["duplicate_ids"], "invalid_page_ranges": totals["invalid_page_ranges"],
        "hash_present": totals["missing_hashes"] == 0, "hash_matches_file": totals["hash_mismatches"] == 0,
        "review_reasons": "", "notes": f"excluidos: {len(excluded)}",
    }
    with (output_root / "quality_report.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=report_columns, quoting=csv.QUOTE_ALL, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        for entry in report + [total_row]:
            writer.writerow({key: entry.get(key, "") for key in report_columns})

    manifest = {
        "corpus_version": CORPUS_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "inputs": {
            "source_manifest": str(source_root / "manifest.json"),
            "graph_ingest": str(graph_root),
            "hierarchy_nodes_sha256": _sha256(graph_root / "hierarchy_nodes.parquet"),
        },
        "outputs": ["corpus_chunks.parquet", "corpus_chunks.csv", "quality_report.csv", "manifest.json"],
        "columns": list(CHUNK_COLUMNS),
        "chunking": {
            "unit": "article/section/numeral; never mixes nodes",
            "split_threshold_chars": SPLIT_THRESHOLD_CHARS,
            "target_chunk_chars": TARGET_CHUNK_CHARS,
            "long_unsplit_chars": LONG_UNSPLIT_CHARS,
            "chunk_id": "c_ + sha1(norm_id|article_id|page_start|text)[:16]",
            "text": "literal PyMuPDF lines (whitespace collapsed) without repeated headers/footers and index pages",
        },
        "counts": totals,
        "excluded": excluded,
        "validations": validations,
        "policy": {"transformer_used": False, "embeddings": False, "ocr_content_included": False},
    }
    (output_root / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest
