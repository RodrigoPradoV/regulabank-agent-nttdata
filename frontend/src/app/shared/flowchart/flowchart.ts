import { ChangeDetectionStrategy, Component, ElementRef, afterNextRender, input, viewChild } from '@angular/core';
import * as d3 from 'd3';

export interface FlowStep { id: string; phase: string; label: string; tool: string; brief: string; }

const NW = 440, NH = 112, GAP = 26, PHASE = 44, X0 = 40, TOP = 4, WRAP = 58;

// Diagrama de flujo vertical, monocromo: rótulo de fase › número › título › herramienta › descripción corta.
@Component({
  selector: 'app-flowchart',
  template: `<div class="viz"><svg #svg class="pipeline" [attr.viewBox]="'0 0 520 ' + height()" preserveAspectRatio="xMidYMin meet"></svg></div>`,
  styleUrl: './flowchart.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class Flowchart {
  readonly steps = input.required<FlowStep[]>();
  private readonly svgRef = viewChild.required<ElementRef<SVGSVGElement>>('svg');

  constructor() { afterNextRender(() => this.draw()); }

  private layout() {
    let y = TOP; let last = ''; const rows: { s: FlowStep; y: number; phaseY: number | null }[] = [];
    for (const s of this.steps()) { let phaseY: number | null = null; if (s.phase !== last) { phaseY = y; y += PHASE; last = s.phase; } rows.push({ s, y, phaseY }); y += NH + GAP; }
    return { rows, height: y - GAP + 6 };
  }
  height(): number { return this.layout().height; }

  private wrap(text: string, width: number): string[] {
    const out: string[] = []; let cur = '';
    for (const w of text.split(' ')) { if ((cur + ' ' + w).trim().length > width && cur) { out.push(cur); cur = w; } else { cur = (cur + ' ' + w).trim(); } }
    if (cur) { out.push(cur); }
    return out.slice(0, 2);
  }

  private draw(): void {
    const svg = d3.select(this.svgRef().nativeElement);
    svg.selectAll('*').remove();
    const rows = this.layout().rows;
    svg.append('defs').append('marker').attr('id', 'arrow').attr('viewBox', '0 0 10 10').attr('refX', 9).attr('refY', 5).attr('markerWidth', 7).attr('markerHeight', 7).attr('orient', 'auto')
      .append('path').attr('d', 'M0,0 L10,5 L0,10 z').attr('fill', '#c7c7cc');
    const phases = rows.filter(r => r.phaseY !== null);
    svg.append('g').selectAll('text').data(phases).join('text').attr('class', 'phase').attr('x', X0).attr('y', r => r.phaseY! + 18).attr('fill', '#86868b').text(r => r.s.phase.toUpperCase());
    svg.append('g').selectAll('line').data(rows.slice(1)).join('line')
      .attr('x1', X0 + NW / 2).attr('x2', X0 + NW / 2).attr('y1', (_r, i) => rows[i].y + NH).attr('y2', (_r, i) => rows[i].y + NH)
      .attr('stroke', '#c7c7cc').attr('stroke-width', 1.5).attr('marker-end', 'url(#arrow)')
      .transition().duration(360).delay((_r, i) => 70 * i + 160).ease(d3.easeCubicOut).attr('y2', r => r.y - 2);
    const node = svg.append('g').selectAll('g').data(rows).join('g').attr('class', 'node').attr('transform', r => `translate(${X0},${r.y})`).attr('opacity', 0);
    node.transition().duration(380).delay((_r, i) => 70 * i).attr('opacity', 1);
    node.append('rect').attr('class', 'box').attr('width', NW).attr('height', NH).attr('rx', 20).attr('fill', '#fff').attr('stroke', 'rgba(0,0,0,0.06)');
    node.append('text').attr('class', 'num').attr('x', 24).attr('y', 44).attr('fill', '#d4d4d4').text((_r, i) => String(i + 1).padStart(2, '0'));
    node.append('text').attr('class', 'title').attr('x', 78).attr('y', 38).text(r => r.s.label);
    node.append('text').attr('class', 'tool').attr('x', 78).attr('y', 56).attr('fill', '#86868b').text(r => r.s.tool);
    node.append('text').attr('class', 'brief').attr('x', 78).attr('y', 80).attr('fill', '#515154')
      .each((r, i, els) => { const lines = this.wrap(r.s.brief, WRAP); d3.select(els[i]).selectAll('tspan').data(lines).join('tspan').attr('x', 78).attr('dy', (_l, j) => j === 0 ? 0 : 17).text(l => l); });
  }
}
