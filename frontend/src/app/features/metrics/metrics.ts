import { KeyValuePipe } from '@angular/common';
import { ChangeDetectionStrategy, Component, ElementRef, effect, inject, signal, viewChild } from '@angular/core';
import * as d3 from 'd3';
import { ApiService } from '../../core/api.service';
import {
  MetricsFilters, MetricsResponse, MetricsSeriesPoint, RISK_LABEL, SCENARIO_LABEL, STATUS_LABEL,
} from '../../core/models';
import { Icon } from '../../shared/icon/icon';

// Dashboard de trazabilidad sobre `data/ledger/answer_graph.jsonl` (GET /metrics). Una fila por consulta,
// agregada y filtrable; nunca inventa datos que el ledger no tiene (docs/10-evaluation.md, docs/ALCANCE...).
@Component({
  selector: 'app-metrics',
  imports: [Icon, KeyValuePipe],
  templateUrl: './metrics.html',
  styleUrl: './metrics.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class Metrics {
  private readonly api = inject(ApiService);

  readonly data = signal<MetricsResponse | null>(null);
  readonly loading = signal(false);
  readonly error = signal<string | null>(null);
  readonly tip = signal<{ x: number; y: number; text: string } | null>(null);

  readonly dateFrom = signal('');
  readonly dateTo = signal('');
  readonly scenario = signal('');
  readonly status = signal('');
  readonly risk = signal('');
  readonly q = signal('');

  readonly statusLabel = STATUS_LABEL;
  readonly riskLabel = RISK_LABEL;
  readonly scenarioLabel = SCENARIO_LABEL;

  private readonly chartRef = viewChild<ElementRef<SVGSVGElement>>('chart');

  constructor() {
    this.reload();
    effect(() => {
      const series = this.data()?.series ?? [];
      const svg = this.chartRef()?.nativeElement;
      if (svg) { this.drawSeries(svg, series); }
    });
  }

  private currentFilters(): MetricsFilters {
    const filters: MetricsFilters = { limit: 50 };
    if (this.dateFrom()) filters.date_from = this.dateFrom();
    if (this.dateTo()) filters.date_to = this.dateTo();
    if (this.scenario()) filters.scenario = this.scenario();
    if (this.status()) filters.status = this.status();
    if (this.risk()) filters.risk = this.risk();
    if (this.q().trim()) filters.q = this.q().trim();
    return filters;
  }

  reload(): void {
    this.loading.set(true);
    this.error.set(null);
    this.api.metrics(this.currentFilters()).subscribe({
      next: (res) => { this.data.set(res); this.loading.set(false); },
      error: () => {
        this.error.set('No se pudo cargar métricas. ¿Está corriendo la API en :8010?');
        this.loading.set(false);
      },
    });
  }

  clearFilters(): void {
    this.dateFrom.set(''); this.dateTo.set(''); this.scenario.set('');
    this.status.set(''); this.risk.set(''); this.q.set('');
    this.reload();
  }

  entries(record: Partial<Record<string, number>>): [string, number][] {
    return Object.entries(record)
      .map(([key, value]) => [key, value ?? 0] as [string, number])
      .sort((a, b) => b[1] - a[1]);
  }

  pct(n: number): string { return `${Math.round(n * 100)}%`; }
  round(n: number): number { return Math.round(n); }
  ms(n: number): string { return n >= 1000 ? `${(n / 1000).toFixed(1)} s` : `${Math.round(n)} ms`; }
  statusText(s: string | null): string { return s ? (this.statusLabel[s] ?? s) : '—'; }
  riskText(r: string | null): string { return r ? (this.riskLabel[r] ?? r) : '—'; }
  scenarioText(s: string | null): string { return s ? (this.scenarioLabel[s] ?? s) : '—'; }
  statusPillClass(s: string | null): string {
    return ({ ok: 'ok', abstained: 'info', pending_human: 'warn', rejected: 'danger' } as Record<string, string>)[s ?? ''] ?? '';
  }

  private drawSeries(svg: SVGSVGElement, series: MetricsSeriesPoint[]): void {
    const W = 640, H = 180, M = { top: 12, right: 12, bottom: 24, left: 12 }, R = 4;
    const sel = d3.select(svg).attr('viewBox', `0 0 ${W} ${H}`);
    sel.selectAll('*').remove();

    if (!series.length) {
      sel.append('text').attr('x', W / 2).attr('y', H / 2).attr('text-anchor', 'middle')
        .attr('fill', 'var(--text-tertiary)').attr('font-size', 13).text('Sin consultas en el rango filtrado.');
      return;
    }

    const baseline = H - M.bottom;
    const x = d3.scaleBand<string>().domain(series.map((s) => s.bucket)).range([M.left, W - M.right]).padding(0.28);
    const y = d3.scaleLinear().domain([0, Math.max(1, ...series.map((s) => s.count))]).range([baseline, M.top]);

    sel.append('line').attr('x1', M.left).attr('x2', W - M.right).attr('y1', baseline).attr('y2', baseline)
      .attr('stroke', 'var(--border-medium)');

    const bars = sel.append('g').selectAll('path').data(series).join('path')
      .attr('fill', 'var(--area-fill)').style('cursor', 'default')
      .attr('d', (s) => {
        const bx = x(s.bucket)!, bw = x.bandwidth(), by = y(s.count), bh = baseline - by;
        if (bh <= 0.5) return `M${bx},${baseline} h${bw} v0.5 h${-bw} Z`;
        const r = Math.min(R, bw / 2, bh);
        return `M${bx},${by + r} Q${bx},${by} ${bx + r},${by} H${bx + bw - r} Q${bx + bw},${by} ${bx + bw},${by + r} V${baseline} H${bx} Z`;
      });

    bars.on('mousemove', (event: MouseEvent, s: MetricsSeriesPoint) => {
      this.tip.set({
        x: event.clientX, y: event.clientY,
        text: `${s.bucket}\n${s.count} consulta(s) · latencia prom. ${this.ms(s.latency_ms_avg)}`,
      });
    }).on('mouseleave', () => this.tip.set(null));

    sel.append('g').selectAll('text').data(series).join('text')
      .attr('x', (s) => x(s.bucket)! + x.bandwidth() / 2).attr('y', baseline + 16).attr('text-anchor', 'middle')
      .attr('fill', 'var(--text-tertiary)').attr('font-size', 10).text((s) => s.bucket.slice(5));
  }
}
