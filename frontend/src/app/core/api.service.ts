import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { Answer, AnswerRequest, Article, Conflict, Decision, NormDetail, NormSummary, Pipeline } from './models';

export const API_URL = 'http://127.0.0.1:8010';

@Injectable({ providedIn: 'root' })
export class ApiService {
  private readonly http = inject(HttpClient);

  norms(): Observable<NormSummary[]> { return this.http.get<NormSummary[]>(`${API_URL}/norms`); }
  norm(id: string): Observable<NormDetail> { return this.http.get<NormDetail>(`${API_URL}/norms/${encodeURIComponent(id)}`); }
  article(id: string): Observable<Article> { return this.http.get<Article>(`${API_URL}/articles/${encodeURIComponent(id)}`); }
  answer(req: AnswerRequest): Observable<Answer> { return this.http.post<Answer>(`${API_URL}/answer`, req); }
  conflicts(): Observable<Conflict[]> { return this.http.get<Conflict[]>(`${API_URL}/conflicts`); }
  pipeline(): Observable<Pipeline> { return this.http.get<Pipeline>(`${API_URL}/pipeline`); }
  decide(id: string, d: Decision): Observable<Conflict> { return this.http.post<Conflict>(`${API_URL}/conflicts/${id}/decide`, d); }
}
