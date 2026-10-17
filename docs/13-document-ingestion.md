# Ingesta estructural para GraphRAG

## Decisión

La estructura primaria de una norma no se extrae con un transformer. Se obtiene de marcadores PDF,
índices y reglas deterministas para conservar trazabilidad y evitar que un modelo invente niveles o
relaciones. Los modelos se incorporan después, donde aportan semántica.

## Flujo propuesto

1. **Bronze**: conservar el archivo original, URL, hash, fecha de captura y licencia.
2. **Silver-text**: extraer texto por página; aplicar OCR solo cuando no exista capa de texto y guardar
   coordenadas, confianza y evidencia visual.
3. **Silver-structure**: construir `norma → título → capítulo → artículo/sección → numeral`
   mediante bookmarks, índice y expresiones regulares. El índice funciona como mapa y control de
   cobertura, no como única fuente de verdad.
4. **Silver-relations**: detectar citas y verbos jurídicos (`modifica`, `deroga`, `incorpora`,
   `reglamenta`, `sustituye`). Las detecciones automáticas quedan como `candidate`; una relación solo
   pasa a `accepted` cuando hay evidencia inequívoca o revisión.
5. **Gold**: crear chunks por artículo o sección, preservando `norm_id`, ancestros, páginas, vigencia,
   autoridad y hash. No mezclar artículos diferentes en un chunk.
6. **Indexación**: cargar aristas aceptadas al grafo e indexar los chunks con embeddings para búsqueda
   híbrida. Mantener los candidatos fuera de las conclusiones jurídicas hasta validarlos.

## Uso de modelos

| Tarea | Método inicial | Transformer |
|---|---|---|
| Jerarquía y numeración | Reglas + bookmarks + índice | No |
| OCR y layout | Motor OCR con coordenadas | Opcional, según motor |
| Citas jurídicas explícitas | Regex y catálogo normalizado | No |
| Relación ambigua | Clasificador con evidencia + revisión | Sí, después del baseline |
| Entidades abiertas | `fastino/gliner2-large-v1` | Sí; obligatorio según `04-entities.md` |
| Recuperación semántica | Embeddings multilingües | Sí |
| Contradicción política-norma | NLI y verificación humana | Sí, en una fase posterior |

## Esquema mínimo

Los nodos estructurales deben guardar `node_id`, `norm_id`, `node_type`, `number`, `title`,
`parent_id`, `ordinal`, `page_start`, `page_end`, `source_path`, `method` y `confidence`.

Las aristas jurídicas deben guardar `source_id`, `target_id`, `edge_type`, `evidence`, `page`,
`method`, `confidence`, `resolved` y `review_status`. Las referencias a normas aún no catalogadas se
mantienen como nodos externos; no se descartan ni se resuelven por suposición.

## Gates de calidad

- Bloquear de `gold` documentos sin texto hasta completar OCR y control visual.
- Bloquear texto comercial no licenciado.
- Exigir IDs únicos y cero aristas colgantes.
- Comparar artículos detectados contra el índice o una muestra manual estratificada.
- Exigir evidencia de página para toda relación automática.
- Versionar parser, fuente, reglas y fecha de extracción.

## Estado de esta corrida

Los artefactos se generan en `data/graph_ingest_v0`. Tres leyes escaneadas permanecen en
`QUARANTINE_OCR`; las dos normas ISO permanecen en `BLOCKED_NO_PUBLIC_TEXT`. Las demás fuentes
cuentan con una primera jerarquía auditable. Las relaciones regex están separadas de las relaciones
validadas para impedir que una coincidencia textual se trate como hecho jurídico.
