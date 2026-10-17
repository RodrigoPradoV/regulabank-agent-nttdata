import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { ApiService } from '../../core/api.service';
import { Conflict } from '../../core/models';
import { Icon } from '../../shared/icon/icon';

@Component({
  selector: 'app-conflicts',
  imports: [Icon],
  templateUrl: './conflicts.html',
  styleUrl: './conflicts.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class Conflicts {
  private readonly api = inject(ApiService);
  readonly items = signal<Conflict[]>([]);
  constructor() { this.api.conflicts().subscribe(c => this.items.set(c)); }
  decide(c: Conflict, action: 'accept' | 'reject'): void {
    this.api.decide(c.id, { action }).subscribe(updated => this.items.update(list => list.map(x => x.id === updated.id ? updated : x)));
  }
  relationLabel(r: string): string { return ({ contradicts: 'Contradice', stricter: 'Más estricta', complies: 'Cumple', unrelated: 'Sin relación' } as Record<string, string>)[r]; }
  statusLabel(s: string): string { return ({ pending_human: 'Pendiente', confirmed: 'Confirmado', dismissed: 'Descartado' } as Record<string, string>)[s]; }
}
