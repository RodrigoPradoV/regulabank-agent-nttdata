# 08 · Recuperación: de la pregunta a los 8 chunks con cita

Todo el camino caliente es código determinista más dos modelos chicos (embedding y, si se activa, reranker). El LLM
entra después, en `09-agents.md`. Parámetros con procedencia en `seeds/params.toml`.

## Pipeline

```
question, as_of ─► speller ─► read ─► understand ─► candidates ─► fuse ─► ppr ─► fuse2 ─► dedup ─► validity ─► rerank ─► contracts ─► top_k
```

| Paso | Qué hace | Salida |
|---|---|---|
| `speller` | fonética + distancia de edición contra el vocabulario del corpus (números de norma, siglas, términos) | pregunta corregida; log del cambio |
| `read` | escenario (`lookup`, `definition`, `threshold`, `procedure`, `validity`, `crossref`, `policy_vs_norm`, `impact`, `negative`), normas nombradas (regex `norm_ref`), fechas (`as_of` explícito o hoy) | `Query{scenario, norms, as_of, dates}` |
| `understand` | n-gramas de hasta 5 palabras normalizados contra el vocabulario de `lens`; un n-grama ancla solo si tiene alguna palabra fuera de las stop medidas en el corpus (df > 5 %); gana el más largo | entidades ordenadas por IDF |
| `candidates` | listas de `CAND_K = 50`: `dense` (gemma, LanceDB), `bm25` (FTS), `entities` (suma de IDF de menciones), `norm` (denso con `where norm_id in …` si la pregunta nombra normas), `terms` (tabla de definiciones, solo en `definition`) | listas rankeadas |
| `fuse` | RRF ponderada `w/(60+rank)`: dense 1,0 · bm25 0,3 · entities 0,3 · norm 0,5 · terms 1,0 | `FUSED_K = 100` |
| `ppr` | PageRank personalizado (`06-graphs.md`) sembrado con entidades (`max(idf,0.1)`) y los 10 mejores de `fuse` (`1/rank`); `alpha 0,5`, 30 iteraciones | ranking por grafo |
| `fuse2` | segunda RRF con `ppr` como lista (peso 0,3) y hasta `PPR_NEW = 30` chunks que solo trajo el grafo (aquí entran los `REFERS_TO` de segundo salto) | candidatos |
| `dedup` | primeros 300 caracteres normalizados; versiones de un mismo artículo se agrupan (`article_id`) y se conserva la vigente a `as_of` como representante, las otras como `history` | candidatos sin duplicados |
| `validity` | **única regla dura:** si `as_of` cae fuera de `[valid_from, valid_to)` el chunk pasa a `history` del representante vigente; nunca desaparece: se muestra como «modificado por … desde …» | vigentes + historia |
| `rerank` | `bge-reranker-v2-m3` sobre `RERANK_K = 30` (activado por flag; medir latencia y nDCG) | reordenado |
| `contracts` | lugares asegurados por escenario (abajo) y tope `PER_NORM = 3` chunks por norma, salvo `procedure` | `TOP_K = 8` |

## Contratos por escenario (lugares asegurados de los 8)

| Escenario | Asegura | Regla |
|---|---|---|
| `lookup` | 1 chunk de la norma nombrada si hay | el mejor de esa norma solo si está en el 1 % más parecido **dentro de la norma** (piso por grupo, no global) |
| `definition` | 1 de `terms` | la definición antes que el uso |
| `threshold` | 1 chunk con `amount`/`percentage`/`deadline` extraído | el número debe existir como entidad estructurada |
| `procedure` | hasta 5 consecutivos por `NEXT` del mejor artículo | orden del texto, no del score |
| `validity` | la versión vigente **y** la anterior del artículo pedido | ambas con fechas |
| `crossref` | el destino del `REFERS_TO` del mejor chunk | segundo salto explícito |
| `policy_vs_norm` | 1 chunk de política + 1 de norma unidos por `IMPLEMENTS`/`CONTRADICTS` | si no hay arista, cae a híbrido |
| `impact` | artículos `MODIFIES` de la norma nombrada + políticas con `IMPLEMENTS` hacia ellos | consulta de grafo pura |
| `negative` | nada asegurado | ver abstención |

## Abstención (dos etapas)

1. **Umbral orientado a recall:** hay evidencia si el promedio de similitud de los 6 mejores supera `evidence.mean6`
   (calibrado como percentil 5 de los positivos del golden; en otro corpus 0,354 con AUC 0,978).
2. **Confirmación con LLM solo si el paso 1 dudó** (entre `rescue_floor` y `mean6`): el juez revisa los 4 mejores y
   confirma o abstiene (`09-agents.md`). Sin evidencia confirmada no hay síntesis: «no encontré una norma que fije
   eso; lo más cercano es …».

## Citas verificadas (en código, nunca en el modelo)

- Para cada chunk del top, `own_quote`: la oración (o ventana de 1-2 oraciones ≤ 320 caracteres) con mayor coseno
  a la pregunta; si existe la capa de oraciones se usa; si no, ventana por regex.
- Verificación: `quote in version.text` tras normalizar espacios; `chunk_id in seen`; números de la respuesta
  presentes en el texto citado (`foreign_fact` si no).
- Formato de cita: `«texto literal» {Res. SBS N.° 11356-2008 | art. 12 | num. 12.3 | vigente desde 2019-04-01}`.

## Salida

```python
Hit(chunk_id, norm_short, article_no, path, citation, text, quote, score, sources: dict[str, int],
    valid_from, valid_to, is_current, history: list[HistoryItem], refers_to: list[str], entities: list[str])
Trace(lists, fused, ppr_new, dedup, validity_moved, timings_ms, params_hash)
```

La traza se guarda con cada consulta: es la base del ledger y de la explicación en la UI («por qué este artículo»).

## Latencias de referencia (otro corpus, 30 mil chunks, Mac en CPU)

| Etapa | ms |
|---|---|
| embeber la pregunta | 60-85 |
| denso | 18-45 |
| BM25 | 3 |
| PageRank | 42 |
| reranker (30) | 2 000-4 600 |
| total sin reranker | 57-80 |
