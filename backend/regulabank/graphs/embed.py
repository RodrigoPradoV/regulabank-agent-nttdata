"""Embeddings de chunks -> LanceDB (`chunks`: columnas CHUNKS + `vector`, indice FTS en espanol).

Modelo principal `google/embeddinggemma-300m` con prefijos de documento y consulta (docs/07-embeddings.md); si esta
cerrado o no se puede cargar, cae a `intfloat/multilingual-e5-small` y lo deja dicho en el manifiesto.
sentence-transformers/torch se importan de forma perezosa; `FakeEmbedder` (hash, dim 16) sirve para las pruebas.
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Protocol

import numpy as np
import pyarrow as pa

from regulabank.shared import schema

log = logging.getLogger("regulabank.graphs.embed")

# Prefijos por modelo: (plantilla de documento, prefijo de consulta). Sin ellos gemma baja mucho.
PREFIXES: dict[str, tuple[str, str]] = {
    "google/embeddinggemma-300m": ("title: {norm_short}, art. {article_no} | text: ", "task: search result | query: "),
    "intfloat/multilingual-e5-small": ("passage: ", "query: "),
    "intfloat/multilingual-e5-base": ("passage: ", "query: "),
}


class Embedder(Protocol):
    name: str
    dim: int

    def doc_prefix(self, norm_short: str, article_no: str) -> str: ...
    def query_prefix(self) -> str: ...
    def encode(self, texts: list[str]) -> np.ndarray: ...


def _normalize(vectors: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return (vectors / norms).astype(np.float32)


class FakeEmbedder:
    """Vectores deterministas por hash del texto (dim 16). Solo para pruebas: no entiende nada."""

    name = "fake"

    def __init__(self, dim: int = 16):
        self.dim = dim

    def doc_prefix(self, norm_short: str, article_no: str) -> str:
        return ""

    def query_prefix(self) -> str:
        return ""

    def encode(self, texts: list[str]) -> np.ndarray:
        out = np.zeros((len(texts), self.dim), dtype=np.float32)
        for i, text in enumerate(texts):
            seed = int.from_bytes(hashlib.sha256(text.encode("utf-8")).digest()[:8], "little")
            out[i] = np.random.default_rng(seed).standard_normal(self.dim)
        return _normalize(out)


class SentenceTransformerEmbedder:
    """Envoltura de sentence-transformers con los prefijos del modelo; import perezoso."""

    def __init__(self, model_name: str, batch_size: int = 32, device: str | None = None):
        from sentence_transformers import SentenceTransformer  # noqa: PLC0415 - import perezoso a proposito

        self.name = model_name
        self.batch_size = batch_size
        self.model = SentenceTransformer(model_name, device=device)
        self.dim = int(self.model.get_sentence_embedding_dimension())
        self._doc, self._query = PREFIXES.get(model_name, ("", ""))

    def doc_prefix(self, norm_short: str, article_no: str) -> str:
        return self._doc.format(norm_short=norm_short, article_no=article_no)

    def query_prefix(self) -> str:
        return self._query

    def encode(self, texts: list[str]) -> np.ndarray:
        vectors = self.model.encode(texts, batch_size=self.batch_size, normalize_embeddings=True,
                                    convert_to_numpy=True, show_progress_bar=False)
        return _normalize(np.asarray(vectors, dtype=np.float32))


class OpenAIEmbedder:
    """Embeddings por la API de OpenAI (httpx): el servidor no carga torch ni un modelo de 1,2 GB. Sin prefijos."""

    def __init__(self, model_name: str = "openai:text-embedding-3-small", batch_size: int = 256):
        import httpx  # noqa: PLC0415

        from regulabank.shared.secrets import api_key  # noqa: PLC0415

        self.name = model_name
        self.api_model = model_name.split(":", 1)[1]
        self.batch_size = batch_size
        self.http = httpx.Client(base_url="https://api.openai.com/v1", headers={"Authorization": f"Bearer {api_key()}"}, timeout=120)
        self.dim = 1536 if "small" in self.api_model else 3072

    def doc_prefix(self, norm_short: str, article_no: str) -> str:
        return f"{norm_short}, art. {article_no}. " if norm_short else ""

    def query_prefix(self) -> str:
        return ""

    def encode(self, texts: list[str]) -> np.ndarray:
        out: list[list[float]] = []
        for i in range(0, len(texts), self.batch_size):
            batch = [t.replace("\n", " ")[:24000] or " " for t in texts[i:i + self.batch_size]]
            r = self.http.post("/embeddings", json={"model": self.api_model, "input": batch})
            if r.status_code != 200:
                raise RuntimeError(f"OpenAI embeddings {r.status_code}: {r.text[:300]}")
            out.extend(d["embedding"] for d in sorted(r.json()["data"], key=lambda d: d["index"]))
        return _normalize(np.asarray(out, dtype=np.float32))


def load_embedder(model_name: str, fallback: str, batch_size: int = 32, device: str | None = None) -> Embedder:
    """Carga el modelo principal; si falla (gated, sin red, sin pesos), carga el repuesto y lo registra."""
    if model_name.startswith("openai:"):
        return OpenAIEmbedder(model_name)
    try:
        return SentenceTransformerEmbedder(model_name, batch_size, device)
    except ImportError:
        raise
    except Exception as exc:  # noqa: BLE001 - cualquier falla de descarga o carga activa el repuesto
        log.warning("no se pudo cargar %s (%s: %s); usando %s", model_name, type(exc).__name__, exc, fallback)
        return SentenceTransformerEmbedder(fallback, batch_size, device)


def doc_texts(chunks: pa.Table, embedder: Embedder) -> list[str]:
    rows = chunks.select(["norm_short", "article_no", "text"]).to_pylist()
    return [embedder.doc_prefix(r["norm_short"] or "", r["article_no"] or "") + r["text"] for r in rows]


def embed_chunks(chunks: pa.Table, embedder: Embedder) -> np.ndarray:
    """Matriz (n_chunks, dim) float32 normalizada, en el orden de la tabla."""
    return embedder.encode(doc_texts(chunks, embedder))


def embed_query(question: str, embedder: Embedder) -> np.ndarray:
    return embedder.encode([embedder.query_prefix() + question])[0]


# vectors.parquet (lo escribe el pod o el build local): una fila por chunk.
VECTORS = pa.schema([
    ("chunk_id", pa.string()),
    ("model", pa.string()),
    ("dim", pa.int32()),
    ("vector", pa.list_(pa.float32())),
])


def lance_schema(dim: int | None) -> pa.Schema:
    if dim is None:
        return schema.CHUNKS
    return schema.CHUNKS.append(pa.field("vector", pa.list_(pa.float32(), dim)))


def write_lance(lance_dir: Path, chunks: pa.Table, vectors: np.ndarray | None, table_name: str = "chunks"):
    """Reemplaza la tabla `chunks` con CHUNKS (+ vector si hay) y crea el indice FTS en espanol sobre `text`."""
    import lancedb  # noqa: PLC0415 - mantiene el modulo importable sin lancedb cargado
    from lancedb.index import FTS  # noqa: PLC0415

    data = chunks.cast(schema.CHUNKS)
    dim = None
    if vectors is not None:
        if vectors.shape[0] != chunks.num_rows:
            raise ValueError(f"vectores {vectors.shape[0]} != chunks {chunks.num_rows}")
        dim = int(vectors.shape[1])
        vec_col = pa.FixedSizeListArray.from_arrays(pa.array(vectors.astype(np.float32).ravel(), pa.float32()), dim)
        data = data.append_column(pa.field("vector", pa.list_(pa.float32(), dim)), vec_col)
    lance_dir.mkdir(parents=True, exist_ok=True)
    db = lancedb.connect(str(lance_dir))
    table = db.create_table(table_name, data=data, schema=lance_schema(dim), mode="overwrite")
    table.create_index("text", config=FTS(language="Spanish"), replace=True)
    return table


def vectors_table(chunk_ids: list[str], vectors: np.ndarray, model_name: str) -> pa.Table:
    """Tabla VECTORS (chunk_id, model, dim, vector) para `vectors.parquet`."""
    dim = int(vectors.shape[1])
    return pa.Table.from_pydict({
        "chunk_id": pa.array(chunk_ids, pa.string()),
        "model": pa.array([model_name] * len(chunk_ids), pa.string()),
        "dim": pa.array([dim] * len(chunk_ids), pa.int32()),
        "vector": pa.array([row.astype(np.float32).tolist() for row in vectors], pa.list_(pa.float32())),
    }, schema=VECTORS)


def read_vectors(table: pa.Table, chunk_ids: list[str]) -> tuple[np.ndarray, str]:
    """Tabla VECTORS -> (matriz alineada a chunk_ids, nombre del modelo). Falla si falta algun chunk."""
    rows = {r["chunk_id"]: r for r in table.to_pylist()}
    missing = [c for c in chunk_ids if c not in rows]
    if missing:
        raise ValueError(f"vectors.parquet no cubre {len(missing)} chunks (p. ej. {missing[:3]})")
    models = {r["model"] for r in rows.values()}
    if len(models) != 1:
        raise ValueError(f"vectors.parquet mezcla modelos: {sorted(models)}")
    matrix = np.array([rows[c]["vector"] for c in chunk_ids], dtype=np.float32)
    return _normalize(matrix), models.pop()
