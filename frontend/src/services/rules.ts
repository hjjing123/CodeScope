import request from '../utils/request';
import type { ApiResponse, TaskLogResponse } from '../types/projectVersion';
import type {
  Rule,
  RuleCreateRequest,
  RuleDraftUpdateRequest,
  RuleSelfTestCreateRequest,
  RuleSet,
  RuleSetCreateRequest,
  RuleSetDetail,
  RuleSetUpdateRequest,
  RuleStats,
  RuleVersion,
} from '../types/rule';

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

export interface RuleQueryParams {
  page?: number;
  page_size?: number;
  name?: string;
  search?: string;
  vuln_type?: string;
  enabled?: boolean;
}

export interface RuleSetQueryParams {
  page?: number;
  page_size?: number;
}

export interface RuleStatsQueryParams {
  rule_key?: string;
  metric_date_from?: string;
  metric_date_to?: string;
  page?: number;
  page_size?: number;
}

export interface SelfTestTriggerPayload {
  selftest_job_id: string;
}

export interface SelfTestLogItem {
  timestamp: string;
  level: string;
  message: string;
  stage: string;
}

export interface SelfTestLogsResponse {
  task_type: string;
  task_id: string;
  items: SelfTestLogItem[];
}

interface RuleDraftUpdateResponse {
  rule: Rule;
  draft_version: RuleVersion;
}

interface RulePublishResponse {
  rule: Rule;
  published_version: RuleVersion;
}

interface RuleRequestOptions {
  skipErrorToast?: boolean;
}

const unwrapData = <T>(promise: Promise<ApiResponse<T>>): Promise<T> => {
  return promise.then((response) => response.data);
};

const parseTaskLogLine = (line: string): Omit<SelfTestLogItem, 'stage'> => {
  const match = line.match(/^\[([^\]]+)\]\s*(.*)$/);
  const timestamp = match?.[1] ?? '';
  const message = match?.[2] ?? line;
  const normalized = message.toLowerCase();

  let level = 'INFO';
  if (normalized.includes('error') || normalized.includes('failed') || normalized.includes('失败')) {
    level = 'ERROR';
  } else if (
    normalized.includes('warn') ||
    normalized.includes('timeout') ||
    normalized.includes('超时')
  ) {
    level = 'WARN';
  }

  return {
    timestamp,
    level,
    message,
  };
};

const flattenSelfTestLogs = (payload: TaskLogResponse): SelfTestLogsResponse => {
  return {
    task_type: payload.task_type,
    task_id: payload.task_id,
    items: payload.items.flatMap((entry) =>
      entry.lines.map((line) => ({
        ...parseTaskLogLine(line),
        stage: entry.stage,
      }))
    ),
  };
};

export const getRules = (params: RuleQueryParams = {}) => {
  return unwrapData(request.get<unknown, ApiResponse<RuleListResponse>>('/rules', { params }));
};

export const getRuleDetails = (ruleKey: string, options: RuleRequestOptions = {}) => {
  return unwrapData(request.get<unknown, ApiResponse<Rule>>(`/rules/${ruleKey}`, options));
};

export const getRuleVersions = (ruleKey: string, options: RuleRequestOptions = {}) => {
  return unwrapData(
    request.get<unknown, ApiResponse<RuleVersionListResponse>>(`/rules/${ruleKey}/versions`, options)
  );
};

export const createRule = (payload: RuleCreateRequest) => {
  return unwrapData(request.post<unknown, ApiResponse<Rule>>('/rules', payload));
};

export const updateDraft = (ruleKey: string, payload: RuleDraftUpdateRequest) => {
  return unwrapData(
    request.patch<unknown, ApiResponse<RuleDraftUpdateResponse>>(`/rules/${ruleKey}/draft`, payload)
  );
};

export const publish = (ruleKey: string) => {
  return unwrapData(
    request.post<unknown, ApiResponse<RulePublishResponse>>(`/rules/${ruleKey}/publish`)
  );
};

export const rollback = (ruleKey: string, version: number) => {
  return unwrapData(
    request.post<unknown, ApiResponse<Rule>>(`/rules/${ruleKey}/rollback`, { version })
  );
};

export const toggle = (ruleKey: string, enabled: boolean) => {
  return unwrapData(
    request.post<unknown, ApiResponse<Rule>>(`/rules/${ruleKey}/toggle`, { enabled })
  );
};

export const getRuleSets = (params: RuleSetQueryParams = {}) => {
  return unwrapData(
    request.get<unknown, ApiResponse<RuleSetListResponse>>('/rule-sets', { params })
  );
};

export const getRuleSet = (ruleSetId: string) => {
  return unwrapData(request.get<unknown, ApiResponse<RuleSetDetail>>(`/rule-sets/${ruleSetId}`));
};

export const createRuleSet = (payload: RuleSetCreateRequest) => {
  return unwrapData(request.post<unknown, ApiResponse<RuleSet>>('/rule-sets', payload));
};

export const updateRuleSet = (ruleSetId: string, payload: RuleSetUpdateRequest) => {
  return unwrapData(
    request.patch<unknown, ApiResponse<RuleSet>>(`/rule-sets/${ruleSetId}`, payload)
  );
};

export const bindRuleSetRules = (ruleSetId: string, ruleKeys: string[]) => {
  return unwrapData(
    request.post<unknown, ApiResponse<RuleSetDetail>>(`/rule-sets/${ruleSetId}/rules`, {
      rule_keys: ruleKeys,
    })
  );
};

export const getRuleStats = (params: RuleStatsQueryParams = {}) => {
  return unwrapData(
    request.get<unknown, ApiResponse<RuleStatsListResponse>>('/rule-stats', { params })
  );
};

export const runSelfTest = (payload: RuleSelfTestCreateRequest) => {
  return unwrapData(
    request.post<unknown, ApiResponse<SelfTestTriggerPayload>>('/rules/selftest', payload)
  );
};

export const runSelfTestWithUpload = (
  file: File,
  payload: Omit<RuleSelfTestCreateRequest, 'version_id'>
) => {
  const formData = new FormData();
  formData.append('file', file);

  if (payload.rule_key) {
    formData.append('rule_key', payload.rule_key);
  }
  if (payload.rule_version !== undefined) {
    formData.append('rule_version', String(payload.rule_version));
  }
  if (payload.draft_payload) {
    formData.append('draft_payload', JSON.stringify(payload.draft_payload));
  }

  return unwrapData(
    request.post<unknown, ApiResponse<SelfTestTriggerPayload>>('/rules/selftest/upload', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    })
  );
};

export const getSelfTestJob = (jobId: string) => {
  return unwrapData(request.get<unknown, ApiResponse<unknown>>(`/rules/selftest/${jobId}`));
};

export const getSelfTestLogs = (jobId: string, params?: { stage?: string; tail?: number }) => {
  return unwrapData(
    request.get<unknown, ApiResponse<TaskLogResponse>>(`/rules/selftest/${jobId}/logs`, {
      params,
    })
  ).then(flattenSelfTestLogs);
};
