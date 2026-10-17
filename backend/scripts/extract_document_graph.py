from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = BACKEND_ROOT.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from regulabank.ingestion import build_document_graph


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract deterministic document hierarchy for GraphRAG.")
    parser.add_argument(
        "--sources",
        type=Path,
        default=REPOSITORY_ROOT / "fuentes_descargadas",
        help="Directory containing manifest.json and downloaded source files.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=REPOSITORY_ROOT / "data" / "graph_ingest_v0",
        help="Output directory for Parquet graph tables and audit report.",
    )
    args = parser.parse_args()
    result = build_document_graph(args.sources, args.output)
    print(json.dumps(result["counts"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
