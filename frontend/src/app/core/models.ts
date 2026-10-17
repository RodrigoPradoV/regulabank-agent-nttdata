// Espejo de src/regulabank/api/contracts.py (schema_version 0.1.0).
export type NormKind = 'law' | 'sbs_resolution' | 'sbs_circular' | 'bcrp_circular' | 'internal_policy';
export type RiskLevel = 'auto' | 'notify' | 'approve';
export type AnswerStatus = 'ok' | 'abstained' | 'rejected' | 'pending_human';

export interface NormSummary {
  id: string; short: string; title: string; kind: NormKind; issuer: string; published: string;
  status: 'in_force' | 'repealed' | 'partial'; n_articles: number; topics: string[];
}
export interface Version {
  id: string; n: number; valid_from: string; valid_to: string | null;
  change_kind: 'original' | 'modified' | 'replaced' | 'repealed' | 'added'; changed_by: string | null; text: string;
}
export interface Article {
  id: string; norm_id: string; no: string; path: string; current: Version; versions: Version[];
  refers_to: string[]; entities: string[];
}
export interface NormDetail extends NormSummary { articles: Article[]; }

export interface AnswerRequest { question: string; as_of?: string | null; thread_id?: string | null; }
export interface Claim {
  text: string; chunk_id: string; article_id: string; quote: string; citation: string;
  valid_from: string; valid_to: string | null; verified: boolean;
}
export interface HistoryItem {
  article_id: string; citation: string; valid_from: string; valid_to: string | null; change_kind: string; changed_by: string | null;
}
export interface Trace {
  scenario: string; seen: string[]; lists: Record<string, number>; ppr_new: number; faults: string[]; fixes: number;
  latency_ms: number; cost_usd: number; model: string; prompt_version: string;
}
export interface Answer {
  schema_version: string; thread_id: string; status: AnswerStatus; risk: RiskLevel; as_of: string; summary: string;
  claims: Claim[]; history: HistoryItem[]; trace: Trace;
}
export interface Conflict {
  id: string; policy_chunk_id: string; policy_citation: string; policy_quote: string; norm_version_id: string;
  norm_citation: string; norm_quote: string; relation: 'contradicts' | 'stricter' | 'complies' | 'unrelated';
  method: 'rules' | 'nli' | 'judge' | 'human'; score: number; reason: string;
  status: 'pending_human' | 'confirmed' | 'dismissed';
}
export interface Decision { action: 'accept' | 'edit' | 'reject'; note?: string | null; }

// Dashboard de trazabilidad (espejo de /metrics en backend/regulabank/api/contracts.py)
export interface MetricsFilters {
  date_from?: string; date_to?: string; scenario?: string; status?: string; risk?: string; model?: string;
  q?: string; limit?: number;
}
export interface MetricsSummary {
  total: number; by_status: Partial<Record<string, number>>; by_risk: Partial<Record<string, number>>;
  by_scenario: Partial<Record<string, number>>; fault_counts: Partial<Record<string, number>>;
  fixes_histogram: Partial<Record<string, number>>;
  human_review_rate: number; latency_ms_avg: number; latency_ms_p50: number; latency_ms_p95: number;
  time_saved_minutes: number; human_baseline_minutes: number;
}
export interface MetricsSeriesPoint { bucket: string; count: number; latency_ms_avg: number; abstained: number; rejected: number; }
export interface MetricsEntry {
  logged_at: string; question: string | null; as_of: string | null; scenario: string | null; status: string | null;
  risk: string | null; latency_ms: number | null; fixes: number; faults: string[]; human_decision: string | null;
  model: string | null; seen: string[];
}
export interface MetricsResponse { summary: MetricsSummary; series: MetricsSeriesPoint[]; entries: MetricsEntry[]; }

export const STATUS_LABEL: Record<string, string> = {
  ok: 'Entregada', abstained: 'Abstención', rejected: 'Rechazada', pending_human: 'En revisión',
};
export const RISK_LABEL: Record<string, string> = { auto: 'Automático', notify: 'Notifica', approve: 'Revisión humana' };
export const SCENARIO_LABEL: Record<string, string> = {
  lookup: 'Búsqueda directa', definition: 'Definición', threshold: 'Umbral', procedure: 'Procedimiento',
  validity: 'Vigencia', crossref: 'Referencia cruzada', policy_vs_norm: 'Política vs. norma', impact: 'Impacto',
  negative: 'Control negativo',
};

export const NORM_KIND_LABEL: Record<NormKind, string> = {
  law: 'Ley', sbs_resolution: 'Resolución SBS', sbs_circular: 'Circular SBS', bcrp_circular: 'Circular BCRP', internal_policy: 'Política interna',
};

// Flujo (espejo de backend/regulabank/api/pipeline.py)
export type StageStatus = 'done' | 'partial' | 'pending';
export type StageArea = 'corpus' | 'graph' | 'search' | 'agents';
export interface PipelineModel { name: string; role: string; family: string; size: string; runs_on: string; status: 'active' | 'optional' | 'planned' | 'rejected'; why: string; }
export interface PipelineParam { name: string; value: string; source: string; }
export interface Stage {
  id: string; area: StageArea; label: string; summary: string; input_title: string; input: string[]; output_title: string; output: string[];
  models: PipelineModel[]; params: PipelineParam[]; counts: Record<string, number | string>; status: StageStatus; doc: string; code: string;
}
export interface Pipeline { release_id: string; stages: Stage[]; }
export const AREA_LABEL: Record<StageArea, string> = { corpus: 'Corpus', graph: 'Grafo', search: 'Búsqueda', agents: 'Agentes' };
