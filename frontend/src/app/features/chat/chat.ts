import { ChangeDetectionStrategy, Component, ElementRef, effect, inject, signal, viewChild } from '@angular/core';
import { ApiService } from '../../core/api.service';
import { ShelfService } from '../../core/shelf.service';
import { Answer } from '../../core/models';
import { Icon } from '../../shared/icon/icon';

interface Turn { role: 'user' | 'assistant'; text: string; answer?: Answer; }

const SUGGESTIONS = [
  '¿Cuál es el plazo para reportar una operación sospechosa a la UIF?',
  '¿Cuál es la exposición máxima con un mismo deudor?',
  '¿Desde qué monto se registra una operación en efectivo?',
  '¿Qué se entiende por operación sospechosa?',
  '¿Cuál es la tasa máxima que fija la SBS para hipotecas?',
];

@Component({
  selector: 'app-chat',
  imports: [Icon],
  templateUrl: './chat.html',
  styleUrl: './chat.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class Chat {
  private readonly api = inject(ApiService);
  readonly shelf = inject(ShelfService);
  readonly suggestions = SUGGESTIONS;
  readonly turns = signal<Turn[]>([]);
  readonly draft = signal('');
  readonly asOf = signal(new Date().toISOString().slice(0, 10));
  readonly busy = signal(false);
  readonly threadId = signal<string | null>(null);
  private readonly threadEl = viewChild<ElementRef<HTMLElement>>('thread');

  constructor() {
    // Al llegar un turno nuevo, el hilo baja al final.
    effect(() => { this.turns(); this.busy(); queueMicrotask(() => { const el = this.threadEl()?.nativeElement; if (el) { el.scrollTop = el.scrollHeight; } }); });
  }

  ask(text = this.draft().trim()): void {
    if (!text || this.busy()) { return; }
    this.turns.update(t => [...t, { role: 'user', text }]);
    this.draft.set(''); this.busy.set(true);
    this.api.answer({ question: text, as_of: this.asOf(), thread_id: this.threadId() }).subscribe({
      next: a => { this.threadId.set(a.thread_id); this.turns.update(t => [...t, { role: 'assistant', text: a.summary, answer: a }]); this.busy.set(false); },
      error: () => { this.turns.update(t => [...t, { role: 'assistant', text: 'No pude contactar al servicio. ¿Está corriendo la API en :8010?' }]); this.busy.set(false); },
    });
  }
  riskLabel(r: string): string { return r === 'auto' ? 'Automático' : r === 'notify' ? 'Aviso' : 'Requiere aprobación'; }
  riskClass(r: string): string { return r === 'auto' ? 'ok' : r === 'notify' ? 'warn' : 'danger'; }
  statusLabel(s: string): string { return ({ ok: 'Verificada', abstained: 'Abstención', rejected: 'Rechazada', pending_human: 'Pendiente de persona' } as Record<string, string>)[s] ?? s; }
}
