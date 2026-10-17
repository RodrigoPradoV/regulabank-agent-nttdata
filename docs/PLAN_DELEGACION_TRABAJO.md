# Plan de Trabajo en Paralelo y Delegación de Responsabilidades
**Proyecto:** RegulaBank Agent — Sistema Multi-Agente GraphRAG Normativo Bancario  
**Contexto:** Hackathon NTT DATA x Sundai (Reto Banca B2: Normativa y Políticas Internas)  
**Objetivo:** Permitir que ambos desarrolladores avancen de forma 100% autónoma y en paralelo hoy mismo, eliminando el riesgo de retrabajo o bloqueos mientras se recibe el documento definitivo de alcance y limitaciones.

---

## 1. Principio de Desacoplamiento: Desarrollo Guiado por Contratos

Para que ambos puedan programar sin esperarse:
* **El puente de unión son contratos de datos (Pydantic)** en `src/regulabank/shared/contracts.py`.
* **Dev 1 (Datos/Búsqueda)** produce objetos `list[Hit]` a partir de una pregunta y un `as_of`.
* **Dev 2 (Agentes/UI)** consume esos objetos `list[Hit]`. Mientras Dev 1 termina, Dev 2 utiliza un `MockRetriever` con datos simulados (JSON).
* **Cero dependencias de APIs en la nube durante el inicio:** Todo corre localmente en CPU con `MODEL_PROVIDER=mock`.

---

## 2. Paso 0 Conjunto (Duración: 20-30 min)
Antes de crear ramas separadas, acuerden y dejen creado el archivo de contratos base:

```python
# src/regulabank/shared/contracts.py
from typing import Literal
from pydantic import BaseModel, Field

class Hit(BaseModel):
    chunk_id: str
    norm_short: str          # Ej: "Res. SBS 11356-2008"
    norm_kind: str           # "law" | "sbs_resolution" | "internal_policy"
    article_no: str          # "12"
    path: str                # "TÍTULO II > CAPÍTULO I > Artículo 12"
    text: str                # Texto plano del artículo/numeral
    quote: str               # Oración más relevante precalculada
    score: float
    valid_from: str          # "YYYY-MM-DD"
    valid_to: str | None     # None si sigue vigente
    is_current: bool

class Claim(BaseModel):
    text: str                # Afirmación generada
    chunk_id: str            # ID del chunk citado
    quote: str               # Cita textual exacta

class Answer(BaseModel):
    claims: list[Claim]
    as_of: str
    abstain: bool = False
    risk_hint: Literal["low", "medium", "high"] = "low"

class Fault(BaseModel):
    kind: Literal[
        "quote_missing", "quote_altered", "foreign_fact", 
        "not_seen", "not_in_force", "fake_consistency"
    ]
    detail: str
```

---

## 3. Asignación de Roles y Tareas

### 🧑‍💻 Desarrollador 1: Data, Graph & Retrieval Engineer
* **Foco:** Ingesta de documentos, segmentación jerárquica, almacenamiento vectorial en LanceDB y PageRank en memoria con SciPy.
* **Rama de trabajo Git:** `feat/data-retrieval`
* **Módulos bajo su responsabilidad:**
  * `src/regulabank/corpus/` (captura, parsing de artículos y chunks)
  * `src/regulabank/search/` (LanceDB, RRF, búsqueda híbrida)
  * `src/regulabank/graphs/` (matriz SciPy para Personalized PageRank)
  * `seeds/` (plantillas de configuración)

#### Lista de Tareas Inmediatas:
1. **Parser de Normas Peruanas y Chunking (`corpus/parse.py` y `corpus/chunk.py`)**:
   * Implementar expresiones regulares para estructurar leyes y resoluciones SBS: *Título $\rightarrow$ Capítulo $\rightarrow$ Artículo $\rightarrow$ Numeral*.
   * Crear la función de corte de chunks (artículos cortos = 1 chunk; artículos largos partidos por numerales sin solapamiento).
   * Generar el identificador determinista: `chunk_id = "c_" + sha1(f"{version_id}:{start}:{end}")[:16]`.
   * Probar el parser con al menos 1 resolución SBS real (ej. Res. SBS 11356-2008 o similar descargada de la web pública de la SBS).
