"""Chunks: unidad = articulo; tope relativo al corpus (percentil 95); sin solape ni reescritura.

Cada chunk es un rango [start, end) sobre el texto de su unidad (articulo, seccion, disposicion, anexo o parrafo)
y cumple text == unit_text[start:end]. Los rangos de una unidad la cubren entera y sin huecos. Las filas salen con
el esquema fijado por el dueño (schema.CHUNKS, docs/03-chunking.md):

  chunk_id          = "c_" + sha1(f"{norm_id}:{article_id}:{page_start}:{index}")[:16]
  node_type         = article | section | paragraph | annex | provision (del parser)
  parent_path       = TITULO II > CAPITULO I > Articulo 12 (> numeral si el chunk empieza en uno)
  extraction_method = regex (PDF/txt) | markdown (.md)
  confidence        = 1.0; 0.6 si el parser cayo a parrafos; review_required = confidence < 0.8
  citation          = "{norm_short}, art. {article_no}, p. {page_start}" (sec./disp./anexo/parr. segun el tipo)
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections import defaultdict

import numpy as np
import pyarrow as pa

from regulabank.corpus.norms import Norm
from regulabank.corpus.parse import Cut, Unit
from regulabank.shared import schema

CAP_PERCENTILE = 95.0
MIN_PIECE_RATIO = 0.5
CONFIDENCE_PARSED = 1.0
CONFIDENCE_FALLBACK = 0.6
REVIEW_BELOW = 0.8
CITATION_LABEL = {"article": "art.", "section": "sec.", "provision": "disp.", "annex": "anexo", "paragraph": "párr."}
EXTRACTION_BY_SUFFIX = {".md": "markdown", ".markdown": "markdown"}
RX_SENTENCE_END = re.compile(r"[.;:][\"”)]?\s+")


def cap_from_lengths(lengths: list[int], percentile: float = CAP_PERCENTILE) -> int:
    """Tope de largo = percentil del largo de las unidades del corpus cargado (nunca un numero fijo)."""
    if not lengths:
        raise ValueError("no hay unidades para calcular el tope")
    return int(math.ceil(float(np.percentile(lengths, percentile))))


def cut_candidates(text: str, cuts: list[Cut]) -> list[int]:
    """Posiciones donde empieza un numeral, literal, item o una oracion nueva (0 < p < len)."""
    cands = {c.offset for c in cuts}
    for m in RX_SENTENCE_END.finditer(text):
        cands.add(m.end())
    return sorted(p for p in cands if 0 < p < len(text))


def split_ranges(
    length: int, cap: int, candidates: list[int], min_ratio: float = MIN_PIECE_RATIO
) -> tuple[list[tuple[int, int]], int]:
    """ceil(len/cap) piezas parejas cortando en el candidato mas cercano al objetivo.

    Ninguna pieza baja de min_ratio x objetivo. Si no hay candidato en la ventana se corta en seco en el
    objetivo (se cuenta como hard cut para medirlo). Devuelve (rangos, hard_cuts).
    """
    n = max(1, math.ceil(length / cap)) if cap > 0 else 1
    if n == 1:
        return [(0, length)], 0
    target = length / n
    ranges: list[tuple[int, int]] = []
    start = 0
    hard = 0
    for k in range(1, n):
        ideal = k * target
        lo = start + min_ratio * target
        hi = length - min_ratio * target * (n - k)
        window = [p for p in candidates if p > start and lo <= p <= hi]
        if window:
            cut = min(window, key=lambda p: (abs(p - ideal), p))
        else:
            cut = int(round(min(max(ideal, lo), hi)))
            hard += 1
        ranges.append((start, cut))
        start = cut
    ranges.append((start, length))
    return ranges, hard


def chunk_id(norm_id: str, article_id: str, page_start: int, index: int) -> str:
    return "c_" + hashlib.sha1(f"{norm_id}:{article_id}:{page_start}:{index}".encode("utf-8")).hexdigest()[:16]


def citation(norm_short: str, node_type: str, article_no: str, page_start: int) -> str:
    return f"{norm_short}, {CITATION_LABEL[node_type]} {article_no}, p. {page_start}"


def extraction_method(suffix: str) -> str:
    return EXTRACTION_BY_SUFFIX.get(suffix.lower(), "regex")


def build_chunks(
    norm: Norm, units: list[Unit], cap: int, page_offsets: list[int], suffix: str, fallback: bool = False
) -> tuple[list[dict], int]:
    """Filas con el esquema CHUNKS para una norma. Devuelve (filas, hard_cuts)."""
    from regulabank.corpus.extract import page_of

    confidence = CONFIDENCE_FALLBACK if fallback else CONFIDENCE_PARSED
    method = extraction_method(suffix)
    rows: list[dict] = []
    hard_total = 0
    for unit in units:
        article_id = f"{norm.norm_id}#{unit.id_suffix}"
        ranges, hard = split_ranges(len(unit.text), cap, cut_candidates(unit.text, unit.cuts))
        hard_total += hard
        label_at = {c.offset: c.label for c in unit.cuts if c.kind == "numeral"}
        for i, (s, e) in enumerate(ranges):
            parent_path = unit.path + (f" > {label_at[s]}" if s in label_at else "")
            p_start = page_of(page_offsets, unit.start + s)
            p_end = page_of(page_offsets, unit.start + e - 1)
            rows.append(
                {
                    "chunk_id": chunk_id(norm.norm_id, article_id, p_start, i),
                    "norm_id": norm.norm_id,
                    "norm_short": norm.short,
                    "title": norm.title,
                    "issuer": norm.issuer,
                    "jurisdiction": norm.jurisdiction,
                    "norm_kind": norm.kind,
                    "status": norm.status,
                    "published": norm.published,
                    "valid_from": norm.valid_from,
                    "valid_to": norm.valid_to,
                    "source_url": norm.source_url,
                    "source_path": norm.source_path,
                    "source_sha256": norm.source_sha256,
                    "article_id": article_id,
                    "article_no": unit.no,
                    "node_type": unit.node_type,
                    "parent_path": parent_path,
                    "page_start": p_start,
                    "page_end": p_end,
                    "text": unit.text[s:e],
                    "citation": citation(norm.short, unit.node_type, unit.no, p_start),
                    "extraction_method": method,
                    "confidence": confidence,
                    "review_required": confidence < REVIEW_BELOW,
                }
            )
    return rows, hard_total


def validate(rows: list[dict], unit_texts: dict[str, str]) -> None:
    """Falla (ValueError) y no se escribe nada si el gold no es reproducible (docs/03-chunking.md).

    Invariantes: chunk_id unico; norm_id, article_id y published presentes; node_type y extraction_method del
    contrato; el texto es literal de la unidad (`unit_texts[article_id]`), los chunks de una unidad la cubren entera,
    en orden y sin huecos ni solapes; review_required coincide con la confianza.
    """
    problems: list[str] = []
    seen: set[str] = set()
    by_article: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        if r["chunk_id"] in seen:
            problems.append(f"chunk_id duplicado {r['chunk_id']}")
        seen.add(r["chunk_id"])
        for col in ("norm_id", "article_id", "published", "norm_short", "citation"):
            if not r.get(col):
                problems.append(f"{r.get('chunk_id')}: sin {col}")
        if r.get("node_type") not in schema.NODE_TYPES:
            problems.append(f"{r['chunk_id']}: node_type {r.get('node_type')!r}")
        if r.get("extraction_method") not in schema.EXTRACTION_METHODS:
            problems.append(f"{r['chunk_id']}: extraction_method {r.get('extraction_method')!r}")
        if bool(r.get("review_required")) != (float(r.get("confidence", 0.0)) < REVIEW_BELOW):
            problems.append(f"{r['chunk_id']}: review_required no coincide con confidence")
        if not r.get("text") or not r["text"].strip():
            problems.append(f"{r['chunk_id']}: chunk vacio")
        if r.get("page_start", 0) < 1 or r.get("page_end", 0) < r.get("page_start", 0):
            problems.append(f"{r['chunk_id']}: paginas {r.get('page_start')}-{r.get('page_end')}")
        by_article[r["article_id"]].append(r)
    for article_id, group in by_article.items():
        text = unit_texts.get(article_id)
        if text is None:
            problems.append(f"{article_id}: unidad sin texto")
            continue
        joined = "".join(r["text"] for r in group)
        if joined != text:
            problems.append(f"{article_id}: la union de sus chunks no reproduce el texto de la unidad")
            continue
        pos = 0
        for r in group:
            if text[pos:pos + len(r["text"])] != r["text"]:
                problems.append(f"{r['chunk_id']}: text no es literal de la unidad en [{pos}:{pos + len(r['text'])}]")
            pos += len(r["text"])
    if problems:
        head = "\n  ".join(problems[:20])
        raise ValueError(f"gold invalido ({len(problems)} problemas), no se escribe nada:\n  {head}")


def fingerprint(rows: list[dict]) -> str:
    """sha256 de los hashes de fila ordenados: independiente del orden de escritura."""
    hashes = sorted(
        hashlib.sha256(json.dumps(r, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")).hexdigest()
        for r in rows
    )
    return hashlib.sha256("\n".join(hashes).encode("ascii")).hexdigest()


def to_table(rows: list[dict]) -> pa.Table:
    return pa.Table.from_pylist(rows, schema=schema.CHUNKS)
