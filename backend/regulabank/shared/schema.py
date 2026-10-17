"""Contrato de datos del gold: esquemas PyArrow de los Parquet que comparten corpus, graphs y search.

Toda etapa escribe y lee estos esquemas; cambiarlos es cambiar el contrato (test + commit). Nombres en ingles,
valores en ingles (docs/03-chunking.md, docs/04-entities.md, docs/06-graphs.md).
"""

from __future__ import annotations

import pyarrow as pa

NORM_KINDS = ("law", "legislative_decree", "sbs_resolution", "sbs_circular", "bcrp_circular", "standard", "internal_policy")
NORM_STATUS = ("in_force", "partial", "repealed", "scheduled")
CHANGE_KINDS = ("original", "modified", "replaced", "repealed", "added")

# Una fila por documento normativo. Se carga desde seeds/norms.csv (a mano) y se completa con lo detectado.
NORMS = pa.schema([
    ("norm_id", pa.string()),          # pe-sbs-res-11356-2008
    ("short", pa.string()),            # Res. SBS 11356-2008
    ("title", pa.string()),
    ("kind", pa.string()),             # NORM_KINDS
    ("issuer", pa.string()),           # SBS, BCRP, Congreso, UIF, BCBS, Banco (sintetico)
    ("published", pa.string()),        # ISO date
    ("valid_from", pa.string()),       # ISO date
    ("valid_to", pa.string()),         # ISO date o null
    ("status", pa.string()),           # NORM_STATUS
    ("topics", pa.list_(pa.string())),
    ("source_url", pa.string()),
    ("source_path", pa.string()),      # ruta local del PDF/MD en bronze
    ("source_sha256", pa.string()),
    ("synthetic", pa.bool_()),
])

# Una fila por chunk (esquema fijado por el dueño el 2026-10-17). text es literal del original; sin solape.
NODE_TYPES = ("article", "section", "paragraph", "annex", "provision")
EXTRACTION_METHODS = ("regex", "markdown", "ocr", "manual")

CHUNKS = pa.schema([
    ("chunk_id", pa.string()),            # c_ + sha1(norm_id:article_id:page_start:start)[:16]
    ("norm_id", pa.string()),
    ("norm_short", pa.string()),
    ("title", pa.string()),               # titulo de la norma
    ("issuer", pa.string()),
    ("jurisdiction", pa.string()),        # PE
    ("norm_kind", pa.string()),           # NORM_KINDS
    ("status", pa.string()),              # NORM_STATUS
    ("published", pa.string()),           # ISO date
    ("valid_from", pa.string()),
    ("valid_to", pa.string()),            # null = vigente
    ("source_url", pa.string()),
    ("source_path", pa.string()),
    ("source_sha256", pa.string()),
    ("article_id", pa.string()),          # {norm_id}#art-12   (politicas: #sec-5.2)
    ("article_no", pa.string()),
    ("node_type", pa.string()),           # NODE_TYPES
    ("parent_path", pa.string()),         # TITULO II > CAPITULO I > Articulo 12
    ("page_start", pa.int32()),
    ("page_end", pa.int32()),
    ("text", pa.string()),
    ("citation", pa.string()),            # Res. SBS N.° 11356-2008, art. 12, p. 4
    ("extraction_method", pa.string()),   # EXTRACTION_METHODS
    ("confidence", pa.float32()),         # 1.0 regex limpio; menor si OCR o parse dudoso
    ("review_required", pa.bool_()),
])

ENTITY_TYPES = (
    "norm_ref", "article_ref", "deadline", "amount", "percentage", "defined_term", "regulator",
    "institution_type", "role", "product", "risk", "obligation", "sanction", "report",
)

# Una fila por mencion (ocurrencia en un chunk). text[start:end] == mention.
MENTIONS = pa.schema([
    ("mention_id", pa.string()),
    ("chunk_id", pa.string()),
    ("entity_id", pa.string()),        # clave canonica: {type}:{key}  (norm_ref:pe-sbs-res-11356-2008)
    ("type", pa.string()),             # ENTITY_TYPES
    ("mention", pa.string()),
    ("start", pa.int32()),
    ("end", pa.int32()),
    ("score", pa.float32()),
    ("method", pa.string()),           # regex | gliner2 | gazetteer
    ("value", pa.string()),            # JSON con el valor estructurado ({"n":15,"unit":"business_day"}) o null
])

# Una fila por entidad canonica.
ENTITIES = pa.schema([
    ("entity_id", pa.string()),
    ("type", pa.string()),
    ("name", pa.string()),
    ("key", pa.string()),
    ("catalog_id", pa.string()),       # id en seeds/catalog.csv o null
    ("n_chunks", pa.int32()),
    ("n_norms", pa.int32()),
])

EDGE_TYPES = (
    "NEXT", "PARENT", "REFERS_TO", "SHARES_ENTITY", "SIMILAR",   # focus
    "MENTIONS",                                                   # lens
    "MODIFIES", "REPLACES", "REPEALS", "ADDS", "IMPLEMENTS",      # horizon / bridge
)

# Una fila por arista. src/dst son chunk_id, entity_id, article_id o norm_id segun el tipo.
EDGES = pa.schema([
    ("src", pa.string()),
    ("src_kind", pa.string()),         # chunk | entity | article | norm
    ("dst", pa.string()),
    ("dst_kind", pa.string()),
    ("type", pa.string()),             # EDGE_TYPES
    ("weight", pa.float32()),
    ("method", pa.string()),           # structure | regex | knn | shared_entity | seed
    ("evidence", pa.string()),         # tramo literal o JSON con la razon
])
