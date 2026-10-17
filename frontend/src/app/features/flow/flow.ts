import { ChangeDetectionStrategy, Component, ElementRef, afterNextRender, viewChild } from '@angular/core';
import * as d3 from 'd3';

interface Step { id: string; phase: string; label: string; tool: string; brief: string; }

// Diagrama de flujo en tres fases. Jerarquía: fase (rótulo) › título › herramienta › descripción.
const STEPS: Step[] = [
  { id: 'corpus', phase: 'Corpus', label: 'Corpus', tool: 'seeds/norms.csv · PDF', brief: 'Parquet por documento: de dónde viene (fuente, emisor) y cuándo se publicó.' },
  { id: 'extract', phase: 'Corpus', label: 'Ingesta', tool: 'pymupdf', brief: 'Texto por página con offsets estables. OCR solo si la página es imagen.' },
  { id: 'chunks', phase: 'Corpus', label: 'Chunks', tool: 'regex de estructura', brief: 'Un chunk por artículo con versión, vigencia, página y cita. Sin solape.' },
  { id: 'entities', phase: 'Grafo', label: 'Entidades', tool: 'regex · GLiNER2 large', brief: 'Norma, artículo, plazo, monto y porcentaje por regex; rol, producto y sanción con GLiNER2.' },
  { id: 'embed', phase: 'Grafo', label: 'Embeddings', tool: 'embeddinggemma-300m · BM25', brief: 'Un vector por chunk en LanceDB más un índice léxico en español.' },
  { id: 'graph', phase: 'Grafo', label: 'Grafo', tool: 'FalkorDB · PageRank', brief: 'Aristas NEXT, REFERS_TO, SHARES_ENTITY, SIMILAR, MENTIONS y MODIFIES. PageRank en memoria.' },
  { id: 'conflicts', phase: 'Consulta', label: 'Conflictos', tool: 'reglas · xlm-roberta-large-xnli', brief: 'Política contra norma: decide la regla si hay valores, el NLI si no. Una persona confirma.' },
  { id: 'retrieve', phase: 'Consulta', label: 'Recuperación', tool: 'denso · BM25 · PPR', brief: 'Pregunta y fecha → ocho chunks con cita. Lo no vigente pasa a historia.' },
  { id: 'answer', phase: 'Consulta', label: 'Respuesta', tool: 'OpenAI · verificador', brief: 'Una cita por afirmación. El código verifica; una persona aprueba si hay riesgo.' },
];

const NW = 440, NH = 112, GAP = 26, PHASE = 44, X0 = 40, TOP = 4, WRAP = 58;

@Component({
  selector: 'app-flow',
  templateUrl: './flow.html',
  styleUrl: './flow.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class Flow {
  private readonly layout = (() => {
    let y = TOP; let last = ''; const rows: { s: Step; y: number; phaseY: number | null }[] = [];
    for (const s of STEPS) { let phaseY: number | null = null; if (s.phase !== last) { phaseY = y; y += PHASE; last = s.phase; } rows.push({ s, y, phaseY }); y += NH + GAP; }
    return { rows, height: y - GAP + 6 };
  })();
  readonly height = this.layout.height;
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
    const rows = this.layout.rows;
    svg.append('defs').append('marker').attr('id', 'arrow').attr('viewBox', '0 0 10 10').attr('refX', 9).attr('refY', 5).attr('markerWidth', 7).attr('markerHeight', 7).attr('orient', 'auto')
      .append('path').attr('d', 'M0,0 L10,5 L0,10 z').attr('fill', '#c7c7cc');

    // Rótulo de fase: pequeño, en mayúsculas, con hairline a la derecha.
    const phases = rows.filter(r => r.phaseY !== null);
    const ph = svg.append('g').selectAll('g').data(phases).join('g').attr('transform', r => `translate(${X0},${r.phaseY! + 18})`);
    ph.append('text').attr('class', 'phase').attr('fill', '#86868b').text(r => r.s.phase.toUpperCase());

    // Flechas entre cajas consecutivas.
    svg.append('g').selectAll('line').data(rows.slice(1)).join('line')
      .attr('x1', X0 + NW / 2).attr('x2', X0 + NW / 2).attr('y1', (_r, i) => rows[i].y + NH).attr('y2', (_r, i) => rows[i].y + NH)
      .attr('stroke', '#c7c7cc').attr('stroke-width', 1.5).attr('marker-end', 'url(#arrow)')
      .transition().duration(360).delay((_r, i) => 70 * i + 160).ease(d3.easeCubicOut).attr('y2', r => r.y - 2);

    const node = svg.append('g').selectAll('g').data(rows).join('g')
      .attr('class', 'node').attr('transform', r => `translate(${X0},${r.y})`).attr('opacity', 0);
    node.transition().duration(380).delay((_r, i) => 70 * i).attr('opacity', 1);
    node.append('rect').attr('class', 'box').attr('width', NW).attr('height', NH).attr('rx', 20).attr('fill', '#fff').attr('stroke', 'rgba(0,0,0,0.06)');
    node.append('text').attr('class', 'num').attr('x', 24).attr('y', 44).attr('fill', '#d4d4d4').text((_r, i) => String(i + 1).padStart(2, '0'));
    node.append('text').attr('class', 'title').attr('x', 78).attr('y', 38).text(r => r.s.label);
    node.append('text').attr('class', 'tool').attr('x', 78).attr('y', 56).attr('fill', '#86868b').text(r => r.s.tool);
    node.append('text').attr('class', 'brief').attr('x', 78).attr('y', 80).attr('fill', '#515154')
      .each((r, i, els) => { const lines = this.wrap(r.s.brief, WRAP); d3.select(els[i]).selectAll('tspan').data(lines).join('tspan').attr('x', 78).attr('dy', (_l, j) => j === 0 ? 0 : 17).text(l => l); });
  }
}
