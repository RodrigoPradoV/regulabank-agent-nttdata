# 12 · Infraestructura

## Stack

| Pieza | Elección | Nota |
|---|---|---|
| Python | ≥ 3.11, `uv` para el entorno | un solo `pyproject.toml`; extras `graph`, `search`, `agents`, `ui` |
| Orquestación | `langgraph >= 1.2, < 1.3` | `SqliteSaver` en `data/state/checkpoints.sqlite`, no en la base del corpus |
| LLM | `anthropic` (Claude) o Azure OpenAI; `FakeProvider` siempre disponible | `MODEL_PROVIDER=mock|anthropic|azure_openai`; claves solo por variable de entorno |
| Vectores + léxico | LanceDB ≥ 0.20 (FTS en español nativo) | un directorio por release: `data/views/<release>/lancedb` |
| Grafo | FalkorDB **v4.22.0** en Docker, puerto 6381 | la 6.x en Rust entra en pánico con tildes en el slow_log; fijar la versión |
| PageRank | `scipy.sparse` en memoria | cargado al arrancar el servicio de búsqueda |
| Modelos | `sentence-transformers ≥ 6`, `transformers ≥ 5`, `torch ≥ 2.14`, `gliner2`, `wtpsplit` | descarga a caché local; sin GPU para la demo |
| PDF | `pymupdf`; OCR `tesseract` solo si la página es imagen | |
| HTTP | `httpx` | sin navegador |
| Datos | `pyarrow`, `duckdb` para consultas sobre Parquet | |
| API | FastAPI; contratos Pydantic en `shared/contracts.py` con `schema_version` | |
| UI | Streamlit (rápido) o React + Vite | |
| Tests | `pytest`, `ruff`; `naming_check` opcional | |

## Docker

```yaml
services:
  falkordb:
    image: falkordb/falkordb:v4.22.0
    ports: ["127.0.0.1:6381:6379", "127.0.0.1:3011:3000"]
    volumes: ["./data/falkor:/data"]
```

Perfiles: `local` (todo en la laptop, mock), `cloud` (proveedor real), `graph` (solo FalkorDB).

## Variables de entorno (con default, leídas en un solo lugar)

```
MODEL_PROVIDER=mock
ANTHROPIC_API_KEY=            # solo si provider=anthropic
AZURE_OPENAI_ENDPOINT= / AZURE_OPENAI_API_KEY= / AZURE_OPENAI_DEPLOYMENT=
FALKOR_HOST=127.0.0.1  FALKOR_PORT=6381  FALKOR_GRAPH=regulabank
LANCE_DIR=data/views/current/lancedb
RELEASE_ID=current
BUDGET_USD_PER_RUN=2.0
HTTP_USER_AGENT="regulabank-hack/0.1 (+contacto)"
```

## Recursos y costo

- **La demo no necesita GPU:** gemma 300M, GLiNER2 large y el NLI corren en CPU/MPS para unos miles de chunks.
  GPU en la nube solo por encima de ~50 mil chunks, con prueba de humo (2 chunks reales más la fila más larga),
  tope duro de horas y borrado del pod al terminar.
- **Memoria:** construir por lotes; un índice completo en memoria dejó inutilizable una laptop de 16 GB en otro
  proyecto.
- **APIs que cobran por token:** `--cap-usd` obligatorio en cada corrida; una llamada de prueba por modelo antes de
  cualquier lote; en modelos con razonamiento fijar el esfuerzo y el tope de salida (se factura 3-5× el texto
  visible); reportar gasto real frente al estimado.
- **Un modelo local a la vez** en la máquina.

## Operación

- Un release es inmutable; las vistas se reconstruyen desde él; el puntero `current` cambia al final y solo si el
  golden de regresión pasa.
- Trabajos largos: una sola instancia con `pid` y lock de escritor; se vigila el avance (filas por minuto), no la
  existencia del proceso; si pasan 15 minutos sin avance, sale con error.
- Ledger en `data/state/ledger.jsonl`, se agrega, nunca se reescribe; también cuando la corrida falla.
- Secretos nunca en el repo; `data/` en `.gitignore`; las políticas internas sintéticas sí se versionan (son del
  equipo), las normas públicas se descargan por script.
