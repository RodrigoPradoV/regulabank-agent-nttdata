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
