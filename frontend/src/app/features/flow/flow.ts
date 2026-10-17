import { ChangeDetectionStrategy, Component, computed, inject } from '@angular/core';
import { Router, RouterLink } from '@angular/router';
import { toSignal } from '@angular/core/rxjs-interop';
import { ApiService } from '../../core/api.service';
import { AREA_LABEL, Pipeline, Stage } from '../../core/models';
import { Icon } from '../../shared/icon/icon';

// Colores por área: tinta y relleno (patrón del atlas: color por área, texto sin fill hereda).
export const AREA_INK: Record<string, { ink: string; fill: string; soft: string }> = {
  corpus: { ink: '#2d4db5', fill: '#5b74d4', soft: '#eaeef9' },
  graph: { ink: '#256e6e', fill: '#5fbdbd', soft: '#e3f3f3' },
  search: { ink: '#6f7d00', fill: '#b9cc2e', soft: '#f3f6dc' },
  agents: { ink: '#6a46b8', fill: '#a17be8', soft: '#efe8fb' },
};

interface Stop { stage: Stage; x: number; value: string; h: number; }

@Component({
  selector: 'app-flow',
  imports: [Icon, RouterLink],
  templateUrl: './flow.html',
  styleUrl: './flow.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class Flow {
  private readonly api = inject(ApiService);
  private readonly router = inject(Router);
  readonly areaLabel = AREA_LABEL;
  readonly ink = AREA_INK;
  readonly pipeline = toSignal(this.api.pipeline());
  readonly W = 1180; readonly H = 300; readonly base = 170;

  readonly stops = computed<Stop[]>(() => {
    const p = this.pipeline(); if (!p) { return []; }
    const n = p.stages.length; const pad = 70;
    return p.stages.map((s, i) => {
      const main = this.mainCount(s);
      const v = typeof main === 'number' ? main : 0;
      const h = v > 0 ? 10 + 86 * Math.log10(1 + v) / 5 : 10;
      return { stage: s, x: pad + (i * (this.W - 2 * pad)) / (n - 1), value: typeof main === 'number' ? (main > 0 ? this.fmt(main) : '·') : (main || '·'), h };
    });
  });
  readonly ribbon = computed(() => {
    const s = this.stops(); if (!s.length) { return ''; }
    const top = s.map(p => `${p.x},${this.base - p.h / 2}`).join(' L');
    const bottom = [...s].reverse().map(p => `${p.x},${this.base + p.h / 2}`).join(' L');
    return `M${top} L${bottom} Z`;
  });
  readonly done = computed(() => (this.pipeline()?.stages ?? []).filter(s => s.status === 'done').length);
  readonly activeModels = computed(() => (this.pipeline()?.stages ?? []).flatMap(s => s.models).filter(m => m.status === 'active' && m.family !== 'regex').length);

  mainCount(s: Stage): number | string | null {
    const order = ['chunks', 'edges', 'entities', 'vectors', 'norms', 'pages', 'articles', 'findings', 'pairs'];
    for (const k of order) { if (k in s.counts) { return s.counts[k]; } }
    return null;
  }
  fmt(v: number): string { return new Intl.NumberFormat('de-DE').format(v); }
  open(s: Stage): void { this.router.navigate(['/flow', s.id]); }
  statusLabel(st: string): string { return st === 'done' ? 'Listo' : st === 'partial' ? 'Parcial' : 'Pendiente'; }
  statusClass(st: string): string { return st === 'done' ? 'ok' : st === 'partial' ? 'warn' : ''; }
}
