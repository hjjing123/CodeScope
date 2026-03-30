export interface ReportJobCreateOptions {
  format: 'MARKDOWN';
  include_code_snippets: boolean;
  include_ai_sections: boolean;
}

export interface ReportJobCreateRequest {
  report_type: 'FINDING';
  generation_mode: 'JOB_ALL' | 'FINDING_SET';
  project_id: string;
  version_id: string;
  job_id: string;
  finding_ids?: string[];
  options?: ReportJobCreateOptions;
}

export interface ReportJobTriggerPayload {
  report_job_id: string;
  expected_report_count: number;
  bundle_expected: boolean;
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

export interface ReportJobArtifact {
  artifact_id: string;
  artifact_type: string;
  display_name: string;
  size_bytes?: number | null;
  source: string;
}

export interface ReportJobArtifactListPayload {
  job_id: string;
  items: ReportJobArtifact[];
}
