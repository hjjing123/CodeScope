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
  result: string;
  summary_zh: string;
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

export interface AuditLogQuery {
  request_id?: string;
  actor_user_id?: string;
  action_group?: string;
  resource_type?: string;
  result?: string;
  keyword?: string;
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
  start_time?: string;
  end_time?: string;
  keyword?: string;
  action_group?: string;
}
