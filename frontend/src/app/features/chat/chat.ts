import { ChangeDetectionStrategy, Component, DestroyRef, ElementRef, effect, inject, signal, viewChild } from '@angular/core';
import { ApiService } from '../../core/api.service';
import { ShelfService } from '../../core/shelf.service';
import { AgentEvent, Answer, Claim } from '../../core/models';
import { Icon } from '../../shared/icon/icon';

interface Step { kind: AgentEvent['type']; say: string; name?: string; items: NonNullable<AgentEvent['items']>; ms: number; ok?: boolean; }
interface Turn {
  role: 'user' | 'assistant'; text: string; steps: Step[]; answer?: Answer; draft?: string; done: boolean;
  open: boolean; active: number | null; error?: string; startedAt: number; lastAt: number; endedAt?: number;
}
interface Part { t?: string; n?: number; b?: boolean; }

const SUGGESTIONS = [
  '¿Cuál es el plazo para reportar una operación sospechosa a la UIF?',
  '¿Qué se entiende por operación sospechosa?',
  '¿Qué dice Basilea sobre el riesgo operacional y qué exige la SBS?',
  '¿La Res. SBS 789-2018 y la 2660-2015 se contradicen en algo?',
  '¿Cuál es la tasa máxima que fija la SBS para hipotecas?',
];

const ICON: Record<string, string> = {
  start: 'compass', plan: 'lightbulb', think: 'chat-circle-dots', model: 'lightning', draft: 'pencil-simple-line',
  verify: 'shield-check', deliver: 'check-circle', suggest: 'sparkle', guard: 'shield-warning', search: 'magnifying-glass', read: 'book-open-text', refers_to: 'link',
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
  private readonly destroyRef = inject(DestroyRef);
  /** Reloj para el contador de segundos: solo corre mientras el agente trabaja. */
  readonly now = signal(Date.now());
  private timer: ReturnType<typeof setInterval> | null = null;
  readonly shelf = inject(ShelfService);
  readonly suggestions = signal<string[]>(SUGGESTIONS);
  readonly refreshing = signal(false);
  readonly turns = signal<Turn[]>([]);
  readonly draft = signal('');
  readonly busy = signal(false);
  readonly threadId = signal<string | null>(null);
  private readonly threadEl = viewChild<ElementRef<HTMLElement>>('thread');

  constructor() {
    // Al llegar un paso o un turno nuevo, el hilo baja al final.
    this.destroyRef.onDestroy(() => this.stopClock());
    this.loadSuggestions(false);
    effect(() => { this.turns(); queueMicrotask(() => { const el = this.threadEl()?.nativeElement; if (el) { el.scrollTop = el.scrollHeight; } }); });
  }

  /** Preguntas para empezar: las propone el agente a partir del corpus; la lista fija solo cubre un servicio caido. */
  loadSuggestions(fresh: boolean): void {
    this.refreshing.set(true);
    this.api.suggestions(fresh).subscribe({
      next: r => { if (r.questions.length) { this.suggestions.set(r.questions); } this.refreshing.set(false); },
      error: () => this.refreshing.set(false),
    });
  }

  private startClock(): void { this.stopClock(); this.now.set(Date.now()); this.timer = setInterval(() => this.now.set(Date.now()), 100); }
  private stopClock(): void { if (this.timer) { clearInterval(this.timer); this.timer = null; } }

  private patch(fn: (t: Turn) => Turn): void {
    this.turns.update(ts => ts.map((t, i) => (i === ts.length - 1 ? fn(t) : t)));
  }

  ask(text = this.draft().trim()): void {
    if (!text || this.busy()) { return; }
    const t0 = Date.now();
    this.turns.update(t => [...t, { role: 'user', text, steps: [], done: true, open: false, active: null, startedAt: t0, lastAt: t0 },
      { role: 'assistant', text: '', steps: [], done: false, open: true, active: null, startedAt: t0, lastAt: t0 }]);
    this.draft.set(''); this.busy.set(true); this.startClock();
    this.api.answerStream({ question: text, thread_id: this.threadId() }).subscribe({
      next: ev => this.onEvent(ev),
      error: () => { this.patch(t => ({ ...t, done: true, open: false, endedAt: Date.now(), error: 'No pude contactar al servicio del agente.' })); this.busy.set(false); this.stopClock(); },
      complete: () => { this.busy.set(false); this.stopClock(); },
    });
  }

  private onEvent(ev: AgentEvent): void {
    if (ev.type === 'final' && ev.answer) {
      this.threadId.set(ev.answer.thread_id);
      this.patch(t => ({ ...t, answer: ev.answer, draft: undefined, done: true, open: false, active: null, endedAt: Date.now() }));
      return;
    }
    if (ev.type === 'error') { this.patch(t => ({ ...t, done: true, open: false, endedAt: Date.now(), error: ev.message ?? 'Error del agente' })); return; }
    const step: Step = { kind: ev.type, say: ev.say ?? '', name: ev.name, items: ev.items ?? [], ms: ev.ms ?? 0, ok: ev.ok };
    this.patch(t => ({ ...t, steps: [...t.steps, step], lastAt: Date.now(), draft: ev.type === 'draft' ? ev.text : t.draft }));
  }

  /** Sin sustento en el corpus: desde «lo más cercano» hasta el final va en negrita (es lo que el usuario puede leer en su lugar). */
  answerParts(a: Answer): Part[] {
    const i = a.status === 'abstained' ? a.summary.search(/lo m[aá]s cercano/i) : -1;
    if (i < 0) { return this.parts(a.summary); }
    return [...this.parts(a.summary.slice(0, i)), ...this.parts(a.summary.slice(i)).map(p => ({ ...p, b: true }))];
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
  /** Tiempo total del turno: corre en vivo y se congela al terminar. */
  elapsed(t: Turn): string { return this.seconds((t.endedAt ?? this.now()) - t.startedAt); }
  /** Tiempo desde el ultimo paso: lo que lleva «pensando» el agente. */
  idle(t: Turn): string { return this.seconds(this.now() - t.lastAt); }
  seconds(ms: number): string { return (ms / 1000).toFixed(1).replace('.', ',') + ' s'; }
  usd(x: number): string { return x < 0.01 ? x.toFixed(4).replace('.', ',') : x.toFixed(2).replace('.', ','); }
  models(a: Answer): string { return (a.trace.models?.length ? a.trace.models : [a.trace.model]).join(' → '); }
  statusLabel(s: string): string { return ({ ok: 'Verificada', abstained: 'Sin sustento en el corpus', rejected: 'No verificada', pending_human: 'Pendiente de revisión', blocked: 'Pregunta no admitida' } as Record<string, string>)[s] ?? s; }
}
