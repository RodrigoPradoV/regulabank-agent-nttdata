import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { Router } from '@angular/router';
import { toSignal } from '@angular/core/rxjs-interop';
import { ApiService } from '../../core/api.service';
import { NORM_KIND_LABEL, NormKind, NormSummary } from '../../core/models';
import { Icon } from '../../shared/icon/icon';

@Component({
  selector: 'app-norms',
  imports: [Icon],
  templateUrl: './norms.html',
  styleUrl: './norms.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class Norms {
  private readonly api = inject(ApiService);
  private readonly router = inject(Router);
  readonly kindLabel = NORM_KIND_LABEL;
  readonly query = signal('');
  readonly kind = signal<NormKind | 'all'>('all');
  readonly all = toSignal(this.api.norms(), { initialValue: [] as NormSummary[] });
  readonly norms = computed(() => {
    const q = this.query().toLowerCase(); const k = this.kind();
    return this.all().filter(n => (k === 'all' || n.kind === k) && (!q || `${n.short} ${n.title} ${n.topics.join(' ')}`.toLowerCase().includes(q)));
  });
  readonly counts = computed(() => ({
    total: this.all().length, regulation: this.all().filter(n => n.kind !== 'internal_policy').length,
    policy: this.all().filter(n => n.kind === 'internal_policy').length,
  }));
  open(n: NormSummary): void { this.router.navigate(['/norms', n.id]); }
  statusClass(n: NormSummary): string { return n.status === 'in_force' ? 'ok' : n.status === 'partial' ? 'warn' : 'danger'; }
  statusLabel(n: NormSummary): string { return n.status === 'in_force' ? 'Vigente' : n.status === 'partial' ? 'Modificada' : 'Derogada'; }
}
