# infra

Dos almacenes (docs/12-infra.md): **FalkorDB** v4.22.0 para el grafo y **LanceDB** para vectores y BM25. LanceDB es
una libreria embebida: no hay servidor, escribe en `data/views/<release>/lancedb`.

## Levantar

(`docker-compose` o `docker compose`, segun como este instalado el plugin.)

```bash
docker-compose -f infra/compose.yaml up -d falkordb       # grafo en 127.0.0.1:6381, UI en http://127.0.0.1:3011
docker-compose -f infra/compose.yaml run --rm app         # construye la imagen y corre scripts/smoke.py
```

Sin Docker para la app (solo FalkorDB en contenedor):

```bash
cd backend && uv venv && uv pip install -e ".[dev]"
uv run python scripts/smoke.py
```

Los modelos (embeddings, GLiNER2, NLI) se instalan aparte: `uv pip install -e ".[models]"`. No van en la imagen base.

## Variables

Copiar `.env.example` a `.env`. Se leen en un solo lugar: `backend/regulabank/shared/config.py`.
