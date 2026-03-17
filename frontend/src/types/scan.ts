export interface ScanJobCreateRequest {
  project_id: string;
  version_id: string;
  rule_set_keys?: string[];
  rule_keys?: string[];
  note?: string;
  ai_enabled?: boolean;
  ai_source?: string;
  ai_provider_id?: string;
  ai_model?: string;
}

export interface JobStep {
  step_key: string;
  display_name: string;
  step_order: number;
  status: string;
  started_at?: string | null;
  finished_at?: string | null;
  duration_ms?: number | null;
}

export interface JobProgress {
  total_steps: number;
  completed_steps: number;
  percent: number;
  current_step?: string | null;
}

export type JobResultSummary = Record<string, unknown>;

export interface Job {
  id: string;
  project_id: string;
  version_id: string;
  job_type: string;
  payload: Record<string, unknown>;
  status: string;
  stage: string;
  failure_code?: string | null;
  failure_stage?: string | null;
  failure_category?: string | null;
  failure_hint?: string | null;
  progress: JobProgress;
  steps: JobStep[];
  result_summary: JobResultSummary;
  created_by?: string | null;
  started_at?: string | null;
  finished_at?: string | null;
  created_at: string;
  updated_at: string;
}

export interface JobLogEntry {
  stage: string;
  lines: string[];
  line_count: number;
  truncated: boolean;
}

export interface JobLog {
  job_id: string;
  items: JobLogEntry[];
}

export interface JobListParams {
  project_id?: string;
  version_id?: string;
  status?: string;
  job_type?: string;
  page?: number;
  page_size?: number;
}

export interface JobListResponse {
  items: Job[];
  total: number;
}

export interface JobTriggerPayload {
  job_id: string;
  idempotent_replay: boolean;
}

export interface JobActionPayload {
  ok: boolean;
  job_id: string;
  status: string;
}

export type ScanJobDeleteTarget =
  | 'logs'
  | 'artifacts'
  | 'workspace'
  | 'findings'
  | 'job_record';

export interface ScanJobDeleteRequest {
  targets: ScanJobDeleteTarget[];
}

export interface ScanJobDeletePayload {
  ok: boolean;
  job_id: string;
  deleted_targets: ScanJobDeleteTarget[];
  forced_targets: ScanJobDeleteTarget[];
  warnings: string[];
  deleted_findings_count: number;
  deleted_job_steps_count: number;
  deleted_task_log_index_count: number;
  deleted_log_files_count: number;
  deleted_archive_files_count: number;
  deleted_report_files_count: number;
  deleted_workspace_paths_count: number;
  deleted_job_record: boolean;
}
