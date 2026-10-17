# regulabank: blueprint del GraphRAG normativo

Misión en una línea: **dada una pregunta de un analista de banca, devolver la respuesta correcta y vigente, con la cita
literal del artículo o de la política interna que la sostiene, y escalar a una persona cuando el riesgo lo pide.**

Reto del hack (NTT DATA x Sundai, Reto Banca, punto 2): «Normativa y políticas internas: encontrar la información
correcta y vigente entre múltiples documentos puede ser lento y generar interpretaciones inconsistentes». Las tres
palabras que importan son *correcta* (cita verificada), *vigente* (versión y fecha) y *consistente* (misma respuesta
ante la misma pregunta, contradicciones detectadas).

## Cómo leer esta carpeta

Un archivo por área. Se leen en orden la primera vez; después cada uno se consulta solo.

| Archivo | Área | Qué decide |
|---|---|---|
| `01-problem.md` | Problema | usuarios, preguntas tipo, criterio de éxito, qué NO hacemos |
| `02-corpus.md` | Corpus | fuentes (SBS, BCRP, leyes, políticas internas), captura, identidad, versiones y vigencia |
| `03-chunking.md` | Unidades | norma → título → capítulo → artículo → numeral → literal; ids y procedencia |
| `04-entities.md` | Entidades | grafo `lens`: etiquetas, modelos, canonicalización, medición |
| `05-relations.md` | Relaciones | modifica / deroga / sustituye / remite / implementa / contradice; extracción y verificación |
| `06-graphs.md` | Grafos | los cuatro grafos (`focus`, `horizon`, `lens`, `bridge`) y su esquema |
| `07-embeddings.md` | Transformers | embeddings, léxico, reranker, segmentador, NLI; tablas LanceDB |
| `08-retrieval.md` | Recuperación | híbrido + PageRank personalizado + vigencia + citas verificadas |
| `09-agents.md` | Agentes | LangGraph: grafo de respuesta, juez, verificador, triage de riesgo, HITL, presupuesto |
| `10-evaluation.md` | Medición | golden, métricas, fingerprint, grade, autonomía |
| `11-demo.md` | Hack | plan por sprint, qué mostrar, impacto, repo |
| `12-infra.md` | Infraestructura | FalkorDB, LanceDB, entorno, proveedores LLM, costos |

## Principios que atraviesan todo

1. **La base es determinista; el modelo decide solo lo que el código no puede.** Las reglas (vigencia, jerarquía,
   referencias cruzadas) van en código y se prueban sin modelo. El LLM lee evidencia congelada con herramientas de
   solo lectura y devuelve salida estructurada; nunca escribe texto libre que se guarde como dato.
2. **El grafo organiza; el embedding puntúa.** El grafo sirve para rescatar lo que el embedding no ve (multi salto,
   referencias cruzadas, versiones) y para explicar; el orden final lo da la similitud y el reranker. Nunca se filtra
   por grafo: las señales del grafo suman, no descartan.
3. **Toda afirmación lleva cita literal verificada por código** (`quote in chunk.text`) y el id del chunk citado debe
   estar entre los que la corrida vio (`seen`). Si no, se rechaza y se reintenta con el error a la vista; a la tercera,
   `rejected`, nunca un valor por defecto.
4. **Vigencia como dato, no como prompt.** Cada artículo tiene versiones con `valid_from` / `valid_to` y aristas
   `MODIFIES` / `REPEALS` / `REPLACES`. La pregunta lleva `as_of` (hoy por defecto). Se recupera sobre todas las
   versiones y se responde con la vigente, señalando la historia.
5. **Humano en el bucle solo en lo irreversible o de alto riesgo**, con `interrupt` y cola; el resto corre solo.
6. **Lo que no se mide no se gestiona.** Golden de preguntas desde el día uno; cada cambio entra solo si mejora sin
   empeorar otro tipo de pregunta.
7. **Idioma:** código, identificadores, valores de datos y nombres de archivo en inglés; prosa, docstrings, prompts y
   mensajes en español.

## Vocabulario fijo (usar tal cual)

| Término | Qué es |
|---|---|
| `norm` | instrumento normativo completo (ley, resolución, circular, política interna) |
| `article` | artículo o unidad equivalente; tiene versiones |
| `chunk` | unidad de recuperación: artículo o parte de artículo, con rango de caracteres sobre el original |
| `version` | texto de un `article` entre dos fechas de vigencia |
| `as_of` | fecha contra la que se decide vigencia (en la pregunta) |
| `focus` | grafo fino: chunk ↔ chunk (estructura, referencias, similitud) |
| `horizon` | grafo de contexto: normas, emisores, temas, términos definidos, historia de versiones |
| `lens` | grafo de entidades por chunk (plazos, montos, umbrales, áreas, productos, riesgos) |
| `bridge` | aristas que unen los tres: chunk → artículo → norma; política → norma; entidad → catálogo |
| `seen` | ids de chunks que la corrida leyó; solo se cita lo que está ahí |
| `judge` | nodo LLM que califica evidencia o propone; nunca aplica |
| `verify` | nodo de código que acepta o rechaza cada propuesta contra el original |
| `golden` | conjunto de preguntas con sus chunks correctos, revisado por persona; una parte queda reservada |
| `ledger` | registro fechado de cada llamada, decisión y costo; se agrega, nunca se reescribe |
| `quota_deferred` | caso que espera por límite de cupo; no es error ni strike |
