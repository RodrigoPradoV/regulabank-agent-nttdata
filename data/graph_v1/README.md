# graph_v1: corpus real + normas sintéticas, listo para el demo

3.171 chunks (2.976 del corpus v0 con `published` + 195 de las 17 normas sintéticas de `seeds/norms.csv`), 3.120 entidades,
34 normas, 49.133 aristas (NEXT, REFERS_TO, MENTIONS, SIMILAR). Vectores `embeddinggemma-300m`; menciones GLiNER2 del pod
(corpus real) y de la Mac (sintéticas).

## Levantar el demo

```bash
cd backend
# 1. LanceDB (no se versiona): crea data/graph_v1/lancedb y carga FalkorDB (puerto 6381)
python -m regulabank.graphs build --release ../data/graph_v1 --pod-out ../data/graph_v1/pod --norms seeds/norms.csv --load
# 2. API con el agente real (gpt-5-mini: OPENAI_API_KEY o llavero `lumen-openai`; sin clave: MODEL_PROVIDER=mock)
REGULABANK_RELEASE=../data/graph_v1 MODEL_PROVIDER=openai uvicorn regulabank.api.app:app --port 8011
# 3. Frontend
cd ../frontend && API_TARGET=http://127.0.0.1:8011 npx ng serve --port 4210      # http://localhost:4210/chat
```

## Medición (docs/eval/2026-10-17-retrieval.json)

Golden `seeds/questions.csv`: 40 preguntas, 34 con respuesta y 6 negativas; 13 reservadas que no se usaron para elegir nada.
