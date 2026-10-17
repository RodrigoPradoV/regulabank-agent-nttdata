"""CLI de la etapa graphs: de un release (chunks.parquet) a menciones, entidades, aristas, LanceDB y FalkorDB.

  python -m regulabank.graphs build --release data/releases/r0001 [--pod-out DIR] [--no-gliner2] [--no-embed] [--load]

- Menciones regex/gazetteer/alias siempre en local. GLiNER2 corre en local salvo `--no-gliner2`; si `--pod-out`
  trae `mentions_gliner2.parquet` se usa ese (no se vuelve a correr el modelo).
- Vectores: `--pod-out/vectors.parquet` si existe; si no, embedder local (`--embedder auto` = gemma con repuesto
  e5; `fake` solo para pruebas). `--no-embed` deja la tabla LanceDB sin vector y sin SIMILAR.
- Escribe mentions.parquet, entities.parquet, edges.parquet, lancedb/ (tabla `chunks` con FTS en espanol) y
  graph_manifest.json en el release. `--load` carga FalkorDB (se salta si esta caido).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

from regulabank.corpus.__main__ import code_version
from regulabank.graphs import aggregate as aggregate_mod
from regulabank.graphs import edges as edges_mod
from regulabank.graphs import embed as embed_mod
from regulabank.graphs import entities as entities_mod
from regulabank.graphs import gliner2 as gliner2_mod
from regulabank.graphs import load as load_mod
from regulabank.graphs import params as params_mod
from regulabank.shared import config, schema

log = logging.getLogger("regulabank.graphs")


def _fingerprint(table: pa.Table) -> str:
    hashes = sorted(
        hashlib.sha256(json.dumps(r, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()
        for r in table.to_pylist()
    )
    return hashlib.sha256("\n".join(hashes).encode("ascii")).hexdigest()


def _device() -> str | None:
    try:
        import torch  # noqa: PLC0415
    except ImportError:
        return None
    if torch.cuda.is_available():
        return "cuda"
    if torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def build(release: Path, pod_out: Path | None, no_gliner2: bool, no_embed: bool, embedder_kind: str,
          lance_dir: Path | None, norms_csv: Path | None, do_load: bool, device: str | None) -> dict:
    settings = config.load()
    params = params_mod.load()
    chunks = pq.read_table(release / "chunks.parquet")
    if not chunks.schema.equals(schema.CHUNKS):
        raise ValueError(f"{release}/chunks.parquet no cumple schema.CHUNKS")
    chunk_ids = chunks["chunk_id"].to_pylist()
    log.info("%d chunks en %s", chunks.num_rows, release)
    manifest: dict = {"release_id": release.name, "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                      "code_version": code_version(), "params": params, "models": {}, "pod": None}
    device = device or _device()

    # 1. Menciones regex + gazetteer + alias de normas.
    t0 = time.perf_counter()
    aliases = entities_mod.NormAliases.from_csv(norms_csv) if norms_csv else entities_mod.NormAliases.from_csv()
    mentions = entities_mod.extract_chunks(chunks, aliases=aliases)
    log.info("regex/gazetteer: %d menciones en %.1f s (%d alias de normas)", mentions.num_rows,
             time.perf_counter() - t0, len(aliases.mapping))

    # 2. GLiNER2: del pod o local.
    pod_mentions = pod_out / "mentions_gliner2.parquet" if pod_out else None
    if pod_mentions and pod_mentions.exists():
        extra = pq.read_table(pod_mentions)
        unknown = set(extra["chunk_id"].to_pylist()) - set(chunk_ids)
        if unknown:
            raise ValueError(f"{pod_mentions}: {len(unknown)} chunk_id no estan en el release")
        mentions = gliner2_mod.merge(mentions, extra)
        manifest["models"]["gliner2"] = {"source": "pod", "rows": extra.num_rows}
        log.info("gliner2 (pod): %d menciones", extra.num_rows)
    elif not no_gliner2:
        model_name = params["entities"]["gliner2_model"]
        t0 = time.perf_counter()
        model = gliner2_mod.load_model(model_name, device=device if device != "mps" else None)
        extra = gliner2_mod.extract(chunks, model, threshold=float(params["entities"]["gliner2_threshold"]))
        mentions = gliner2_mod.merge(mentions, extra)
        elapsed = time.perf_counter() - t0
        manifest["models"]["gliner2"] = {"source": "local", "model": model_name, "rows": extra.num_rows,
                                         "seconds": round(elapsed, 1), "device": device}
        log.info("gliner2 (local, %s): %d menciones en %.1f s (%.2f s/chunk)", device, extra.num_rows, elapsed,
                 elapsed / max(chunks.num_rows, 1))
    else:
        manifest["models"]["gliner2"] = {"source": "skipped"}
        log.info("gliner2: omitido (--no-gliner2)")
    if pod_out and (pod_out / "manifest.json").exists():
        manifest["pod"] = json.loads((pod_out / "manifest.json").read_text(encoding="utf-8"))

    # 3. Entidades.
    entities = aggregate_mod.aggregate(mentions, chunks, params)
    log.info("entidades: %d", entities.num_rows)

    # 4. Vectores: pod, local o ninguno.
    vectors: np.ndarray | None = None
    pod_vectors = pod_out / "vectors.parquet" if pod_out else None
    if pod_vectors and pod_vectors.exists():
        vectors, model_name = embed_mod.read_vectors(pq.read_table(pod_vectors), chunk_ids)
        manifest["models"]["embed"] = {"source": "pod", "model": model_name, "dim": int(vectors.shape[1])}
        log.info("vectores (pod): %s dim %d", model_name, vectors.shape[1])
    elif not no_embed:
        t0 = time.perf_counter()
        if embedder_kind == "fake":
            embedder = embed_mod.FakeEmbedder()
        else:
            embedder = embed_mod.load_embedder(settings.embed_model, params["embed"]["fallback_model"],
                                               int(params["embed"]["batch_size"]), device=device)
        vectors = embed_mod.embed_chunks(chunks, embedder)
        manifest["models"]["embed"] = {"source": "local", "model": embedder.name, "dim": int(vectors.shape[1]),
                                       "seconds": round(time.perf_counter() - t0, 1), "device": device,
                                       "fallback_used": embedder.name == params["embed"]["fallback_model"]}
        log.info("vectores (local): %s dim %d en %.1f s", embedder.name, vectors.shape[1], time.perf_counter() - t0)
        pq.write_table(embed_mod.vectors_table(chunk_ids, vectors, embedder.name), release / "vectors.parquet")
    else:
        manifest["models"]["embed"] = {"source": "skipped"}
        log.info("vectores: omitidos (--no-embed)")

    # 5. LanceDB: tabla chunks (+ vector) con FTS en espanol.
    lance_dir = lance_dir or (release / "lancedb")
    lance_table = embed_mod.write_lance(lance_dir, chunks, vectors)
    log.info("lancedb: %s/chunks (%d filas, vector=%s)", lance_dir, lance_table.count_rows(), vectors is not None)

    # 6. Aristas.
    edges, stats = edges_mod.build_edges(chunks, entities, mentions, vectors, params,
                                         lance_table=lance_table if vectors is not None else None)
    log.info("aristas: %s (sin resolver: %d)", stats["edges_by_type"], stats["refers_to_unresolved"])

    # 7. Escritura y manifiesto.
    pq.write_table(mentions, release / "mentions.parquet")
    pq.write_table(entities, release / "entities.parquet")
    pq.write_table(edges, release / "edges.parquet")
    manifest["counts"] = {
        "chunks": chunks.num_rows,
        "mentions": mentions.num_rows,
        "mentions_by_method": dict(sorted(Counter(mentions["method"].to_pylist()).items())),
        "mentions_by_type": dict(sorted(Counter(mentions["type"].to_pylist()).items())),
        "entities": entities.num_rows,
        "entities_by_type": dict(sorted(Counter(entities["type"].to_pylist()).items())),
        "edges": edges.num_rows,
        "edges_by_type": stats["edges_by_type"],
        "refers_to_unresolved": stats["refers_to_unresolved"],
        "vectors": int(vectors.shape[0]) if vectors is not None else 0,
    }
    manifest["refers_to_unresolved_targets"] = stats["refers_to_unresolved_targets"]
    manifest["lance_dir"] = str(lance_dir)
    manifest["fingerprint"] = {"mentions": _fingerprint(mentions), "entities": _fingerprint(entities),
                               "edges": _fingerprint(edges)}

    # 8. FalkorDB.
    if do_load:
        counts = load_mod.load(chunks, entities, edges, settings)
        manifest["falkor"] = {"loaded": counts is not None, "graph": settings.falkor_graph, "counts": counts}
        log.info("falkordb: %s", "cargado " + json.dumps(counts) if counts else "no disponible, se salta")
    else:
        manifest["falkor"] = {"loaded": False, "graph": settings.falkor_graph, "counts": None}
    (release / "graph_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2, default=str),
                                                  encoding="utf-8")
    return manifest


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(prog="python -m regulabank.graphs")
    sub = parser.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build", help="release -> mentions, entities, edges, lancedb, graph_manifest")
    b.add_argument("--release", type=Path, required=True)
    b.add_argument("--pod-out", type=Path, default=None, help="salida del pod (mentions_gliner2, vectors)")
    b.add_argument("--no-gliner2", action="store_true", help="no correr GLiNER2 en local")
    b.add_argument("--no-embed", action="store_true", help="sin vectores ni SIMILAR")
    b.add_argument("--embedder", choices=("auto", "fake"), default="auto", help="fake: solo pruebas")
    b.add_argument("--lance-dir", type=Path, default=None, help="por defecto <release>/lancedb")
    b.add_argument("--norms", type=Path, default=None, help="seeds/norms.csv con la columna aliases")
    b.add_argument("--device", default=None, help="cuda | mps | cpu (por defecto el mejor disponible)")
    b.add_argument("--load", action="store_true", help="cargar FalkorDB")
    args = parser.parse_args(argv)
    try:
        manifest = build(args.release, args.pod_out, args.no_gliner2, args.no_embed, args.embedder, args.lance_dir,
                         args.norms, args.load, args.device)
    except gliner2_mod.Gliner2NotInstalled as exc:
        print(f"{exc}\n(o bien: --no-gliner2 para omitirlo)", file=sys.stderr)
        return 2
    print(json.dumps({k: manifest[k] for k in ("release_id", "counts", "models", "falkor")}, ensure_ascii=False,
                     indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
