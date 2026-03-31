export interface ReportJobCreateOptions {
  format: 'MARKDOWN';
  include_code_snippets: boolean;
  include_ai_sections: boolean;
}

export interface ReportJobCreateRequest {
  report_type: 'SCAN' | 'FINDING';
  project_id: string;
  version_id: string;
  job_id: string;
  finding_id?: string;
  options?: ReportJobCreateOptions;
}

export interface ReportJobTriggerPayload {
  report_job_id: string;
  report_type: 'SCAN' | 'FINDING';
  finding_count: number;
}

export interface ReportPayload {
  id: string;
  project_id: string;
  version_id?: string;
  job_id?: string;
  report_job_id?: string;
  finding_id?: string;
  report_type: string;
  status: string;
  format: string;
  object_key?: string;
  file_name?: string;
  title?: string;
  template_key?: string;
  summary_text?: string;
  finding_count?: number | null;
  created_by?: string;
  created_at: string;
  rule_key?: string;
  vuln_type?: string;
  vuln_display_name?: string;
  severity?: string;
  finding_status?: string;
  entry_display?: string;
  entry_kind?: string;
}

export interface ReportListPayload {
  items: ReportPayload[];
  total: number;
}

export interface ReportContentPayload {
  report: ReportPayload;
  content: string;
  mime_type: 'text/markdown';
}

export interface ReportDeletePayload {
  ok: boolean;
  report_id: string;
  report_job_id?: string;
  remaining_report_count: number;
  deleted_report_file: boolean;
  deleted_report_job_root: boolean;
  deleted_report_job_files_count: number;
  deleted_task_log_index_count: number;
  deleted_log_files_count: number;
}

export interface ReportListParams {
  project_id?: string;
  version_id?: string;
  job_id?: string;
  report_job_id?: string;
  finding_id?: string;
  report_type?: string;
  page?: number;
  page_size?: number;
}
