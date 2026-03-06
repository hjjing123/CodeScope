import request from '../utils/request';
import type {
  Rule,
  RuleVersion,
  RuleSet,
  RuleSetDetail,
  RuleStats,
  SelfTestJob,
  RuleCreateRequest,
  RuleDraftUpdateRequest,
  RuleSetCreateRequest,
  RuleSetUpdateRequest,
  RuleSelfTestCreateRequest,
} from '../types/rule';

export interface RuleListParams {
  page?: number;
  page_size?: number;
  enabled?: boolean;
  vuln_type?: string;
}

export interface RuleStatsParams {
  page?: number;
  page_size?: number;
  rule_key?: string;
  metric_date_from?: string;
  metric_date_to?: string;
}

export interface RuleListResponse {
  items: Rule[];
  total: number;
}

export interface RuleVersionListResponse {
  items: RuleVersion[];
  total: number;
}

export interface RuleSetListResponse {
  items: RuleSet[];
  total: number;
}

export interface RuleStatsListResponse {
  items: RuleStats[];
  total: number;
}

export interface RuleUpdateResponse {
  rule: Rule;
  draft_version: RuleVersion;
}

export interface RulePublishResponse {
  rule: Rule;
  published_version: RuleVersion;
}

export interface SelfTestLogsResponse {
  task_type: string;
  task_id: string;
  items: Array<{
    timestamp: string;
    level: string;
    message: string;
    stage: string;
  }>;
}

export const getRules = (params?: RuleListParams) => {
  return request.get<unknown, RuleListResponse>('/rules', { params });
};

export const getRuleDetails = (ruleKey: string) => {
  return request.get<unknown, Rule>(`/rules/${ruleKey}`);
};

export const getRuleVersions = (ruleKey: string) => {
  return request.get<unknown, RuleVersionListResponse>(`/rules/${ruleKey}/versions`);
};

export const createRule = (data: RuleCreateRequest) => {
  return request.post<unknown, Rule>('/rules', data);
};

export const updateDraft = (ruleKey: string, data: RuleDraftUpdateRequest) => {
  return request.patch<unknown, RuleUpdateResponse>(`/rules/${ruleKey}/draft`, data);
};

export const publish = (ruleKey: string) => {
  return request.post<unknown, RulePublishResponse>(`/rules/${ruleKey}/publish`);
};

export const rollback = (ruleKey: string, version: number) => {
  return request.post<unknown, Rule>(`/rules/${ruleKey}/rollback`, { version });
};

export const toggle = (ruleKey: string, enabled: boolean) => {
  return request.post<unknown, Rule>(`/rules/${ruleKey}/toggle`, { enabled });
};

export const runSelfTest = (data: RuleSelfTestCreateRequest) => {
  return request.post<unknown, { selftest_job_id: string }>('/rules/selftest', data);
};

export const runSelfTestWithUpload = (
  file: File,
  data: {
    rule_key?: string;
    rule_version?: number;
    draft_payload?: Record<string, unknown>;
  }
) => {
  const formData = new FormData();
  formData.append('file', file);
  if (data.rule_key) formData.append('rule_key', data.rule_key);
  if (data.rule_version) formData.append('rule_version', String(data.rule_version));
  if (data.draft_payload) formData.append('draft_payload', JSON.stringify(data.draft_payload));

  return request.post<unknown, { selftest_job_id: string }>('/rules/selftest/upload', formData, {
    headers: {
      'Content-Type': 'multipart/form-data',
    },
  });
};

export const getSelfTestJob = (jobId: string) => {
  return request.get<unknown, SelfTestJob>(`/rules/selftest/${jobId}`);
};

export const getSelfTestLogs = (jobId: string, params?: { stage?: string; tail?: number }) => {
  return request.get<unknown, SelfTestLogsResponse>(`/rules/selftest/${jobId}/logs`, { params });
};

export const getRuleSets = (params?: { page?: number; page_size?: number }) => {
  return request.get<unknown, RuleSetListResponse>('/rule-sets', { params });
};

export const getRuleSet = (ruleSetId: string) => {
  return request.get<unknown, RuleSetDetail>(`/rule-sets/${ruleSetId}`);
};

export const createRuleSet = (data: RuleSetCreateRequest) => {
  return request.post<unknown, RuleSet>('/rule-sets', data);
};

export const updateRuleSet = (ruleSetId: string, data: RuleSetUpdateRequest) => {
  return request.patch<unknown, RuleSet>(`/rule-sets/${ruleSetId}`, data);
};

export const bindRuleSetRules = (ruleSetId: string, ruleKeys: string[]) => {
  return request.post<unknown, RuleSetDetail>(`/rule-sets/${ruleSetId}/rules`, { rule_keys: ruleKeys });
};

export const getRuleStats = (params?: RuleStatsParams) => {
  return request.get<unknown, RuleStatsListResponse>('/rule-stats', { params });
};
