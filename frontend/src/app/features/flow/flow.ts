import { ChangeDetectionStrategy, Component } from '@angular/core';
import { Flowchart, FlowStep } from '../../shared/flowchart/flowchart';

// Un solo flujo, de la norma a la respuesta. Un color por fase; el agente va relleno: ahí es donde decide el modelo.
const BLUE = '#007aff', GREEN = '#34c759', ORANGE = '#ff9500', INK = '#1d1d1f';
const STEPS: FlowStep[] = [
  { id: 'corpus', phase: 'Corpus', accent: BLUE, label: 'Normas y chunks', tool: 'PyMuPDF · regex de estructura', brief: '17 normas reales en 2.976 chunks por artículo, con página, vigencia y fecha de publicación.' },
  { id: 'entities', phase: 'Grafo', accent: GREEN, label: 'Entidades', tool: 'regex · gazetteer · GLiNER2', brief: 'Normas, plazos y montos por regex; roles, productos y sanciones con GLiNER2. 3.000 entidades.' },
  { id: 'embed', phase: 'Grafo', accent: GREEN, label: 'Vectores', tool: 'text-embedding-3-small · LanceDB', brief: 'Un vector por chunk; coseno y texto completo en LanceDB. Empata con gemma en el golden y el servidor no carga modelos.' },
  { id: 'edges', phase: 'Grafo', accent: GREEN, label: 'Aristas', tool: 'NEXT · REFERS_TO · MENTIONS · SIMILAR · CONTRADICTS', brief: '47.992 aristas en 5 tipos entre chunks y entidades. FalkorDB guarda el grafo para explorarlo y explicar.' },
  { id: 'nli', phase: 'Grafo', accent: GREEN, label: 'Conflictos', tool: 'RoBERTa XNLI · RunPod', brief: '28.915 pares de oraciones entre normas; 861 contradicciones con p ≥ 0,9 entran al grafo como CONTRADICTS.' },
  { id: 'plan', phase: 'Agente', accent: ORANGE, filled: true, label: 'Plan', tool: 'gpt-5-mini', brief: 'Se asigna complejidad de 1 a 3, y elige la estrategia (directa, reformular, comparar, varios saltos) y el modelo.' },
  { id: 'tools', phase: 'Agente', accent: ORANGE, filled: true, label: 'Herramientas', tool: 'search · read · refers_to · neighbors · conflicts', brief: 'Busca por significado, lee el texto completo, sigue remisiones y contradicciones. Hasta 8 consultas.' },
  { id: 'verify', phase: 'Agente', accent: ORANGE, filled: true, label: 'Verificación', tool: 'código · distancia · gpt-5 si falla', brief: 'Cada cita existe y cada cifra está en lo citado; si la evidencia queda a más de 0,372 de distancia, se abstiene.' },
  { id: 'human', phase: 'Agente', accent: ORANGE, filled: true, label: 'Persona', tool: 'tabla de riesgo', brief: 'Política contra norma e impacto quedan pendientes de aprobación humana. Todo va al ledger.' },
  { id: 'answer', phase: 'Respuesta', accent: INK, label: 'Respuesta', tool: 'texto con citas [n] · SSE', brief: 'Texto natural con citas numeradas; el chat muestra cada paso del agente mientras trabaja.' },
];

// Quién decide en cada nodo del agente (docs/09): el modelo solo entra donde hace falta; lo demás es código.
const DECIDES = [
  { node: 'Plan', who: 'modelo', what: 'complejidad, estrategia, modelo y presupuesto de consultas' },
  { node: 'Herramientas', who: 'modelo + código', what: 'el modelo elige qué buscar; el código ejecuta, de solo lectura' },
  { node: 'Verificación', who: 'código', what: 'cita literal, cifras, vigencia; hasta 2 correcciones' },
  { node: 'Escalar', who: 'modelo o código', what: 'gpt-5-mini → gpt-5 si el modelo lo pide o falla la verificación' },
  { node: 'Riesgo', who: 'tabla', what: 'seeds/risk_rules.csv; una versión no vigente exige persona' },
];

const METRICS = [
  { k: '67,5 %', v: 'respuestas confiables en 40 preguntas reales (IC 95 %: 52,5 a 82,5)' },
  { k: '96,9 %', v: 'citas literales verificadas en lo respondido' },
  { k: '81,2 %', v: 'respuestas respaldadas por el juez (Claude, otra familia)' },
  { k: '6 de 6', v: 'preguntas fuera del corpus abstenidas, verificado en vivo (la regla de distancia es el respaldo)' },
  { k: '20 %', v: 'de lo respondido agrega algo que no está en la cita: lo que falta mejorar' },
  { k: '0,31 USD', v: 'las 40 preguntas; p50 24 s por respuesta' },
  { k: '0,582', v: 'nDCG@8 del retrieval (0,623 en el golden reservado)' },
  { k: '47.992', v: 'aristas en 5 tipos sobre 2.976 chunks de 17 normas' },
];

@Component({
  selector: 'app-flow',
  imports: [Flowchart],
  templateUrl: './flow.html',
  styleUrl: './flow.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class Flow { readonly steps = STEPS; readonly decides = DECIDES; readonly metrics = METRICS; }
