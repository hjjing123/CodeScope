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
  resource_type: string;
  resource_id: string;
  project_id: string | null;
  result: string;
  error_code: string | null;
  detail_json: Record<string, unknown>;
  created_at: string;
}

export interface RuntimeLogItem {
  id: string;
  occurred_at: string;
  level: string;
  service: string;
  module: string;
  event: string;
  message: string;
  request_id: string;
  operator_user_id: string | null;
  project_id: string | null;
  resource_type: string | null;
  resource_id: string | null;
  task_type: string | null;
  task_id: string | null;
  status_code: number | null;
  duration_ms: number | null;
  error_code: string | null;
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
  runtime_logs: RuntimeLogItem[];
  task_log_previews: TaskLogPreviewItem[];
}

export interface AuditLogQuery {
  request_id?: string;
  actor_user_id?: string;
  action?: string;
  resource_type?: string;
  project_id?: string;
  result?: string;
  error_code?: string;
  start_time?: string;
  end_time?: string;
  page?: number;
  page_size?: number;
}

export interface RuntimeLogQuery {
  level?: string;
  service?: string;
  module?: string;
  event?: string;
  request_id?: string;
  operator_user_id?: string;
  project_id?: string;
  task_type?: string;
  task_id?: string;
  status_code?: number;
  error_code?: string;
  start_time?: string;
  end_time?: string;
  page?: number;
  page_size?: number;
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
