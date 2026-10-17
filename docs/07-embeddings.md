# 07 · Transformers: embeddings, léxico, reranker, segmentación, NLI, LLM

Todos son modelos ya entrenados; no se afina nada para la demo. Cada elección lleva su medición de origen y se
re-mide en el golden de este corpus antes de fijarla.

## Tabla de modelos

| Papel | Modelo | Dim | Por qué | Cuándo se re-mide |
|---|---|---|---|---|
| Embedding principal | `google/embeddinggemma-300m` | 768 | en un corpus en español de ~30 mil chunks ganó el denso solo (nDCG@8 0,718) a bge-m3 (0,622) y Qwen3-0.6B (0,585); 300M corre en CPU/MPS a 60-85 ms por consulta | semana 1 sobre 30 preguntas |
| Embedding alterno | `BAAI/bge-m3` | 1024 | denso + sparse + multivector; mejor en textos largos y legales en otros benchmarks | A/B en el golden |
| Léxico | FTS nativo de LanceDB (BM25, `language="Spanish"`, stem, stopwords, ascii folding) | | los números de artículo y siglas (ROS, LAFT) son tokens exactos: BM25 los encuentra, el embedding no siempre | siempre activo como votante débil (0,3) |
| Reranker | `BAAI/bge-reranker-v2-m3` | | +0,06 nDCG en otro corpus sobre los 300 primeros; cuesta 2-4 s en CPU; aquí la latencia importa menos que en voz | activar y medir |
| Segmentación de oraciones | SaT `sat-3l-sm` (wtpsplit) + 2 reglas | | 52/60 fronteras correctas vs spaCy 40 y regex 30 | citas por oración |
| NER abierto | `fastino/gliner2-large-v1` | | etiquetas propias sin entrenar | `04-entities.md` |
| NER clásico | `MMG/xlm-roberta-large-ner-spanish`, BETO NER | | voto | `04-entities.md` |
| NLI (contradicción) | `MoritzLaurer/mDeBERTa-v3-base-xnli-multilingual-nli-2mil7` | | multilingüe, 3 clases; candidatos de contradicción política ↔ norma | 50 pares etiquetados |
| Temas (opcional) | UMAP + HDBSCAN sobre vectores; BERTopic solo pone palabras | | agrupar normas por tema para `REGULATES` | si hay tiempo |
| LLM juez / redactor | Claude (Anthropic) o Azure OpenAI (stack de NTT DATA); proveedor abstraído con un `FakeProvider` guionado | | salida estructurada con Pydantic; el proveedor se elige por variable de entorno | siempre con modo mock |

Prefijos de consulta y documento (sin ellos gemma baja mucho):

```
gemma  doc:   "title: {norm_short}, art. {no} | text: {chunk}"
gemma  query: "task: search result | query: {question}"
bge-m3        sin prefijo
```

Vectores normalizados a norma 1, float32 en LanceDB.

## Qué se embebe

- **Chunks** con encabezado de contexto («Res. SBS 11356-2008, art. 12, num. 12.3. » + texto).
- **Versiones no vigentes también** (con su `valid_to`): se recupera sobre la historia y se decide vigencia después.
- **Definiciones** (`Term`): el texto de la definición, para `definition`.
- **Preguntas del golden** (para el A/B y para el speller).
- Las entidades **no** se embeben: se anclan por vocabulario.

## Tablas LanceDB

```
chunks
  chunk_id, norm_id, norm_short, norm_kind, article_id, article_no, path, version_id,
  valid_from, valid_to, is_current (bool), text, citation, prev_chunk_id, next_chunk_id,
  gemma (FixedSizeList[768]), bge_m3 (FixedSizeList[1024])
  índice FTS sobre text (español)

terms
  term_id, name, norm_id, version_id, definition, gemma

questions_golden
  question_id, text, scenario, as_of, expected_chunk_ids, reserved (bool), gemma
```

## Reglas aprendidas que aplican

- **El embedding manda; lo demás vota.** Sumar BM25 y entidades como listas de igual peso en la RRF **bajó** nDCG de
  0,72 a 0,53 en otro corpus («la vía más débil arrastra al resto»). Pesos: denso 1,0; BM25 0,3; entidades 0,3;
  PageRank 0,3.
- **Señales blandas, no filtros.** Una compuerta por entidad o por fecha bajó el recall (0,731 → 0,626). Aquí la
  única excepción es `as_of`, y se aplica al final, sobre los candidatos, no antes.
- **Encabezado en el vector, no en la cita.** El encabezado sesga el agrupamiento por norma: para temas se resta la
  media por norma antes de UMAP.
- **Speller barato antes de embeber:** fonética + distancia de edición contra el vocabulario del corpus (números de
  norma, siglas): 0,15 ms y arregla «resolucion 11356» o «LAFT» mal escrito.
