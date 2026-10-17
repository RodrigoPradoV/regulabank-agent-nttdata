import { ChangeDetectionStrategy, Component, ElementRef, effect, inject, signal, viewChild } from '@angular/core';
import { ApiService } from '../../core/api.service';
import { ShelfService } from '../../core/shelf.service';
import { AgentEvent, Answer, Claim } from '../../core/models';
import { Icon } from '../../shared/icon/icon';

interface Step { kind: AgentEvent['type']; say: string; name?: string; items: NonNullable<AgentEvent['items']>; ms: number; ok?: boolean; }
interface Turn {
  role: 'user' | 'assistant'; text: string; steps: Step[]; answer?: Answer; draft?: string; done: boolean;
  open: boolean; active: number | null; error?: string;
}
interface Part { t?: string; n?: number; }

const SUGGESTIONS = [
  '¿Cuál es el plazo para reportar una operación sospechosa a la UIF?',
  '¿Qué se entiende por operación sospechosa?',
  '¿Qué dice Basilea sobre el riesgo operacional y qué exige la SBS?',
  '¿La Res. SBS 789-2018 y la 2660-2015 se contradicen en algo?',
  '¿Cuál es la tasa máxima que fija la SBS para hipotecas?',
];

const ICON: Record<string, string> = {
  start: 'compass', plan: 'lightbulb', think: 'chat-circle-dots', model: 'lightning', draft: 'pencil-simple-line',
  verify: 'shield-check', deliver: 'check-circle', search: 'magnifying-glass', read: 'book-open-text', refers_to: 'link',
  neighbors: 'arrows-out-line-horizontal', conflicts: 'warning', escalate: 'lightning',
};

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
    // Al llegar un paso o un turno nuevo, el hilo baja al final.
    effect(() => { this.turns(); queueMicrotask(() => { const el = this.threadEl()?.nativeElement; if (el) { el.scrollTop = el.scrollHeight; } }); });
  }

  private patch(fn: (t: Turn) => Turn): void {
    this.turns.update(ts => ts.map((t, i) => (i === ts.length - 1 ? fn(t) : t)));
  }

  ask(text = this.draft().trim()): void {
    if (!text || this.busy()) { return; }
    this.turns.update(t => [...t, { role: 'user', text, steps: [], done: true, open: false, active: null },
      { role: 'assistant', text: '', steps: [], done: false, open: true, active: null }]);
    this.draft.set(''); this.busy.set(true);
    this.api.answerStream({ question: text, as_of: this.asOf(), thread_id: this.threadId() }).subscribe({
      next: ev => this.onEvent(ev),
      error: () => { this.patch(t => ({ ...t, done: true, open: false, error: 'No pude contactar al servicio del agente.' })); this.busy.set(false); },
      complete: () => this.busy.set(false),
    });
  }

  private onEvent(ev: AgentEvent): void {
    if (ev.type === 'final' && ev.answer) {
      this.threadId.set(ev.answer.thread_id);
      this.patch(t => ({ ...t, answer: ev.answer, draft: undefined, done: true, open: false, active: null }));
      return;
    }
    if (ev.type === 'error') { this.patch(t => ({ ...t, done: true, open: false, error: ev.message ?? 'Error del agente' })); return; }
    const step: Step = { kind: ev.type, say: ev.say ?? '', name: ev.name, items: ev.items ?? [], ms: ev.ms ?? 0, ok: ev.ok };
    this.patch(t => ({ ...t, steps: [...t.steps, step], draft: ev.type === 'draft' ? ev.text : t.draft }));
  }

  /** El texto con las citas [n] separadas para mostrarlas como numeritos dentro de la frase. */
  parts(text: string): Part[] {
    const out: Part[] = []; let last = 0;
    for (const m of text.matchAll(/\s*\[(\d+)\]/g)) {
      if (m.index! > last) { out.push({ t: text.slice(last, m.index) }); }
      out.push({ n: +m[1] }); last = m.index! + m[0].length;
    }
    if (last < text.length) { out.push({ t: text.slice(last) }); }
    return out;
  }

  claim(a: Answer, n: number): Claim | undefined { return a.claims.find(c => c.n === n); }
  focus(i: number, n: number): void { this.turns.update(ts => ts.map((t, k) => (k === i ? { ...t, active: t.active === n ? null : n } : t))); }
  toggle(i: number): void { this.turns.update(ts => ts.map((t, k) => (k === i ? { ...t, open: !t.open } : t))); }
  pages(c: Claim): string { const m = /\{[^}]*?(pp?\.\s*[\d\-–, ]+)/.exec(c.citation); return m ? m[1].trim() : ''; }
  vigencia(c: Claim): string { return c.is_current === false ? 'no vigente a la fecha' : c.valid_from ? `vigente desde ${c.valid_from}` : 'vigente'; }
  icon(s: Step): string { return ICON[s.name ?? ''] ?? ICON[s.kind] ?? 'dot'; }
  seconds(ms: number): string { return (ms / 1000).toFixed(1).replace('.', ',') + ' s'; }
  usd(x: number): string { return x < 0.01 ? x.toFixed(4).replace('.', ',') : x.toFixed(2).replace('.', ','); }
  models(a: Answer): string { return (a.trace.models?.length ? a.trace.models : [a.trace.model]).join(' → '); }
  statusLabel(s: string): string { return ({ ok: 'Verificada', abstained: 'Sin sustento en el corpus', rejected: 'No verificada', pending_human: 'Pendiente de revisión' } as Record<string, string>)[s] ?? s; }
}
