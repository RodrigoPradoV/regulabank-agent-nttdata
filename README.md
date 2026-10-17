# regulabank

GraphRAG de normativa bancaria y políticas internas, con citas literales verificadas, vigencia por fecha,
detección de contradicciones política ↔ norma y humano en el bucle. Reto Banca (NTT DATA x Sundai), punto 2:
«encontrar la información correcta y vigente entre múltiples documentos».

## Estructura

| Carpeta | Qué es |
|---|---|
| `backend/` | Python 3.11: paquete `regulabank` (api, shared; luego corpus, graphs, search, agents, eval), `scripts/`, `seeds/`, `tests/` |
| `frontend/` | Angular 21: sidebar + topbar + shelf, módulos Textos, Conflictos y Consulta |
| `charter/` | cómo se comportan los LLMs: principios, estilo, herramientas, riesgo y prompts versionados |
| `docs/` | blueprint, un `.md` por área (empezar por `docs/README.md`) |
| `infra/` | Docker: FalkorDB y Dockerfile del backend |
| `data/` | gitignored: bronze, silver, releases, views, state |

Nada cruza de carpeta hacia arriba: el frontend solo conoce los contratos de la API
(`backend/regulabank/api/contracts.py`, espejados en `frontend/src/app/core/models.ts`); el backend no conoce al
frontend; los prompts viven en `charter/`, nunca dentro de un `.py`.

## Levantarlo en local (10 minutos)

### 0. Requisitos

| Qué | Versión | Cómo comprobar |
|---|---|---|
| Docker (Docker Desktop, Colima u OrbStack) con `docker-compose` | cualquiera reciente | `docker version` y `docker-compose version` |
| Python | 3.11 o 3.12 | `python3 --version` |
| uv | cualquiera | `uv --version` (instalar: `curl -LsSf https://astral.sh/uv/install.sh \| sh`) |
| Node | 20 o 22 | `node --version` |

Sin claves de API: todo corre con `MODEL_PROVIDER=mock`.

### 1. Clonar

```bash
git clone https://github.com/RodrigoPradoV/regulabank-agent-nttdata.git
cd regulabank-agent-nttdata
```

### 2. Grafo (FalkorDB) en Docker

```bash
docker-compose -f infra/compose.yaml up -d falkordb
docker ps | grep regulabank-falkordb        # debe decir (healthy)
```

Queda en `127.0.0.1:6381` y su UI en http://127.0.0.1:3011. Si el 6381 está ocupado, cambia el puerto en
`infra/compose.yaml` y en `FALKOR_PORT`.

### 3. Backend (FastAPI) en :8010

```bash
cd backend
uv venv --python 3.11
uv pip install -e ".[dev]"
.venv/bin/python scripts/smoke.py          # debe imprimir dos líneas OK (Lance y Falkor)
.venv/bin/uvicorn regulabank.api.app:app --reload --port 8010
```

Comprobar: http://127.0.0.1:8010/health → `{"ok": true, "provider": "mock", ...}` y http://127.0.0.1:8010/docs
(Swagger con todos los endpoints).

### 4. Frontend (Angular) en :4200

En otra terminal:

```bash
cd frontend
npm install
npx ng serve
```

Abrir http://localhost:4200. Rutas: `/norms` (Textos), `/norms/<id>` (detalle con shelf por artículo),
`/conflicts` (cola de contradicciones, confirmar o descartar), `/chat` (consulta con citas y selector de vigencia).

### 5. Qué probar en la demo

1. En `/chat` pregunta «¿Cuál es el plazo para reportar una operación sospechosa a la UIF?» con vigencia hoy:
   responde 15 días hábiles, cita verificada, riesgo `auto`.
2. Cambia «Vigencia al» a 2018-01-01 y repite: responde 30 días calendario (versión derogada), queda «Pendiente de
   persona». Clic en la cita abre el shelf con las dos versiones.
3. Pregunta «¿Cuál es la tasa máxima que fija la SBS para hipotecas?»: se abstiene (no está en el corpus).
4. En `/conflicts`: la política interna da 20 días y la norma exige 15; confirmar la contradicción.

### Todo con Docker (opcional)

```bash
docker-compose -f infra/compose.yaml run --rm app      # construye la imagen del backend y corre el smoke test
```

### Problemas frecuentes

| Síntoma | Causa | Arreglo |
|---|---|---|
| `Bind for 127.0.0.1:6381 failed` | otro contenedor usa el puerto | cambiar puerto en `infra/compose.yaml` y `FALKOR_PORT` |
| `docker compose: unknown command` | plugin no instalado | usar `docker-compose` (con guion) |
| el chat dice «No pude contactar al servicio» | backend apagado o en otro puerto | paso 3; el frontend apunta a `API_URL` en `frontend/src/app/core/api.service.ts` |
| `FAIL check_falkor` en el smoke | FalkorDB no está `healthy` | `docker-compose -f infra/compose.yaml logs falkordb` |
| `ng serve` falla por versión de Node | Node < 20 | instalar Node 20 o 22 |

## Variables de entorno

Copiar `.env.example` a `.env` (opcional en local; los defaults sirven). Se leen en un solo lugar:
`backend/regulabank/shared/config.py`. `MODEL_PROVIDER=mock|anthropic|azure_openai`; las claves nunca van al repo.

## Dónde seguir

- `docs/README.md`: principios, vocabulario y mapa de las 12 áreas.
- `docs/11-demo.md`: reparto por sprint y guion de la demo.
- `charter/`: antes de escribir o cambiar un prompt.
- Siguiente paso de código: reemplazar `backend/regulabank/api/mock.py` por lecturas reales a Lance y Falkor
  (`docs/02-corpus.md`, `docs/08-retrieval.md`).
