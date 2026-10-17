# graph_v2: solo corpus real, 5 tipos de arista, vectores de OpenAI

2.976 chunks reales (`data/graph_v0/chunks.parquet`), 3.000 entidades, 47.992 aristas:
NEXT 2.959, REFERS_TO 1.083, MENTIONS 20.942, SIMILAR (coseno de OpenAI), y **CONTRADICTS 861** (RoBERTa XNLI, p ≥ 0,9, sin validar;
la evidencia son las dos oraciones literales). La tabla completa de 28.915 pares está en `conflicts.parquet`.

No se versionan los vectores (18 MB) ni LanceDB: se regeneran.

```bash
cd backend
python scripts/reembed.py --chunks ../data/graph_v0/chunks.parquet --model openai:text-embedding-3-small --out ../data/graph_v2/pod/vectors.parquet --yes   # ~0,03 USD
mkdir -p ../data/graph_v2/release && cp ../data/graph_v0/chunks.parquet ../data/graph_v2/conflicts.parquet ../data/graph_v2/release/
cp ../data/graph_v0/pod/mentions_gliner2.parquet ../data/graph_v2/pod/
python -m regulabank.graphs build --release ../data/graph_v2/release --pod-out ../data/graph_v2/pod --norms seeds/norms.csv
python -m regulabank.graphs conflicts-edges --release ../data/graph_v2/release          # agrega CONTRADICTS (p >= 0,9)
```
