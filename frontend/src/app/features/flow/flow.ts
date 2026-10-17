import { ChangeDetectionStrategy, Component, ElementRef, afterNextRender, viewChild } from '@angular/core';
import * as d3 from 'd3';

interface Step { id: string; label: string; tool: string; brief: string; }

// Diagrama de flujo: una caja por paso con título, herramienta y descripción corta adentro; sin colores ni clics.
const STEPS: Step[] = [
  { id: 'corpus', label: 'Corpus', tool: 'seeds/norms.csv + PDF', brief: 'Parquet con metadatos: norma, emisor, publicación, vigencia, estado, sha256.' },
  { id: 'extract', label: 'Ingesta', tool: 'pymupdf', brief: 'Texto por página con offsets estables; OCR solo si la página es imagen.' },
  { id: 'chunks', label: 'Chunks', tool: 'regex de estructura', brief: 'Un chunk por artículo con versión, vigencia, página y cita; sin solape.' },
  { id: 'entities', label: 'Entidades', tool: 'regex + GLiNER2 large', brief: 'Norma, artículo, plazo, monto y % por regex; rol, producto y sanción con GLiNER2.' },
  { id: 'embed', label: 'Embeddings', tool: 'embeddinggemma-300m + BM25', brief: 'Un vector por chunk en LanceDB más índice léxico en español.' },
  { id: 'graph', label: 'Grafo', tool: 'FalkorDB + PageRank', brief: 'NEXT, REFERS_TO, SHARES_ENTITY, SIMILAR, MENTIONS, MODIFIES; PPR en memoria.' },
  { id: 'conflicts', label: 'Conflictos', tool: 'reglas + xlm-roberta-large-xnli', brief: 'Política contra norma: regla si hay valores, NLI si no; una persona confirma.' },
  { id: 'retrieve', label: 'Recuperación', tool: 'denso + BM25 + PPR', brief: 'Pregunta y fecha → 8 chunks con cita; lo no vigente pasa a historia.' },
  { id: 'answer', label: 'Respuesta', tool: 'OpenAI + verificador', brief: 'Una cita por afirmación; el código verifica; persona aprueba si hay riesgo.' },
];

const NW = 400, NH = 92, GAP = 28, X0 = 60, TOP = 6, WRAP = 52;

@Component({
  selector: 'app-flow',
  templateUrl: './flow.html',
  styleUrl: './flow.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class Flow {
  readonly height = TOP + STEPS.length * NH + (STEPS.length - 1) * GAP + 8;
  private readonly svgRef = viewChild.required<ElementRef<SVGSVGElement>>('svg');

  constructor() { afterNextRender(() => this.draw()); }

  private wrap(text: string, width: number): string[] {
    const out: string[] = []; let cur = '';
    for (const w of text.split(' ')) { if ((cur + ' ' + w).trim().length > width && cur) { out.push(cur); cur = w; } else { cur = (cur + ' ' + w).trim(); } }
    if (cur) { out.push(cur); }
    return out.slice(0, 2);
  }

  private draw(): void {
    const svg = d3.select(this.svgRef().nativeElement);
    svg.selectAll('*').remove();
    const y = (i: number) => TOP + i * (NH + GAP);
    svg.append('defs').append('marker').attr('id', 'arrow').attr('viewBox', '0 0 10 10').attr('refX', 9).attr('refY', 5).attr('markerWidth', 7).attr('markerHeight', 7).attr('orient', 'auto')
      .append('path').attr('d', 'M0,0 L10,5 L0,10 z').attr('fill', '#a1a1a6');

    svg.append('g').selectAll('line').data(STEPS.slice(1)).join('line')
      .attr('x1', X0 + NW / 2).attr('x2', X0 + NW / 2).attr('y1', (_s, i) => y(i) + NH).attr('y2', (_s, i) => y(i) + NH)
      .attr('stroke', '#a1a1a6').attr('stroke-width', 1.5).attr('marker-end', 'url(#arrow)')
      .transition().duration(360).delay((_s, i) => 80 * i + 180).ease(d3.easeCubicOut).attr('y2', (_s, i) => y(i + 1) - 2);

    const node = svg.append('g').selectAll('g').data(STEPS).join('g')
      .attr('class', 'node').attr('transform', (_s, i) => `translate(${X0},${y(i)})`).attr('opacity', 0);
    node.transition().duration(400).delay((_s, i) => 80 * i).attr('opacity', 1);
    node.append('rect').attr('class', 'box').attr('width', NW).attr('height', NH).attr('rx', 18).attr('fill', '#fff').attr('stroke', 'rgba(0,0,0,0.08)');
    node.append('text').attr('class', 'num').attr('x', 22).attr('y', 30).attr('fill', '#a1a1a6').text((_s, i) => String(i + 1).padStart(2, '0'));
    node.append('text').attr('class', 'title').attr('x', 50).attr('y', 30).text(s => s.label);
    node.append('text').attr('class', 'tool').attr('x', NW - 22).attr('y', 30).attr('text-anchor', 'end').attr('fill', '#86868b').text(s => s.tool);
    node.append('text').attr('class', 'brief').attr('x', 50).attr('y', 54).attr('fill', '#515154')
      .each((s, i, els) => { const lines = this.wrap(s.brief, WRAP); d3.select(els[i]).selectAll('tspan').data(lines).join('tspan').attr('x', 50).attr('dy', (_l, j) => j === 0 ? 0 : 17).text(l => l); });
  }
}
