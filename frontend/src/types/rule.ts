export interface Rule {
  rule_key: string;
  name: string;
  vuln_type: string;
  default_severity: string;
  language_scope: string;
  description?: string | null;
  enabled: boolean;
  active_version?: number | null;
  created_at: string;
  updated_at: string;
}

export interface RuleVersion {
  id: string;
  rule_key: string;
  version: number;
  status: string;
  content: Record<string, any>;
  created_by?: string | null;
  created_at: string;
}

export interface RuleSet {
  id: string;
  key: string;
  name: string;
  description?: string | null;
  enabled: boolean;
  rule_count: number;
  created_at: string;
  updated_at: string;
}

export interface RuleSetItem {
  id: string;
  rule_set_id: string;
  rule_key: string;
  created_at: string;
}

export interface RuleSetDetail extends Omit<RuleSet, 'rule_count'> {
  items: RuleSetItem[];
}

export interface RuleStats {
  rule_key: string;
  rule_version: number;
  metric_date: string;
  hits: number;
  avg_duration_ms: number;
  timeout_count: number;
  fp_count: number;
}

export interface SelfTestJob {
  id: string;
  rule_key?: string | null;
  rule_version?: number | null;
  payload: Record<string, any>;
  status: string;
  stage: string;
  failure_code?: string | null;
  failure_hint?: string | null;
  result_summary: Record<string, any>;
  created_by?: string | null;
  started_at?: string | null;
  finished_at?: string | null;
  created_at: string;
  updated_at: string;
}

export interface RuleCreateRequest {
  rule_key: string;
  name: string;
  vuln_type: string;
  default_severity: string;
  language_scope?: string;
  description?: string;
  content: Record<string, any>;
}

export interface RuleDraftUpdateRequest {
  name?: string;
  vuln_type?: string;
  default_severity?: string;
  language_scope?: string;
  description?: string;
  content?: Record<string, any>;
}

export interface RuleSetCreateRequest {
  key: string;
  name: string;
  description?: string;
  enabled?: boolean;
}

export interface RuleSetUpdateRequest {
  name?: string;
  description?: string;
  enabled?: boolean;
}

export interface RuleSelfTestCreateRequest {
  rule_key?: string;
  rule_version?: number;
  draft_payload?: Record<string, any>;
  version_id?: string;
}
