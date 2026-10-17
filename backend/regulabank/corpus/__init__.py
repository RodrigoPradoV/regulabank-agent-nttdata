"""Etapa corpus: de seeds/norms.csv a un release con norms.parquet, chunks.parquet y manifest.json.

Capas (docs/02-corpus.md): bronze (original + sha256), silver (texto por pagina, nunca se modifica),
gold (release versionado con chunks cuyo texto es un rango exacto del articulo).
"""
