import { ChangeDetectionStrategy, Component, signal } from '@angular/core';

interface Step { id: string; label: string; tool: string; text: string; fields?: string[]; }

// Una sola línea: nueve pasos, de izquierda a derecha. Clic en un paso muestra su descripción debajo.
const STEPS: Step[] = [
  { id: 'corpus', label: 'Corpus', tool: 'seeds/norms.csv + PDF', text: 'Un Parquet con los metadatos de cada documento. El original se guarda tal cual con su sha256.',
    fields: ['norm_id', 'short', 'title', 'kind', 'issuer', 'published', 'valid_from', 'valid_to', 'status', 'topics', 'source_url', 'source_sha256', 'synthetic'] },
  { id: 'extract', label: 'Ingesta', tool: 'pymupdf', text: 'Texto por página con offsets estables. OCR solo si la página es imagen. El texto no se toca después: las citas se verifican contra él.',
    fields: ['norm_id', 'page', 'text'] },
  { id: 'chunks', label: 'Chunks', tool: 'regex de estructura', text: 'Un chunk por artículo (los largos se parten por numeral), sin solape, id por contenido. Cada chunk sabe su versión, vigencia y página.',
    fields: ['chunk_id', 'norm_id', 'article_id', 'article_no', 'path', 'version_id', 'valid_from', 'valid_to', 'change_kind', 'changed_by', 'page_start', 'page_end', 'start', 'end', 'text', 'citation'] },
  { id: 'entities', label: 'Entidades', tool: 'regex + GLiNER2 large', text: 'Lo formulaico por regex (norma, artículo, plazo, monto, porcentaje, término definido); lo abierto con GLiNER2 (rol, producto, sanción, reporte, obligación). Cada mención con start y end verificados.',
    fields: ['mention_id', 'chunk_id', 'entity_id', 'type', 'mention', 'start', 'end', 'score', 'method', 'value'] },
  { id: 'embed', label: 'Embeddings', tool: 'embeddinggemma-300m + BM25', text: 'Un vector por chunk en LanceDB con encabezado «norma, art. N» y un índice léxico en español. El embedding manda; BM25 vota.' },
  { id: 'graph', label: 'Grafo', tool: 'FalkorDB + PageRank', text: 'Aristas NEXT, REFERS_TO, SHARES_ENTITY, SIMILAR, MENTIONS y MODIFIES / REPEALS entre normas. PageRank personalizado en memoria para el multi salto.',
    fields: ['src', 'src_kind', 'dst', 'dst_kind', 'type', 'weight', 'method', 'evidence'] },
  { id: 'conflicts', label: 'Conflictos', tool: 'reglas + xlm-roberta-large-xnli', text: 'Política interna contra norma: si los dos lados tienen valor (12 % contra 10 %, 20 contra 15 días) decide la regla; si no, el NLI. Una persona confirma antes de que cuente.' },
  { id: 'retrieve', label: 'Recuperación', tool: 'denso + BM25 + PPR', text: 'Pregunta y fecha de vigencia → 8 chunks con cita. Las versiones no vigentes a esa fecha pasan a historia, nunca desaparecen.' },
  { id: 'answer', label: 'Respuesta', tool: 'OpenAI + verificador', text: 'El modelo redacta con una cita por afirmación; el código comprueba cita literal, vigencia y números; si el riesgo lo pide, una persona aprueba antes de entregar.' },
];

@Component({
  selector: 'app-flow',
  templateUrl: './flow.html',
  styleUrl: './flow.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class Flow {
  readonly steps = STEPS;
  readonly selected = signal<Step>(STEPS[0]);
}
