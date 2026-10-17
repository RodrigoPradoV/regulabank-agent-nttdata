# 06 · Los cuatro grafos

Un solo grafo físico en FalkorDB (`regulabank`) con cuatro capas lógicas. La **fuente de verdad son los Parquet**
del release; FalkorDB se carga desde ellos con `MERGE` en lotes de 500 y la carga aborta si los conteos no
coinciden. **La búsqueda no consulta FalkorDB:** en el arranque se arma un grafo en memoria (`scipy.sparse`) desde
los mismos Parquet para el PageRank personalizado (en otro corpus: ~80 mil nodos, 42 ms por consulta). FalkorDB
queda para explorar, explicar y la UI.

```
                 horizon  (contexto: normas, emisores, temas, términos, versiones)
                    ▲
          bridge    │  BELONGS_TO / IMPLEMENTS / CONTRADICTS / SAME_AS
                    │
   focus  ◄───────► chunk ◄───────► lens
 (chunk↔chunk)                   (chunk↔entidad)
```

## `horizon`: contexto normativo

| Nodo | Propiedades |
|---|---|
| `Norm` | `id, short, title, kind, issuer_id, published, valid_from, status (in_force/repealed/partial), url, sha256` |
| `Article` | `id, norm_id, no, path, current_version_id` |
| `Version` | `id, article_id, n, valid_from, valid_to, change_kind, changed_by, text_sha` |
| `Issuer` | `id, name` (SBS, BCRP, Congreso, UIF, SMV) |
| `Topic` | `id, name` (riesgo de crédito, LAFT, provisiones, conducta de mercado, ciberseguridad…) |
| `Term` | `id, name, definition_version_id` (término definido) |

Aristas: `HAS_ARTICLE`, `HAS_VERSION`, `CURRENT` (Article→Version vigente), `MODIFIES`, `REPLACES`, `REPEALS`, `ADDS`,
`IMPLEMENTS`, `ISSUED_BY`, `REGULATES`, `DEFINES`, `REFERS_TO` (Article→Article).

Se construye desde `seeds/norms.csv` + el parser de relaciones A (`05-relations.md`). Es pequeño (cientos de nodos)
y es el que explica la **vigencia** y el **impacto**.

## `focus`: texto fino

| Nodo | Propiedades |
|---|---|
| `Chunk` | `id, norm_id, article_id, version_id, path, start, end, valid_from, valid_to, kind, cluster` |

Aristas: `NEXT {w=0.5}`, `PARENT`, `REFERS_TO {w=1.0}`, `SIMILAR {score}`, `SHARES_TERM {idf}`.

## `lens`: entidades

`(:Lens {id, type, name, key, catalog_id})`, `(:Chunk)-[:MENTIONS {n, starts, ends, score}]->(:Lens)`. Ver
`04-entities.md`.

## `bridge`

```
(:Chunk)-[:BELONGS_TO]->(:Version)-[:OF]->(:Article)-[:IN]->(:Norm)
(:Chunk{policy})-[:IMPLEMENTS]->(:Article)
(:Chunk{policy})-[:CONTRADICTS|STRICTER_THAN]->(:Version)
(:Lens)-[:SAME_AS]->(:Catalog)
(:Lens{defined_term})-[:DEFINED_IN]->(:Version)
```

## Grafo en memoria para PageRank

Matriz no dirigida, columna estocástica, nodos = chunks (`0..n-1`) ∪ entidades lens (`n..`) ∪ artículos
(`n+m..`). Pesos (en `seeds/params.toml`, sección `ppr.edge_weights`, con fuente):

| Arista | Peso | Motivo |
|---|---|---|
| `MENTIONS` | `max(idf(e), 0)` con `idf = log(n/(1+df))` | una entidad común no conecta nada |
| `NEXT` | 0,5 | contexto local |
| `REFERS_TO` | 1,0 | multi salto explícito; es la arista más valiosa de este dominio |
| `SIMILAR` | `score` | rescate semántico |
| `BELONGS_TO` (chunk↔artículo) | 1,0 | las piezas de un mismo artículo se sostienen |
| `MODIFIES`/`REPLACES` (vía artículo) | 0,7 | la versión nueva hereda la relevancia de la vieja |

Parámetros del PageRank: `alpha = 0,5` (reinicio), 30 iteraciones de potencia. Semillas: entidades de la pregunta con
peso `max(idf, 0.1)` y los 10 mejores de la fusión densa con peso `1/rank`.

## Orden de construcción

```
1. release (02)                  norms, articles, versions, chunks           → Parquet + manifest
2. horizon                       seeds/norms.csv + relaciones A               → Parquet (nodes, edges)
3. embeddings (07)               chunks → LanceDB (vector + FTS)
4. lens (04)                     menciones → entidades → curate → Parquet
5. focus                         NEXT/PARENT/REFERS_TO/SIMILAR/SHARES_TERM     → Parquet
6. bridge C (05)                 candidatos → nli → rules → judge → human      → Parquet (pendientes aparte)
7. load                          FalkorDB MERGE por lotes + verificación de 16 conteos
8. golden check (10)             el retrieval sobre el golden no retrocede
```

Cada paso escribe su `manifest.json` (conteos, parámetros efectivos, versión del código, fingerprint). Construir
antes de mirar la colección fue un error en otro proyecto: hubo que rehacer el grafo entero. **Abrir 20 chunks al
azar después del paso 1 antes de seguir.**
