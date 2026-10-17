import { ChangeDetectionStrategy, Component } from '@angular/core';
import { Flowchart, FlowStep } from '../../shared/flowchart/flowchart';

// Del PDF al grafo: corpus, entidades, embeddings, aristas.
const STEPS: FlowStep[] = [
  { id: 'corpus', phase: 'Corpus', label: 'Corpus', tool: 'seeds/norms.csv · PDF', brief: 'Parquet por documento: de dónde viene (fuente, emisor) y cuándo se publicó.' },
  { id: 'extract', phase: 'Corpus', label: 'Ingesta', tool: 'pymupdf', brief: 'Texto por página con offsets estables. OCR solo si la página es imagen.' },
  { id: 'chunks', phase: 'Corpus', label: 'Chunks', tool: 'regex de estructura', brief: 'Un chunk por artículo con norma, página y cita. Texto literal, sin solape.' },
  { id: 'entities', phase: 'Grafo', label: 'Entidades', tool: 'regex · GLiNER2 large', brief: 'Norma, artículo, plazo, monto y porcentaje por regex; rol, producto y sanción con GLiNER2.' },
  { id: 'embed', phase: 'Grafo', label: 'Embeddings', tool: 'embeddinggemma-300m', brief: 'Un vector por chunk en LanceDB. Corre en RunPod junto con GLiNER2.' },
  { id: 'edges', phase: 'Grafo', label: 'Aristas', tool: 'REFERS_TO · MENTIONS · SIMILAR · NEXT', brief: 'Remisiones por regex, chunk → entidad con peso idf, vecinos por coseno (k = 10), orden del texto.' },
  { id: 'graph', phase: 'Grafo', label: 'Grafo', tool: 'FalkorDB', brief: 'Nodos: chunks y entidades. Se carga desde los Parquet; la matriz para PageRank vive en memoria.' },
];

@Component({
  selector: 'app-flow',
  imports: [Flowchart],
  templateUrl: './flow.html',
  styleUrl: './flow.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class Flow { readonly steps = STEPS; }
