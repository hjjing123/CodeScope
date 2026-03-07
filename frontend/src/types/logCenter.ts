export type TaskType = 'SCAN' | 'IMPORT' | 'SELFTEST';

export interface ApiResponse<T> {
  request_id: string;
  data: T;
  meta: Record<string, unknown>;
}

export interface PagedPayload<T> {
  items: T[];
  total: number;
}

export interface AuditLogItem {
  id: string;
  request_id: string;
  operator_user_id: string | null;
  action: string;
  action_zh: string;
  action_group: string;
  resource_type: string;
  resource_id: string;
  project_id: string | null;
  result: string;
  error_code: string | null;
  summary_zh: string;
  is_high_value: boolean;
  detail_json: Record<string, unknown>;
  created_at: string;
}

export interface TaskLogEntry {
  stage: string;
  lines: string[];
  line_count: number;
  truncated: boolean;
}

export interface TaskLogPayload {
  task_type: string;
  task_id: string;
  items: TaskLogEntry[];
}

export interface TaskLogPreviewItem {
  task_type: string;
  task_id: string;
  stage: string;
  line_count: number;
  size_bytes: number;
  updated_at: string;
}

export interface LogCorrelationPayload {
  audit_logs: AuditLogItem[];
  task_log_previews: TaskLogPreviewItem[];
}

export interface AuditLogQuery {
  request_id?: string;
  actor_user_id?: string;
  action?: string;
  action_group?: string;
  resource_type?: string;
  project_id?: string;
  result?: string;
  error_code?: string;
  keyword?: string;
  high_value_only?: boolean;
  start_time?: string;
  end_time?: string;
  page?: number;
  page_size?: number;
}

export interface BatchDeleteLogsPayload {
  log_kind?: 'OPERATION';
  request_id?: string;
  task_type?: string;
  task_id?: string;
  project_id?: string;
  start_time?: string;
  end_time?: string;
  keyword?: string;
  action_group?: string;
  high_value_only?: boolean;
}

export interface CorrelationQuery {
  request_id?: string;
  task_type?: string;
  task_id?: string;
  project_id?: string;
  start_time?: string;
  end_time?: string;
  limit?: number;
}
