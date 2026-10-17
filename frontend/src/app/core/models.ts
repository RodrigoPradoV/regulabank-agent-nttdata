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

export const NORM_KIND_LABEL: Record<NormKind, string> = {
  law: 'Ley', sbs_resolution: 'Resolución SBS', sbs_circular: 'Circular SBS', bcrp_circular: 'Circular BCRP', internal_policy: 'Política interna',
};
