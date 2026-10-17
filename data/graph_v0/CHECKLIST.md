# Checklist del grafo v0 (medido sobre los archivos de esta carpeta)

| Pieza | Estado | Dato |
|---|---|---|
| Chunks | listo | 2.976 en 17 normas, contrato de 25 columnas |
| Artículos y normas | listo | 1.191 y 17 |
| Entidades | listo | 3.000 en 14 tipos |
| Menciones | listo | 47.454 (GLiNER2 42.643, gazetteer 10.774, regex 6.346 tras solapes) |
| Tramo literal `text[start:end] == mention` | 0 fallas | verificado en las 47.454 |
| NEXT | listo | 2.959 (17 chunks sin salida: el último de cada norma) |
| REFERS_TO | listo | 1.083 resueltas, 290 sin resolver (se listan en `graph_manifest.json`) |
| MENTIONS | listo | 20.942 con peso idf |
| SIMILAR | listo | 22.229, coseno gemma, kNN k = 10 sin el mismo artículo |
| Invariantes de aristas | cumple | extremos existen, sin bucles, peso > 0, una fila por (src, dst, tipo) |
| Vectores | listo | embeddinggemma-300m, 768 dimensiones, 2.976 |
| FalkorDB | cargado | conteos iguales al parquet (el cargador verifica y falla si difieren) |
| Chunks sin ninguna mención | 57 | para revisar |
| Calidad de `product` | sin revisar | 24.337 menciones y 1.263 entidades: es el 51 % de todo; abrir muestras antes de confiar |
| NLI RoBERTa | pendiente | pares preparados, modelo sin correr; sale como tabla, no como aristas |

## NLI (XLM-R large XNLI, RunPod RTX 4090, 272 s, 28.915 pares de oraciones, 0 errores)

| Relación | Pares | % |
|---|---|---|
| neutral | 24.319 | 84,1 |
| entailment | 2.523 | 8,7 |
| contradiction | 2.073 | 7,2 |

Sin validar. Con p ≥ 0,9 hay 916 contradicciones y con p ≥ 0,99 hay 278. Las de mayor puntaje mezclan temas
distintos («las OSFL no son sujetos obligados» contra cláusulas de debida diligencia), así que el 7,2 % está
inflado. Se mide contra `nli/etiquetar_pares.csv` (200 pares repartidos por cluster HDBSCAN) antes de usarlo.
Es una tabla (`nli/conflicts.parquet`), no aristas: el grafo conserva sus 4. 2.498 de 2.976 chunks tienen algún par.

## Fecha de publicación (`published`)

| Dato | Estado |
|---|---|
| Filas con fecha | 2.947 de 2.976 |
| Normas con fecha | 16 de 17, con evidencia por norma en `backend/seeds/published.csv` |
| Sin fecha | Res. SBS 2116-2009 (29 chunks): solo se halló la emisión, 2009-04-02 |
| Fecha de día confirmada en El Peruano o fuente primaria | 9 normas |
| Fuente secundaria (vLex, BCRP) | 5 normas: 9075-2012, 3296-2022, 272-2017, 789-2018, DS 016-2024-JUS |
| Confianza baja | Res. 6328-2009 (20-06-2009, puede ser el portal SBS) |
| Precisión menor al día | FATF `2025-12` (mes); Basel Framework `2026-10-17` (fecha de edición del PDF, el BIS no da una sola) |

`backend/scripts/apply_published.py` aplica el CSV a cualquier `corpus_chunks.parquet`; `data/graph_v0/chunks.parquet`
ya lo trae aplicado. El parquet de `main` (`data/corpus_v0`) no se tocó.
