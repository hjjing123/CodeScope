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
  search?: string;
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

interface ApiResponse<T> {
  request_id: string;
  data: T;
  meta: Record<string, unknown>;
}

export const getRules = (params?: RuleListParams) => {
  return request
    .get<unknown, ApiResponse<RuleListResponse>>('/rules', { params })
    .then((res) => res.data);
};

export const getRuleDetails = (ruleKey: string) => {
  return request
    .get<unknown, ApiResponse<Rule>>(`/rules/${ruleKey}`)
    .then((res) => res.data);
};

export const getRuleVersions = (ruleKey: string) => {
  return request
    .get<unknown, ApiResponse<RuleVersionListResponse>>(`/rules/${ruleKey}/versions`)
    .then((res) => res.data);
};

export const createRule = (data: RuleCreateRequest) => {
  return request
    .post<unknown, ApiResponse<Rule>>('/rules', data)
    .then((res) => res.data);
};

export const updateDraft = (ruleKey: string, data: RuleDraftUpdateRequest) => {
  return request
    .patch<unknown, ApiResponse<RuleUpdateResponse>>(`/rules/${ruleKey}/draft`, data)
    .then((res) => res.data);
};

export const publish = (ruleKey: string) => {
  return request
    .post<unknown, ApiResponse<RulePublishResponse>>(`/rules/${ruleKey}/publish`)
    .then((res) => res.data);
};

export const rollback = (ruleKey: string, version: number) => {
  return request
    .post<unknown, ApiResponse<Rule>>(`/rules/${ruleKey}/rollback`, { version })
    .then((res) => res.data);
};

export const toggle = (ruleKey: string, enabled: boolean) => {
  return request
    .post<unknown, ApiResponse<Rule>>(`/rules/${ruleKey}/toggle`, { enabled })
    .then((res) => res.data);
};

export const runSelfTest = (data: RuleSelfTestCreateRequest) => {
  return request
    .post<unknown, ApiResponse<{ selftest_job_id: string }>>('/rules/selftest', data)
    .then((res) => res.data);
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

  return request
    .post<unknown, ApiResponse<{ selftest_job_id: string }>>('/rules/selftest/upload', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    })
    .then((res) => res.data);
};

export const getSelfTestJob = (jobId: string) => {
  return request
    .get<unknown, ApiResponse<SelfTestJob>>(`/rules/selftest/${jobId}`)
    .then((res) => res.data);
};

export const getSelfTestLogs = (jobId: string, params?: { stage?: string; tail?: number }) => {
  return request
    .get<unknown, ApiResponse<SelfTestLogsResponse>>(`/rules/selftest/${jobId}/logs`, { params })
    .then((res) => res.data);
};

export const getRuleSets = (params?: { page?: number; page_size?: number }) => {
  return request
    .get<unknown, ApiResponse<RuleSetListResponse>>('/rule-sets', { params })
    .then((res) => res.data);
};

export const getRuleSet = (ruleSetId: string) => {
  return request
    .get<unknown, ApiResponse<RuleSetDetail>>(`/rule-sets/${ruleSetId}`)
    .then((res) => res.data);
};

export const createRuleSet = (data: RuleSetCreateRequest) => {
  return request
    .post<unknown, ApiResponse<RuleSet>>('/rule-sets', data)
    .then((res) => res.data);
};

export const updateRuleSet = (ruleSetId: string, data: RuleSetUpdateRequest) => {
  return request
    .patch<unknown, ApiResponse<RuleSet>>(`/rule-sets/${ruleSetId}`, data)
    .then((res) => res.data);
};

export const bindRuleSetRules = (ruleSetId: string, ruleKeys: string[]) => {
  return request
    .post<unknown, ApiResponse<RuleSetDetail>>(`/rule-sets/${ruleSetId}/rules`, { rule_keys: ruleKeys })
    .then((res) => res.data);
};

export const getRuleStats = (params?: RuleStatsParams) => {
  return request
    .get<unknown, ApiResponse<RuleStatsListResponse>>('/rule-stats', { params })
    .then((res) => res.data);
};