2. **Setup de LanceDB y Búsqueda Vectorial/FTS (`search/index.py`)**:
   * Configurar LanceDB local (`data/views/current/lancedb`).
   * Crear la tabla `chunks` con embedding (Gemma 300M o BGE-M3) e índice Full Text Search (BM25) nativo en español.
   * Aplicar la regla de prefijo contextual al vector: `«{norm_short}, art. {article_no}. » + text`.
3. **Personalized PageRank (PPR) en Memoria (`graphs/ppr.py`)**:
   * Portar desde el prototipo existente la construcción de la matriz rala estocástica (`scipy.sparse.csr_matrix`).
   * Configurar los pesos de aristas (`seeds/params.toml`): `REFERS_TO = 1.0`, `NEXT = 0.5`, `SIMILAR = score`.
   * Implementar la función de cálculo PPR (30 iteraciones de potencia, $\alpha = 0.5$).
4. **Filtro de Vigencia Temporal y Contratos (`search/retrieve.py`)**:
   * Implementar el pipeline: pregunta $\rightarrow$ candidatos densos/BM25 $\rightarrow$ RRF 1 $\rightarrow$ PPR $\rightarrow$ RRF 2 $\rightarrow$ descarte/agrupación por `as_of` (`valid_from <= as_of < valid_to`).
   * Devolver la lista ordenada con los mejores 8 `Hit`.

* **¿Cómo valida su trabajo de forma autónoma?**
  Crea un script de prueba `tests/test_retrieval_standalone.py` que ejecute una pregunta de prueba y valide que devuelve 8 objetos `Hit` válidos con sus textos y vigencia resueltos.

---

### 🧑‍💻 Desarrollador 2: Agentic Orchestration, Verification & Frontend
* **Foco:** Entorno del proyecto, orquestación con LangGraph, verificador determinista por código, proveedor Mock y la interfaz de usuario.
* **Rama de trabajo Git:** `feat/agents-and-ui`
* **Módulos bajo su responsabilidad:**
  * `src/regulabank/agents/` (workflows LangGraph, `answer_graph`, `verify`)
  * `src/regulabank/shared/` (contratos, configuración de entorno)
  * `ui/` (aplicación web Streamlit o React + Vite)
  * `docker-compose.yml` (FalkorDB) y configuración del proyecto (`pyproject.toml`)

#### Lista de Tareas Inmediatas:
1. **Configuración de Proyecto y Contenedores**:
   * Inicializar `pyproject.toml` con `uv` definiendo dependencias clave (`langgraph`, `fastapi`, `pydantic`, `lancedb`, `scipy`, `httpx`, `streamlit` o React).
   * Crear `docker-compose.yml` para levantar la instancia local de FalkorDB:
     ```yaml
     services:
       falkordb:
         image: falkordb/falkordb:v4.22.0
         ports: ["6380:6379", "3010:3000"]
         volumes: ["./data/falkor:/data"]
     ```
2. **Proveedor Abstraído con Modo Simulado (`agents/providers.py`)**:
   * Crear la interfaz `BaseProvider` y la implementación `FakeProvider`.
   * El `FakeProvider` debe retornar salidas estructuradas tipo `Answer` con citas predefinidas para poder probar el flujo completo sin consumir tokens ni requerir credenciales de API.
3. **Nodo Determinista de Verificación (`agents/verify.py`)**:
   * Desarrollar la función de verificación estricta por código (sin LLM):
     * Validar `claim.quote in chunk.text` (normalizando espacios).
     * Validar `claim.chunk_id in state["seen"]`.
     * Validar que números y porcentajes presentes en `claim.text` figuren en `claim.quote` (emitir `foreign_fact` si no están).
     * Validar vigencia de la norma citada respecto al `as_of`.
