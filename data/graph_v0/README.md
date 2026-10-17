# graph_v0: grafo del corpus v0

Salida de `python -m regulabank.graphs build --release <release> --pod-out data/graph_v0/pod` sobre
`data/corpus_v0/corpus_chunks.parquet` (2.976 chunks, contrato de 25 columnas).

| Archivo | Contenido |
|---|---|
| `mentions.parquet` | 47.454 menciones GLiNER2 y regex, con `text[start:end] == mention` |
| `entities.parquet` | entidades canonicas (3.000) |
| `edges.parquet` | 4 aristas: NEXT 2.959, REFERS_TO 1.083, MENTIONS 20.942, SIMILAR 22.229 |
| `graph_manifest.json` | conteos, modelos, huellas |
| `pod/mentions_gliner2.parquet` | GLiNER2 `fastino/gliner2-large-v1`, RTX 4090 en RunPod, 154 s |
| `pod/vectors.parquet` | `google/embeddinggemma-300m`, dim 768, corrida en Mac (MPS) |

LanceDB no se versiona: se regenera con el comando de arriba. FalkorDB se carga con `--load`.
Antes de cargar, el cargador quita caracteres de control (un chunk de Basilea trae un NUL de PDF);
el texto del parquet queda intacto.
