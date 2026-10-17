// Espejo de src/regulabank/api/contracts.py (schema_version 0.1.0).
export type NormKind = 'law' | 'legislative_decree' | 'supreme_decree' | 'sbs_resolution' | 'sbs_circular' | 'bcrp_circular' | 'internal_policy'
  | 'international_standard' | 'international_guideline' | 'eu_regulation' | 'standard';
export type RiskLevel = 'auto' | 'notify' | 'approve';
export type AnswerStatus = 'ok' | 'abstained' | 'rejected' | 'pending_human' | 'blocked';

export interface NormSummary {
  id: string; short: string; title: string; kind: NormKind; issuer: string; published: string;
  status: 'in_force' | 'repealed' | 'partial' | 'scheduled'; n_articles: number; topics: string[];
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
  n?: number; norm_short?: string; article_no?: string; is_current?: boolean;
}
export interface HistoryItem {
  article_id: string; citation: string; valid_from: string; valid_to: string | null; change_kind: string; changed_by: string | null;
}
export interface Trace {
  scenario: string; seen: string[]; lists: Record<string, number>; ppr_new: number; faults: string[]; fixes: number;
  latency_ms: number; cost_usd: number; model: string; prompt_version: string; tool_calls?: number; models?: string[];
}
export interface Answer {
  schema_version: string; thread_id: string; status: AnswerStatus; risk: RiskLevel; as_of: string; summary: string;
  claims: Claim[]; history: HistoryItem[]; trace: Trace; follow_ups?: string[];
}
export interface Conflict {
  id: string; policy_chunk_id: string; policy_citation: string; policy_quote: string; norm_version_id: string;
  norm_citation: string; norm_quote: string; relation: 'contradicts' | 'stricter' | 'complies' | 'unrelated';
  method: 'rules' | 'nli' | 'judge' | 'human'; score: number; reason: string;
  status: 'pending_human' | 'confirmed' | 'dismissed';
}
export interface Decision { action: 'accept' | 'edit' | 'reject'; note?: string | null; }

export const NORM_KIND_LABEL: Record<NormKind, string> = {
  law: 'Ley', legislative_decree: 'Decreto legislativo', supreme_decree: 'Decreto supremo', sbs_resolution: 'Resolución SBS',
  sbs_circular: 'Circular SBS', bcrp_circular: 'Circular BCRP', internal_policy: 'Política interna', international_standard: 'Estándar internacional',
  international_guideline: 'Guía internacional', eu_regulation: 'Reglamento UE', standard: 'Estándar',
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

// Eventos del agente (Server-Sent Events de POST /answer/stream): cada uno trae `say`, una frase lista para mostrar.
export interface StepItem { n: number; cita: string; vigente: boolean; fragmento: string; }
export interface AgentEvent {
  type: 'start' | 'plan' | 'think' | 'tool' | 'model' | 'draft' | 'verify' | 'deliver' | 'suggest' | 'guard' | 'final' | 'error';
  say?: string; ms?: number; name?: string; args?: Record<string, unknown>; summary?: string; items?: StepItem[];
  complexity?: number; strategy?: string; budget?: number; model?: string; text?: string; ok?: boolean; faults?: string[];
  from?: string; to?: string; reason?: string; status?: string; claims?: number; answer?: Answer; message?: string; scenario?: string;
}
