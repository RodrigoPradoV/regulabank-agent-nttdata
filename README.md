# regulabank-agent-nttdata
Multi-agent GraphRAG system for banking regulatory compliance, policy versioning, contradiction detection, and explainable decision support with Human-in-the-Loop.

## Correr la maqueta

```bash
# 1. grafo (FalkorDB) en Docker
docker-compose -f infra/compose.yaml up -d falkordb

# 2. API (FastAPI, datos de muestra, proveedor mock) en :8010
uv venv && uv pip install -e ".[dev]"
.venv/bin/uvicorn regulabank.api.app:app --reload --port 8010

# 3. UI (Angular 21) en :4200
cd ui && npm install && npx ng serve
```

Blueprint completo en `docs/` (empezar por `docs/README.md`). Estructura: `src/regulabank/` (api, shared; luego corpus,
graphs, search, agents, eval), `ui/` (Angular: sidebar + topbar + shelf, módulos Textos, Conflictos y Consulta),
`infra/` (Docker), `seeds/` (datos de dominio), `data/` (gitignored).
