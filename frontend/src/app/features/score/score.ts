import { ChangeDetectionStrategy, Component } from '@angular/core';
import { Flowchart, FlowStep } from '../../shared/flowchart/flowchart';

// De la pregunta a la respuesta: un solo puntaje (PageRank personalizado, HippoRAG 2) y un auditor que verifica.
const STEPS: FlowStep[] = [
  { id: 'question', phase: 'Pregunta', label: 'Pregunta', tool: 'texto · as_of', brief: 'La consulta del analista y la fecha contra la que se decide vigencia (hoy por defecto).' },
  { id: 'seeds', phase: 'Pregunta', label: 'Semillas', tool: 'regex · coseno', brief: 'Entidades de la pregunta con peso idf, y los 10 chunks más parecidos con peso 1/rango.' },
  { id: 'ppr', phase: 'Puntuación', label: 'PageRank personalizado', tool: 'alpha 0,5 · 30 iteraciones', brief: 'Camina chunk → entidad → chunk y por REFERS_TO, NEXT y SIMILAR. Un solo puntaje por chunk.' },
  { id: 'validity', phase: 'Puntuación', label: 'Vigencia', tool: 'código', brief: 'Lo no vigente a as_of pasa a historia del artículo; nunca desaparece. Tope de 3 chunks por norma.' },
  { id: 'top', phase: 'Puntuación', label: 'Top 8', tool: 'con cita', brief: 'Ocho chunks con norma, artículo, página y texto literal. Sin evidencia suficiente, se abstiene.' },
  { id: 'answer', phase: 'Respuesta', label: 'Redacta', tool: 'OpenAI · salida estructurada', brief: 'Una afirmación = una cita literal de un chunk visto. Nada fuera de la evidencia.' },
  { id: 'auditor', phase: 'Respuesta', label: 'Agente auditor', tool: 'LangGraph · código · NLI', brief: 'Cita literal, vigencia, números y consistencia. Si falla, el redactor corrige (máximo 2).' },
  { id: 'human', phase: 'Respuesta', label: 'Persona', tool: 'interrupt', brief: 'Entra solo cuando el riesgo lo pide: acepta, edita o rechaza. Todo queda en el ledger.' },
];

@Component({
  selector: 'app-score',
  imports: [Flowchart],
  templateUrl: './score.html',
  styleUrl: '../flow/flow.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class Score { readonly steps = STEPS; }
