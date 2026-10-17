"""Job de GPU (RunPod) sobre chunks.parquet: menciones GLiNER2 y vectores de embedding.

  python backend/pod/job.py --chunks chunks.parquet --out out --preflight      # 2 chunks + el mas largo, proyeccion
  python backend/pod/job.py --chunks chunks.parquet --out out                  # corrida completa, reanudable
  python backend/pod/job.py --chunks chunks.parquet --out out --limit 20 --allow-cpu   # humo en la Mac

Reglas pagadas con horas de pod (memoria del proyecto):
- Aborta en el acto si no hay CUDA, salvo `--allow-cpu` (entonces usa MPS o CPU).
- Cada lote se escribe atomico (archivo temporal + rename) en out/parts/ y la corrida se reanuda saltando los
  chunk_id ya hechos; el lote guarda sus chunk_id en los metadatos del Parquet (un chunk sin menciones tambien cuenta).
- Una linea de avance por lote (chunks/min y proyeccion) para que un vigilante vea avance, no existencia.
- `DONE` solo cuando las dos etapas terminaron y los finales (mentions_gliner2.parquet, vectors.parquet,
  manifest.json) estan escritos. Toda mencion se verifica `text[start:end] == mention` antes de escribir.

Salida (esquemas del contrato): out/mentions_gliner2.parquet (schema.MENTIONS, method=gliner2),
out/vectors.parquet (chunk_id, model, dim, vector list<float32>), out/manifest.json, out/DONE.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import platform
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.compute as pc
import pyarrow.parquet as pq

# El paquete regulabank esta instalado en el pod (uv pip install -e ".[models]"); si no, se toma del repo.
try:
    import regulabank  # noqa: F401
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from regulabank.graphs import gliner2 as gliner2_mod  # noqa: E402
from regulabank.graphs.embed import PREFIXES, VECTORS, vectors_table  # noqa: E402
from regulabank.shared import schema  # noqa: E402

log = logging.getLogger("pod.job")

DEFAULT_GLINER2 = "fastino/gliner2-large-v1"
DEFAULT_EMBED = "google/embeddinggemma-300m"
DEFAULT_FALLBACK = "intfloat/multilingual-e5-small"
THRESHOLD = 0.3
GLINER2_WINDOW_WORDS = 384   # ventana en palabras para batch_extract_entities_long, bajo el tope del modelo
GLINER2_OVERLAP_WORDS = 64
RX_PART = re.compile(r"^(?P<stage>gliner2|embed)\.(?P<n>\d{5})\.parquet$")


# ----------------------------------------------------------------------------------------------------------
# Dispositivo y utilidades
# ----------------------------------------------------------------------------------------------------------


def pick_device(allow_cpu: bool) -> str:
    """cuda o aborta; con --allow-cpu, mps si existe y si no cpu."""
    import torch

    if torch.cuda.is_available():
        return "cuda"
    if not allow_cpu:
        sys.exit("ABORT: torch.cuda.is_available() es False y no se paso --allow-cpu (este job cuesta por hora)")
    if torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def atomic_write(table: pa.Table, path: Path) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    pq.write_table(table, tmp)
    os.replace(tmp, path)


def atomic_text(text: str, path: Path) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def with_chunk_ids(table: pa.Table, chunk_ids: list[str], extra: dict[str, str] | None = None) -> pa.Table:
    meta = {"chunk_ids": json.dumps(chunk_ids)}
    meta.update(extra or {})
    return table.replace_schema_metadata(meta)


def done_chunk_ids(parts_dir: Path, stage: str) -> tuple[set[str], int]:
    """chunk_id ya procesados en out/parts/<stage>.NNNNN.parquet y el siguiente numero de lote libre."""
    done: set[str] = set()
    last = -1
    if not parts_dir.exists():
        return done, 0
    for p in sorted(parts_dir.iterdir()):
        m = RX_PART.match(p.name)
        if not m or m["stage"] != stage:
            continue
        meta = pq.read_schema(p).metadata or {}
        ids = json.loads(meta.get(b"chunk_ids", b"[]"))
        done.update(ids)
        last = max(last, int(m["n"]))
    return done, last + 1


def read_chunks(path: Path) -> pa.Table:
    """Lee chunks.parquet al contrato: las 25 columnas de schema.CHUNKS (columnas extra se ignoran, tipos se
    convierten); aborta con la lista de columnas faltantes."""
    table = pq.read_table(path)
    missing = [n for n in schema.CHUNKS.names if n not in table.schema.names]
    if missing:
        sys.exit(f"ABORT: {path} no cumple schema.CHUNKS; faltan columnas {missing}")
    extra = [n for n in table.schema.names if n not in schema.CHUNKS.names]
    if extra:
        log.info("columnas fuera del contrato ignoradas: %s", extra)
    return table.select(schema.CHUNKS.names).cast(schema.CHUNKS)


def batches(table: pa.Table, size: int):
    for i in range(0, table.num_rows, size):
        yield table.slice(i, size)


class Progress:
    """Linea de avance por lote: hechos/total, chunks/min y tiempo restante proyectado."""

    def __init__(self, stage: str, total: int, already: int):
        self.stage, self.total, self.already = stage, total, already
        self.done_now = 0
        self.t0 = time.perf_counter()

    def step(self, n: int) -> None:
        self.done_now += n
        elapsed = time.perf_counter() - self.t0
        rate = self.done_now / elapsed * 60 if elapsed > 0 else 0.0
        remaining = self.total - self.already - self.done_now
        eta = remaining / rate * 60 if rate > 0 else float("nan")
        print(f"[{self.stage}] {self.already + self.done_now}/{self.total} chunks | {rate:.1f} chunks/min | "
              f"{elapsed:.0f} s | restan ~{eta:.0f} s", flush=True)


# ----------------------------------------------------------------------------------------------------------
# Modelos
# ----------------------------------------------------------------------------------------------------------


def load_gliner2(model_name: str, device: str) -> Any:
    model = gliner2_mod.load_model(model_name)
    try:
        model = model.to(device)
    except Exception as exc:  # noqa: BLE001 - mps/cuda no disponible para este modelo: sigue en cpu
        log.warning("gliner2 no se pudo mover a %s (%s); queda en cpu", device, exc)
    return model


class Embedder:
    """sentence-transformers con prefijo de documento por modelo; repuesto si el principal esta cerrado."""

    def __init__(self, model_name: str, fallback: str, device: str):
        from sentence_transformers import SentenceTransformer

        self.fallback_used = False
        try:
            self.model = SentenceTransformer(model_name, device=device)
            self.name = model_name
        except Exception as exc:  # noqa: BLE001 - gated, sin red o sin pesos: repuesto
            log.warning("no se pudo cargar %s (%s: %s); usando %s", model_name, type(exc).__name__, exc, fallback)
            self.model = SentenceTransformer(fallback, device=device)
            self.name = fallback
            self.fallback_used = True
        self.dim = int(self.model.get_sentence_embedding_dimension())
        self.doc_template = PREFIXES.get(self.name, ("", ""))[0]

    def texts(self, rows: list[dict[str, Any]]) -> list[str]:
        return [self.doc_template.format(norm_short=r["norm_short"] or "", article_no=r["article_no"] or "")
                + r["text"] for r in rows]

    def encode(self, rows: list[dict[str, Any]], batch_size: int) -> np.ndarray:
        vectors = self.model.encode(self.texts(rows), batch_size=batch_size, normalize_embeddings=True,
                                    convert_to_numpy=True, show_progress_bar=False)
        return np.asarray(vectors, dtype=np.float32)


# ----------------------------------------------------------------------------------------------------------
# Etapas
# ----------------------------------------------------------------------------------------------------------


def run_gliner2_batch(model: Any, batch: pa.Table, threshold: float, batch_size: int) -> pa.Table:
    table = gliner2_mod.extract(batch, model, threshold=threshold, batch_size=batch_size,
                                chunk_size=GLINER2_WINDOW_WORDS, chunk_overlap=GLINER2_OVERLAP_WORDS)
    verify_spans(table, batch)
    return table


def verify_spans(mentions: pa.Table, chunks: pa.Table) -> None:
    text_of = dict(zip(chunks["chunk_id"].to_pylist(), chunks["text"].to_pylist()))
    for r in mentions.to_pylist():
        if text_of[r["chunk_id"]][r["start"]:r["end"]] != r["mention"]:
            raise ValueError(f"tramo inconsistente en {r['chunk_id']}: {r['mention']!r} [{r['start']}:{r['end']}]")


def stage_gliner2(chunks: pa.Table, out: Path, model: Any, threshold: float, batch_size: int,
                  batch_chunks: int) -> dict[str, Any]:
    parts = out / "parts"
    parts.mkdir(parents=True, exist_ok=True)
    done, next_n = done_chunk_ids(parts, "gliner2")
    pending = chunks.filter(pc.invert(pc.is_in(chunks["chunk_id"], pa.array(list(done), pa.string()))))
    log.info("gliner2: %d hechos, %d pendientes", len(done), pending.num_rows)
    progress = Progress("gliner2", chunks.num_rows, len(done))
    t0 = time.perf_counter()
    rows = 0
    for i, batch in enumerate(batches(pending, batch_chunks)):
        table = run_gliner2_batch(model, batch, threshold, batch_size)
        ids = batch["chunk_id"].to_pylist()
        atomic_write(with_chunk_ids(table, ids), parts / f"gliner2.{next_n + i:05d}.parquet")
        rows += table.num_rows
        progress.step(len(ids))
    return {"processed_now": pending.num_rows, "resumed": len(done), "rows_now": rows,
            "seconds": round(time.perf_counter() - t0, 1)}


def stage_embed(chunks: pa.Table, out: Path, embedder: Embedder, batch_size: int, batch_chunks: int) -> dict:
    parts = out / "parts"
    parts.mkdir(parents=True, exist_ok=True)
    done, next_n = done_chunk_ids(parts, "embed")
    pending = chunks.filter(pc.invert(pc.is_in(chunks["chunk_id"], pa.array(list(done), pa.string()))))
    log.info("embed: %d hechos, %d pendientes (%s, dim %d)", len(done), pending.num_rows, embedder.name, embedder.dim)
    progress = Progress("embed", chunks.num_rows, len(done))
    t0 = time.perf_counter()
    for i, batch in enumerate(batches(pending, batch_chunks)):
        rows = batch.select(["chunk_id", "norm_short", "article_no", "text"]).to_pylist()
        vectors = embedder.encode(rows, batch_size)
        ids = [r["chunk_id"] for r in rows]
        atomic_write(with_chunk_ids(vectors_table(ids, vectors, embedder.name), ids),
                     parts / f"embed.{next_n + i:05d}.parquet")
        progress.step(len(ids))
    return {"processed_now": pending.num_rows, "resumed": len(done), "model": embedder.name, "dim": embedder.dim,
            "fallback_used": embedder.fallback_used, "seconds": round(time.perf_counter() - t0, 1)}


def collect(out: Path, stage: str, chunk_ids: list[str], empty_schema: pa.Schema) -> pa.Table:
    """Une los lotes de una etapa; falla si algun chunk del release no fue procesado."""
    parts = sorted(p for p in (out / "parts").iterdir() if RX_PART.match(p.name) and p.name.startswith(stage))
    tables = [pq.read_table(p) for p in parts]
    covered: set[str] = set()
    for p in parts:
        covered.update(json.loads((pq.read_schema(p).metadata or {}).get(b"chunk_ids", b"[]")))
    missing = [c for c in chunk_ids if c not in covered]
    if missing:
        raise ValueError(f"{stage}: faltan {len(missing)} chunks por procesar (p. ej. {missing[:3]})")
    if not tables:
        return pa.Table.from_pylist([], schema=empty_schema)
    table = pa.concat_tables([t.replace_schema_metadata(None) for t in tables])
    if stage == "embed":
        # Un chunk por fila: si un lote se reescribio, gana la primera aparicion.
        seen: set[str] = set()
        keep = []
        for i, c in enumerate(table["chunk_id"].to_pylist()):
            if c not in seen:
                seen.add(c)
                keep.append(i)
        table = table.take(keep)
    return table


# ----------------------------------------------------------------------------------------------------------
# Preflight
# ----------------------------------------------------------------------------------------------------------


def preflight(chunks: pa.Table, args: argparse.Namespace, device: str) -> None:
    """2 chunks reales + el mas largo por cada modelo; imprime s/chunk y total proyectado. No escribe nada."""
    lengths = [len(t) for t in chunks["text"].to_pylist()]
    longest = int(np.argmax(lengths))
    idx = sorted({0, min(1, chunks.num_rows - 1), longest})
    sample = chunks.take(idx)
    n = chunks.num_rows
    print(f"preflight: {len(idx)} chunks (indices {idx}; el mas largo tiene {lengths[longest]} caracteres) en {device}")
    report: dict[str, Any] = {}
    if not args.no_gliner2:
        t0 = time.perf_counter()
        model = load_gliner2(args.gliner2_model, device)
        load_s = time.perf_counter() - t0
        t0 = time.perf_counter()
        table = run_gliner2_batch(model, sample, args.threshold, args.batch_size)
        per = (time.perf_counter() - t0) / len(idx)
        report["gliner2"] = {"load_s": round(load_s, 1), "s_per_chunk": round(per, 3), "projected_s": round(per * n),
                             "mentions_in_sample": table.num_rows}
        print(f"  gliner2  carga {load_s:.1f} s | {per:.3f} s/chunk | proyeccion {per * n / 60:.1f} min para {n} chunks "
              f"| {table.num_rows} menciones en la muestra")
    if not args.no_embed:
        t0 = time.perf_counter()
        embedder = Embedder(args.embed_model, args.fallback_model, device)
        load_s = time.perf_counter() - t0
        t0 = time.perf_counter()
        vectors = embedder.encode(sample.select(["chunk_id", "norm_short", "article_no", "text"]).to_pylist(),
                                  args.embed_batch_size)
        per = (time.perf_counter() - t0) / len(idx)
        report["embed"] = {"model": embedder.name, "fallback_used": embedder.fallback_used, "dim": embedder.dim,
                           "load_s": round(load_s, 1), "s_per_chunk": round(per, 3), "projected_s": round(per * n)}
        print(f"  embed    {embedder.name} (repuesto: {embedder.fallback_used}) dim {vectors.shape[1]} | carga "
              f"{load_s:.1f} s | {per:.3f} s/chunk | proyeccion {per * n / 60:.1f} min para {n} chunks")
    total = sum(v["projected_s"] for v in report.values())
    print(f"  TOTAL proyectado: {total / 60:.1f} min de computo (+ cargas) para {n} chunks")
    print(json.dumps(report, ensure_ascii=False))


# ----------------------------------------------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    p = argparse.ArgumentParser(description="GLiNER2 + embeddings sobre chunks.parquet (RunPod)")
    p.add_argument("--chunks", type=Path, required=True)
    p.add_argument("--out", type=Path, default=Path("out"))
    p.add_argument("--preflight", action="store_true", help="2 chunks + el mas largo; imprime s/chunk y proyeccion")
    p.add_argument("--allow-cpu", action="store_true", help="no abortar sin CUDA (humo en la Mac)")
    p.add_argument("--limit", type=int, default=None, help="solo los primeros N chunks (humo)")
    p.add_argument("--no-gliner2", action="store_true")
    p.add_argument("--no-embed", action="store_true")
    p.add_argument("--gliner2-model", default=DEFAULT_GLINER2)
    p.add_argument("--embed-model", default=DEFAULT_EMBED)
    p.add_argument("--fallback-model", default=DEFAULT_FALLBACK)
    p.add_argument("--threshold", type=float, default=THRESHOLD)
    p.add_argument("--batch-size", type=int, default=8, help="lote interno de GLiNER2")
    p.add_argument("--embed-batch-size", type=int, default=32)
    p.add_argument("--batch-chunks", type=int, default=64, help="chunks por archivo de lote (reanudable)")
    args = p.parse_args(argv)

    device = pick_device(args.allow_cpu)
    chunks = read_chunks(args.chunks)
    if args.limit:
        chunks = chunks.slice(0, args.limit)
    log.info("%d chunks de %s en %s (%s)", chunks.num_rows, args.chunks, device, platform.platform())

    if args.preflight:
        preflight(chunks, args, device)
        return 0

    out = args.out
    out.mkdir(parents=True, exist_ok=True)
    if (out / "DONE").exists():
        log.info("%s/DONE ya existe; nada que hacer (borra el directorio para repetir)", out)
        return 0
    started = datetime.now(timezone.utc).isoformat(timespec="seconds")
    t_all = time.perf_counter()
    stages: dict[str, Any] = {}
    chunk_ids = chunks["chunk_id"].to_pylist()

    if not args.no_gliner2:
        model = load_gliner2(args.gliner2_model, device)
        stages["gliner2"] = {"model": args.gliner2_model, "threshold": args.threshold,
                             "window_words": GLINER2_WINDOW_WORDS, "overlap_words": GLINER2_OVERLAP_WORDS,
                             **stage_gliner2(chunks, out, model, args.threshold, args.batch_size, args.batch_chunks)}
        del model
    if not args.no_embed:
        embedder = Embedder(args.embed_model, args.fallback_model, device)
        stages["embed"] = {"doc_prefix": embedder.doc_template,
                           **stage_embed(chunks, out, embedder, args.embed_batch_size, args.batch_chunks)}

    # Finales: unir lotes, verificar y escribir atomico. DONE al final de todo.
    if not args.no_gliner2:
        mentions = collect(out, "gliner2", chunk_ids, schema.MENTIONS)
        verify_spans(mentions, chunks)
        atomic_write(mentions, out / "mentions_gliner2.parquet")
        stages["gliner2"]["rows_total"] = mentions.num_rows
    if not args.no_embed:
        vectors = collect(out, "embed", chunk_ids, VECTORS)
        atomic_write(vectors, out / "vectors.parquet")
        stages["embed"]["rows_total"] = vectors.num_rows
    manifest = {
        "started_at": started, "finished_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "seconds_total": round(time.perf_counter() - t_all, 1), "device": device, "platform": platform.platform(),
        "chunks": {"path": str(args.chunks), "sha256": sha256_file(args.chunks), "rows": chunks.num_rows,
                   "limit": args.limit},
        "stages": stages,
        "python": sys.version.split()[0],
    }
    try:
        import torch

        manifest["torch"] = torch.__version__
    except ImportError:
        pass
    atomic_text(json.dumps(manifest, ensure_ascii=False, indent=2), out / "manifest.json")
    atomic_text(manifest["finished_at"] + "\n", out / "DONE")
    log.info("DONE en %.1f s: %s", manifest["seconds_total"], json.dumps(
        {k: {kk: vv for kk, vv in v.items() if kk in ("rows_total", "model", "fallback_used", "seconds")}
         for k, v in stages.items()}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
