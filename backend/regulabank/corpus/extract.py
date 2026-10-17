"""Silver: texto por pagina. PDF con pymupdf; Markdown y txt son una sola pagina.

El texto extraido nunca se modifica despues: todos los offsets del gold se calculan sobre el, y el texto del
documento es la union de las paginas con un salto de linea entre pagina y pagina (ver join_pages).
"""

from __future__ import annotations

from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

PAGES = pa.schema([("page", pa.int32()), ("text", pa.string())])
PAGE_SEP = "\n"
TEXT_EXT = {".md", ".txt", ".markdown"}


def extract_pages(path: Path) -> list[str]:
    """Lista de textos, uno por pagina (la primera pagina es la 1 al escribir)."""
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        import pymupdf

        with pymupdf.open(path) as doc:
            return [page.get_text("text") for page in doc]
    if suffix in TEXT_EXT:
        return [path.read_text(encoding="utf-8")]
    raise ValueError(f"{path}: formato no soportado ({suffix}); se aceptan .pdf, .md y .txt")


def extract_to_silver(norm_id: str, source: Path, silver_dir: Path) -> list[str]:
    """Escribe data/silver/<norm_id>/pages.parquet y devuelve las paginas."""
    pages = extract_pages(source)
    out = silver_dir / norm_id
    out.mkdir(parents=True, exist_ok=True)
    table = pa.Table.from_pylist(
        [{"page": i, "text": t} for i, t in enumerate(pages, start=1)], schema=PAGES
    )
    pq.write_table(table, out / "pages.parquet")
    return pages


def read_pages(norm_id: str, silver_dir: Path) -> list[str]:
    table = pq.read_table(silver_dir / norm_id / "pages.parquet")
    rows = sorted(table.to_pylist(), key=lambda r: r["page"])
    return [r["text"] for r in rows]


def join_pages(pages: list[str]) -> tuple[str, list[int]]:
    """Texto del documento y offset inicial de cada pagina (indice 0 = pagina 1)."""
    offsets: list[int] = []
    pos = 0
    for i, t in enumerate(pages):
        offsets.append(pos)
        pos += len(t) + (len(PAGE_SEP) if i < len(pages) - 1 else 0)
    return PAGE_SEP.join(pages), offsets


def page_of(offsets: list[int], pos: int) -> int:
    """Numero de pagina (desde 1) del caracter en pos."""
    lo, hi = 0, len(offsets) - 1
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if offsets[mid] <= pos:
            lo = mid
        else:
            hi = mid - 1
    return lo + 1
