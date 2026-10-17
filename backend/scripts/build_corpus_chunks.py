from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = BACKEND_ROOT.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from regulabank.ingestion import build_corpus_chunks


def main() -> None:
    parser = argparse.ArgumentParser(description="Build deterministic normative chunks (Parquet + CSV) for GraphRAG.")
    parser.add_argument(
        "--sources",
        type=Path,
        default=REPOSITORY_ROOT / "fuentes_descargadas",
        help="Directory containing manifest.json and downloaded source files.",
    )
    parser.add_argument(
        "--graph",
        type=Path,
        default=REPOSITORY_ROOT / "data" / "graph_ingest_v0",
        help="Output of extract_document_graph.py (hierarchy, gates and validated relations).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=REPOSITORY_ROOT / "data" / "corpus_v0",
        help="Output directory for corpus_chunks.parquet/csv, quality_report.csv and manifest.json.",
    )
    args = parser.parse_args()
    manifest = build_corpus_chunks(args.sources, args.graph, args.output)
    counts = {key: value for key, value in manifest["counts"].items() if not isinstance(value, dict)}
    print(json.dumps({"counts": counts, "validations": {name: outcome["passed"] for name, outcome in manifest["validations"].items()}}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
