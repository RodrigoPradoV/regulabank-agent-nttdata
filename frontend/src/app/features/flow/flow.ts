import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { Router, RouterLink } from '@angular/router';
import { toSignal } from '@angular/core/rxjs-interop';
import { ApiService } from '../../core/api.service';
import { AREA_LABEL, Pipeline, Stage } from '../../core/models';
import { Icon } from '../../shared/icon/icon';

// Tinta, relleno y lavado por área: los mismos valores que declara styles/_base.scss con data-area.
export const AREA_INK: Record<string, { ink: string; fill: string; soft: string }> = {
  corpus: { ink: '#2d4db5', fill: '#5b74d4', soft: '#eaeef9' },
  graph: { ink: '#3f63e0', fill: '#6e92ff', soft: '#eef2ff' },
  search: { ink: '#6f7d00', fill: '#d6eb52', soft: '#f7fadf' },
  agents: { ink: '#6a46b8', fill: '#a17be8', soft: '#f2ecfb' },
};

interface Stop { stage: Stage; x: number; value: string; h: number; caption: string[]; }
interface Tip { x: number; y: number; text: string; }

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
  readonly tip = signal<Tip | null>(null);
  readonly W = 1180; readonly H = 310; readonly base = 178;

  // Cinta de recorrido: el grosor es el volumen (escala log) que pasa por cada parada.
  readonly stops = computed<Stop[]>(() => {
    const p = this.pipeline(); if (!p) { return []; }
    const n = p.stages.length; const pad = 76;
    return p.stages.map((s, i) => {
      const main = this.mainCount(s);
      const v = typeof main === 'number' ? main : 0;
      return {
        stage: s, x: pad + (i * (this.W - 2 * pad)) / (n - 1),
        value: typeof main === 'number' ? (v > 0 ? this.fmt(v) : '·') : (main || '·'),
        h: v > 0 ? 12 + 84 * Math.min(1, Math.log10(1 + v) / 5) : 10,
        caption: this.wrap(s.summary, 22, 2),
      };
    });
  });
  // Curva suave entre paradas: tangentes horizontales en cada punto (misma lectura que curveMonotoneX).
  readonly ribbon = computed(() => {
    const s = this.stops(); if (s.length < 2) { return ''; }
    const edge = (pts: { x: number; y: number }[]) => pts.slice(1).map((p, i) => { const q = pts[i]; const dx = (p.x - q.x) / 2; return `C${q.x + dx},${q.y} ${p.x - dx},${p.y} ${p.x},${p.y}`; }).join(' ');
    const top = s.map(p => ({ x: p.x, y: this.base - p.h / 2 }));
    const bottom = [...s].reverse().map(p => ({ x: p.x, y: this.base + p.h / 2 }));
    return `M${top[0].x},${top[0].y} ${edge(top)} L${bottom[0].x},${bottom[0].y} ${edge(bottom)} Z`;
  });
  readonly done = computed(() => (this.pipeline()?.stages ?? []).filter(s => s.status === 'done').length);
  readonly activeModels = computed(() => (this.pipeline()?.stages ?? []).flatMap(s => s.models).filter(m => m.status === 'active' && m.family !== 'regex').length);
  readonly areas = computed(() => {
    const p = this.pipeline(); if (!p) { return []; }
    const order: Stage['area'][] = ['corpus', 'graph', 'search', 'agents'];
    return order.map(a => ({ area: a, label: AREA_LABEL[a], stages: p.stages.filter(s => s.area === a) })).filter(g => g.stages.length);
  });

  mainCount(s: Stage): number | string | null {
    for (const k of ['chunks', 'edges', 'entities', 'vectors', 'norms', 'pages', 'articles', 'findings', 'pairs']) { if (k in s.counts) { return s.counts[k]; } }
    return null;
  }
  fmt(v: number): string { return new Intl.NumberFormat('de-DE').format(v); }
  wrap(text: string, width: number, lines: number): string[] {
    const out: string[] = []; let cur = '';
    for (const w of text.split(' ')) { if ((cur + ' ' + w).trim().length > width && cur) { out.push(cur); cur = w; } else { cur = (cur + ' ' + w).trim(); } }
    if (cur) { out.push(cur); }
    if (out.length > lines) { out.length = lines; out[lines - 1] = out[lines - 1].replace(/[,.]?$/, '…'); }
    return out;
  }
  open(s: Stage): void { this.router.navigate(['/flow', s.id]); }
  showTip(e: MouseEvent, s: Stop): void {
    const models = s.stage.models.filter(m => m.status === 'active').map(m => m.name).join(' · ');
    this.tip.set({ x: e.clientX + 14, y: e.clientY + 14, text: `${s.stage.label} · ${this.statusLabel(s.stage.status)}\n${s.stage.input_title} → ${s.stage.output_title}\n${models || 'sin modelos'}` });
  }
  hideTip(): void { this.tip.set(null); }
  statusLabel(st: string): string { return st === 'done' ? 'Listo' : st === 'partial' ? 'Parcial' : 'Pendiente'; }
  statusClass(st: string): string { return st === 'done' ? 'ok' : st === 'partial' ? 'warn' : 'gray'; }
}