4. **State Machine en LangGraph (`agents/answer_graph.py`)**:
   * Implementar el grafo: `read -> retrieve (Mock) -> grade -> answer (FakeProvider) -> verify -> risk -> deliver`.
   * Programar el bucle de corrección ante fallas (`verify` rechaza $\rightarrow$ reintento con mensaje de error visible, con tope `MAX_FIXES = 2`).
   * Configurar la regla de Human-in-the-Loop (`interrupt()`) usando `SqliteSaver` cuando el riesgo sea clasificado como `approve`.
5. **Dashboard Mínimo de Usuario (`ui/`)**:
   * Construir la vista con:
     * Caja de entrada de pregunta y selector de fecha `as_of`.
     * Renderizado de la respuesta con citas resaltadas desplegables (`«texto» {norma, art., fecha}`).
     * Pestaña o sección de "Cola de Aprobación Humana" para reanudar casos pausados (`interrupt`).
     * Visualizador del ledger de auditoría (costo en USD, tokens, latencia, resultado de verificación).

* **¿Cómo valida su trabajo de forma autónoma?**
  Crea un script de prueba `tests/test_agents_standalone.py` que alimente a `answer_graph` con 4 `Hit` simulados y verifique que el ciclo de verificación, el retry y la pausa humana funcionen de punta a punta.

---

## 4. Diagrama de Flujo del Trabajo Paralelo

```
=============================================================================
                          PASO 0: CONTRATOS (shared/contracts.py)
=============================================================================
                                     │
                  ┌──────────────────┴──────────────────┐
                  ▼                                     ▼
        [DEV 1: DATA & RETRIEVAL]             [DEV 2: AGENTS & UI]
         (Rama: feat/data-retrieval)           (Rama: feat/agents-and-ui)
                  │                                     │
   1. Parser de artículos y chunking     1. Entorno pyproject.toml y Docker
                  │                                     │
   2. LanceDB (Embeddings + FTS)         2. FakeProvider (Modo Mock offline)
                  │                                     │
   3. Personalized PageRank (SciPy)      3. verify.py (Guardrail determinista)
                  │                                     │
   4. Filtro de vigencia (as_of)         4. answer_graph (LangGraph + HITL)
                  │                                     │
   5. Output validado: list[Hit]         5. UI interactiva (Streamlit/React)
                  │                                     │
                  └──────────────────┬──────────────────┘
                                     ▼
=============================================================================
            FASE DE INTEGRACIÓN (Llegada del Documento de Alcance)
=============================================================================
  1. Dev 1 conecta el retrieve real en el nodo 'retrieve' de LangGraph.
  2. Dev 2 activa el proveedor real (Claude / Azure OpenAI) en lugar de Fake.
  3. Carga del corpus oficial acordado (normas SBS + políticas sintéticas).
  4. Ejecución del benchmark conjunto contra el golden dataset.
=============================================================================
```

---

## 5. Qué Ajustar Cuando Llegue el Documento de Alcance

Al recibir el documento con el alcance detallado y las limitaciones:

| Documento / Decisión que llega | Acción de Dev 1 | Acción de Dev 2 |
|---|---|---|
| **Lista de 8 a 12 normas oficiales** | Agrega los URLs/PDFs al parser y genera el release `gold`. | Ninguna (su flujo no cambia). |
| **Políticas internas y 10 contradicciones** | Carga las políticas sintéticas en el pipeline de chunks. | Configura los casos de prueba para el flujo `conflict_graph`. |
| **Proveedor Cloud (Azure vs. Claude)** | Ninguna. | Coloca las credenciales y el cliente real en `providers.py`. |
| **Reglas de negocio y niveles de riesgo** | Ninguna. | Ajusta la tabla de reglas de riesgo (`seeds/risk_rules.csv`). |
| **UI definitiva (Streamlit vs. React)** | Ninguna. | Pule el diseño visual y la integración con la API FastAPI. |

---

## 6. Reglas de Convivencia Git
1. **Nunca hacer push directo a `main`:** Trabajar en sus ramas asignadas (`feat/data-retrieval` y `feat/agents-and-ui`).
2. **Archivos protegidos:** Si uno necesita modificar `src/regulabank/shared/contracts.py`, debe avisarle al otro antes de commitear.
3. **Commit temprano y frecuente:** Subir cambios al menos 2 veces al día para que el otro pueda ver los avances.
