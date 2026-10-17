import { ChangeDetectionStrategy, Component, computed, inject, input } from '@angular/core';
import { RouterLink } from '@angular/router';
import { toSignal } from '@angular/core/rxjs-interop';
import { ApiService } from '../../core/api.service';
import { AREA_LABEL, PipelineModel } from '../../core/models';
import { Icon } from '../../shared/icon/icon';
import { AREA_INK } from './flow';

@Component({
  selector: 'app-stage',
  imports: [Icon, RouterLink],
  templateUrl: './stage.html',
  styleUrl: './stage.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class StagePage {
  readonly id = input.required<string>();
  private readonly api = inject(ApiService);
  readonly areaLabel = AREA_LABEL;
  readonly ink = AREA_INK;
  readonly pipeline = toSignal(this.api.pipeline());
  readonly index = computed(() => (this.pipeline()?.stages ?? []).findIndex(s => s.id === this.id()));
  readonly stage = computed(() => this.pipeline()?.stages[this.index()] ?? null);
  readonly prev = computed(() => { const i = this.index(); return i > 0 ? this.pipeline()!.stages[i - 1] : null; });
  readonly next = computed(() => { const p = this.pipeline(); const i = this.index(); return p && i >= 0 && i < p.stages.length - 1 ? p.stages[i + 1] : null; });
  readonly countRows = computed(() => Object.entries(this.stage()?.counts ?? {}));
  readonly active = computed(() => (this.stage()?.models ?? []).filter(m => m.status !== 'rejected'));
  readonly rejected = computed(() => (this.stage()?.models ?? []).filter(m => m.status === 'rejected'));

  fmt(v: number | string): string { return typeof v === 'number' ? new Intl.NumberFormat('de-DE').format(v) : v; }
  statusLabel(st: string): string { return ({ done: 'Listo', partial: 'Parcial', pending: 'Pendiente', active: 'Activo', optional: 'Opcional', planned: 'Después', rejected: 'Descartado' } as Record<string, string>)[st] ?? st; }
  statusClass(st: string): string { return ({ done: 'ok', partial: 'warn', active: 'ok', optional: 'info', planned: '', rejected: 'danger' } as Record<string, string>)[st] ?? ''; }
  familyLabel(m: PipelineModel): string { return ({ regex: 'código', gazetteer: 'vocabulario', ner: 'NER', embedding: 'embedding', nli: 'NLI', llm: 'LLM', reranker: 'reranker' } as Record<string, string>)[m.family] ?? m.family; }
}
