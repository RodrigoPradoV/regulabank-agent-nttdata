import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { Answer, AgentEvent, AnswerRequest, Article, Conflict, Decision, NormDetail, NormSummary, Pipeline } from './models';

// El API cuelga de `<base href>`: en desarrollo `/api` (ng serve lo reenvia, proxy.conf.js, destino con API_TARGET) y en el droplet
// `/regulabank/api` (nginx). Asi el mismo build sirve en cualquier prefijo.
export const API_URL = `${new URL(document.baseURI).pathname.replace(/\/$/, '')}/api`;

@Injectable({ providedIn: 'root' })
export class ApiService {
  private readonly http = inject(HttpClient);

  norms(): Observable<NormSummary[]> { return this.http.get<NormSummary[]>(`${API_URL}/norms`); }
  norm(id: string): Observable<NormDetail> { return this.http.get<NormDetail>(`${API_URL}/norms/${encodeURIComponent(id)}`); }
  article(id: string): Observable<Article> { return this.http.get<Article>(`${API_URL}/articles/${encodeURIComponent(id)}`); }
  answer(req: AnswerRequest): Observable<Answer> { return this.http.post<Answer>(`${API_URL}/answer`, req); }
  /** El agente trabajando: un AgentEvent por paso (plan, busquedas, lecturas, verificacion) y al final `final`. */
  answerStream(req: AnswerRequest): Observable<AgentEvent> {
    return new Observable<AgentEvent>(sub => {
      const ctl = new AbortController();
      (async () => {
        try {
          const res = await fetch(`${API_URL}/answer/stream`, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(req), signal: ctl.signal });
          if (!res.ok || !res.body) { sub.error(new Error(`HTTP ${res.status}`)); return; }
          const reader = res.body.getReader(); const dec = new TextDecoder(); let buf = '';
          for (;;) {
            const { done, value } = await reader.read();
            if (done) { break; }
            buf += dec.decode(value, { stream: true });
            let i: number;
            while ((i = buf.indexOf('\n\n')) >= 0) {
              const chunk = buf.slice(0, i); buf = buf.slice(i + 2);
              const line = chunk.split('\n').find(l => l.startsWith('data: '));
              if (line) { sub.next(JSON.parse(line.slice(6)) as AgentEvent); }
            }
          }
          sub.complete();
        } catch (e) { if (!ctl.signal.aborted) { sub.error(e); } }
      })();
      return () => ctl.abort();
    });
  }
  suggestions(fresh = false): Observable<{ questions: string[] }> { return this.http.get<{ questions: string[] }>(`${API_URL}/suggestions${fresh ? '?fresh=true' : ''}`); }
  conflicts(): Observable<Conflict[]> { return this.http.get<Conflict[]>(`${API_URL}/conflicts`); }
  pipeline(): Observable<Pipeline> { return this.http.get<Pipeline>(`${API_URL}/pipeline`); }
  decide(id: string, d: Decision): Observable<Conflict> { return this.http.post<Conflict>(`${API_URL}/conflicts/${id}/decide`, d); }
}
