"""CLI de la etapa corpus.

  python -m regulabank.corpus build --norms backend/seeds/norms.csv --out data/releases/r0001
  python -m regulabank.corpus inspect --release data/releases/r0001 --n 20
"""

from __future__ import annotations

import argparse
import json
import logging
import random
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import pyarrow.parquet as pq

from regulabank.corpus import capture as capture_mod
from regulabank.corpus import chunks as chunks_mod
from regulabank.corpus import extract as extract_mod
from regulabank.corpus import norms as norms_mod
from regulabank.corpus import parse as parse_mod
from regulabank.shared import config

log = logging.getLogger("regulabank.corpus")


def code_version() -> dict:
    """Commit del repo y version del paquete; None cuando no hay git o el paquete no esta instalado."""
    try:
        git = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True,
            cwd=Path(__file__).resolve().parent,
        ).stdout.strip()
    except (subprocess.CalledProcessError, OSError):
        git = None
    try:
        from importlib.metadata import version

        pkg = version("regulabank")
    except Exception:  # noqa: BLE001 - paquete sin instalar
        pkg = None
    return {"git": git, "package": pkg}


def build(norms_csv: Path, out: Path, bronze: Path, silver: Path, sleep_s: float) -> dict:
    """Todos los pasos: seeds -> bronze -> silver -> unidades -> chunks -> validate -> release."""
    settings = config.load()
    norms = norms_mod.load_norms(norms_csv)
    log.info("%d normas en %s", len(norms), norms_csv)

    captures = capture_mod.capture_all(norms, bronze, settings.http_user_agent, sleep_s=sleep_s)
    for c in captures:
        log.info("capture %-32s %s %s", c.norm_id, c.outcome, c.path or "")

    ready: list[tuple[norms_mod.Norm, parse_mod.ParsedDoc, int, str]] = []
    skipped: dict[str, str] = {}
    for norm, cap in zip(norms, captures):
        if not cap.ok:
            skipped[norm.norm_id] = cap.outcome
            continue
        norm.source_path = str(cap.path)
        norm.source_sha256 = cap.sha256
        pages = extract_mod.extract_to_silver(norm.norm_id, cap.path, silver)
        parsed = parse_mod.parse_pages(pages, cap.path.suffix)
        if not parsed.units:
            skipped[norm.norm_id] = "error:sin texto"
            log.warning("%s: sin texto; se deja fuera del release", norm.norm_id)
            continue
        if parsed.fallback:
            log.warning("%s: sin estructura detectada; chunks por parrafo con confianza %.1f", norm.norm_id,
                        chunks_mod.CONFIDENCE_FALLBACK)
        log.info("parse   %-32s pages=%d units=%d %s coverage=%.3f", norm.norm_id, len(pages),
                 parsed.stats["units"], parsed.stats["by_kind"], parsed.stats["coverage"])
        ready.append((norm, parsed, len(pages), cap.path.suffix))
    if not ready:
        raise SystemExit("ninguna norma lista: no se escribe el release")

    lengths = [len(u.text) for _, parsed, _, _ in ready for u in parsed.units]
    cap_chars = chunks_mod.cap_from_lengths(lengths)
    rows: list[dict] = []
    unit_texts: dict[str, str] = {}
    per_norm: dict[str, dict] = {}
    hard_cuts = 0
    for norm, parsed, n_pages, suffix in ready:
        norm_rows, hard = chunks_mod.build_chunks(norm, parsed.units, cap_chars, parsed.page_offsets, suffix,
                                                  fallback=parsed.fallback)
        hard_cuts += hard
        for u in parsed.units:
            unit_texts[f"{norm.norm_id}#{u.id_suffix}"] = u.text
        rows.extend(norm_rows)
        per_norm[norm.norm_id] = {
            "pages": n_pages, "chars": len(parsed.text), "units": parsed.stats["units"],
            "by_kind": parsed.stats["by_kind"], "chunks": len(norm_rows), "hard_cuts": hard,
            "coverage": parsed.stats["coverage"], "fallback": parsed.fallback, "parser": parsed.stats,
        }
    chunks_mod.validate(rows, unit_texts)

    out.mkdir(parents=True, exist_ok=True)
    kept = [n for n, _, _, _ in ready]
    pq.write_table(norms_mod.to_table(kept), out / "norms.parquet")
    pq.write_table(chunks_mod.to_table(rows), out / "chunks.parquet")
    manifest = {
        "release_id": out.name,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "code_version": code_version(),
        "inputs": {
            "norms_csv": {"path": str(norms_csv), "sha256": capture_mod.sha256_of(norms_csv)},
            "sources": {
                n.norm_id: {"path": n.source_path, "sha256": n.source_sha256, "url": n.source_url}
                for n in kept
            },
        },
        "params": {
            "cap_chars": cap_chars,
            "cap_percentile": chunks_mod.CAP_PERCENTILE,
            "min_piece_ratio": chunks_mod.MIN_PIECE_RATIO,
            "confidence_parsed": chunks_mod.CONFIDENCE_PARSED,
            "confidence_fallback": chunks_mod.CONFIDENCE_FALLBACK,
            "review_below": chunks_mod.REVIEW_BELOW,
            "page_sep": extract_mod.PAGE_SEP,
            "unit_length_stats": {
                "n": len(lengths), "min": min(lengths), "median": int(sorted(lengths)[len(lengths) // 2]),
                "max": max(lengths),
            },
        },
        "counts": {
            "norms": len(kept),
            "articles": len(unit_texts),
            "chunks": len(rows),
            "hard_cuts": hard_cuts,
            "by_node_type": dict(sorted(Counter(r["node_type"] for r in rows).items())),
            "by_extraction_method": dict(sorted(Counter(r["extraction_method"] for r in rows).items())),
            "review_required": sum(1 for r in rows if r["review_required"]),
        },
        "per_norm": per_norm,
        "skipped": skipped,
        "fingerprint": chunks_mod.fingerprint(rows),
    }
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def inspect(release: Path, n: int, seed: int, width: int = 400) -> None:
    table = pq.read_table(release / "chunks.parquet")
    rows = table.to_pylist()
    sample = random.Random(seed).sample(rows, min(n, len(rows)))
    for r in sample:
        print("=" * 100)
        print(f"{r['chunk_id']}  {r['citation']}  [{r['node_type']}, {r['extraction_method']}, conf {r['confidence']:.1f}]")
        print(f"  path: {r['parent_path']}")
        body = r["text"].strip().replace("\n", " ")
        print("  " + (body[:width] + (" ..." if len(body) > width else "")))


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(prog="python -m regulabank.corpus")
    sub = parser.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build", help="seeds -> bronze -> silver -> release")
    b.add_argument("--norms", type=Path, required=True)
    b.add_argument("--out", type=Path, required=True)
    b.add_argument("--bronze", type=Path, default=Path("data/bronze"))
    b.add_argument("--silver", type=Path, default=Path("data/silver"))
    b.add_argument("--sleep", type=float, default=5.0, help="segundos entre peticiones a portales")
    i = sub.add_parser("inspect", help="muestra chunks al azar con su cita")
    i.add_argument("--release", type=Path, required=True)
    i.add_argument("--n", type=int, default=20)
    i.add_argument("--seed", type=int, default=7)
    i.add_argument("--width", type=int, default=400)
    args = parser.parse_args(argv)
    if args.cmd == "build":
        manifest = build(args.norms, args.out, args.bronze, args.silver, args.sleep)
        print(json.dumps({k: manifest[k] for k in ("release_id", "counts", "params", "skipped", "fingerprint")},
                         ensure_ascii=False, indent=2))
    else:
        inspect(args.release, args.n, args.seed, args.width)
    return 0


if __name__ == "__main__":
    sys.exit(main())
