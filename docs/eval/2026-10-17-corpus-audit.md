# Auditoría de calidad del corpus real (2026-10-17)

Tres agentes de solo lectura leyeron 8 chunks por norma (el primero, el último, los dos más largos y cuatro al azar con semilla 7;
14 para Basilea) y revisaron con código la numeración. Veredicto por norma, sobre `data/graph_v0/chunks.parquet`.

| Norma | Veredicto | Lo que daña una cita |
|---|---|---|
| Res. SBS 11356-2008 | con reservas | numeral 1.4 truncado; notas al pie dentro del texto; chunks que empiezan a media frase |
| Res. SBS 2116-2009 | con reservas | tablas de los anexos aplastadas |
| Res. SBS 2660-2015 | con reservas | 12 chunks solo con título y glifo roto; un chunk de la cola del art. 64 etiquetado como 65 |
| Res. SBS 9075-2012 | con reservas | anexos sin tablas; notas al pie intercaladas |
| Res. SBS 504-2021 | con reservas | referencias cruzadas tomadas por encabezados; notas dentro de listas |
| Res. SBS 272-2017 | con reservas | notas al pie dentro de artículos; jerarquía de disposiciones mal armada |
| Res. SBS 6523-2013 | con reservas | marcadores de nota pegados a números («5-A.17») |
| Res. SBS 789-2018 | con reservas | colisión de numeración entre la resolución y la norma; dos chunks idénticos (arts. 43 y 44) |
| BCBS PSMOR 2021 | con reservas | notas y números de página dentro de párrafos |
| Reglamento UE 2024/1689 | con reservas | guion blando en 229 chunks y marcas ▼M1/▼B (limpiados al cargar) |
| **Res. SBS 6328-2009** | **no listo** | fórmulas destrozadas; cuatro chunks que son celdas de una tabla con `article_no` falso |
| **Res. SBS 3296-2022** | **no listo** | límites del artículo 30 atribuidos al Anexo 16-A; fórmula de depósitos operacionales perdida |
| **Res. SBS 4221-2023** | **no listo** | arts. 44 a 46 fragmentados y mal etiquetados; fórmulas de ratios de liquidez perdidas |
| **D.S. 016-2024-JUS** | **no listo** | siete artículos pegados al anterior (18, 21, 33, 36, 89, 109, 116); no se recuperan por número |
| **D.Leg. 1531-2022** | **no listo** | `article_no` mezcla los artículos del decreto con los de la Ley 26702 que cita |
| **Basel Framework** | **no listo** | ligadura ﬀ en el 71 % de los chunks (limpiada al cargar); fórmulas y tablas perdidas; un NUL (limpiado) |
| **Recomendaciones GAFI 2025** | **no listo** | secciones con etiqueta equivocada (R.1 y R.8 cruzadas); chunks que empiezan a media frase |

Cruce: las notas al pie, las tablas y las fórmulas se pierden o se mezclan con el texto en casi todas las normas.
El texto corrido de los artículos sale entero; lo que no se debe citar sin mirar el original son cifras de anexos, fórmulas y tablas.

Limpiado al cargar (sin tocar el parquet): ligaduras U+FB00 a U+FB06, guion blando U+00AD y NUL (`retrieval/search.py: clean_text`).
No limpiado: ligaduras partidas con espacio («fi n», 112 de 150 chunks del D.S. 016-2024-JUS) y todo lo demás de esta tabla;
requiere corregir la extracción del corpus, que es del equipo.
