export interface Finding {
  id: string;
  project_id: string;
  version_id: string;
  job_id: string;
  rule_key: string;
  rule_version?: number | null;
  vuln_type?: string | null;
  severity: string;
  status: string;
  file_path?: string | null;
  line_start?: number | null;
  line_end?: number | null;
  has_path: boolean;
  path_length?: number | null;
  source_file?: string | null;
  source_line?: number | null;
  sink_file?: string | null;
  sink_line?: number | null;
  evidence_json: Record<string, unknown>;
  created_at: string;
}

export interface FindingListParams {
  project_id?: string;
  version_id?: string;
  job_id?: string;
  severity?: string;
  vuln_type?: string;
  status?: string;
  file_prefix?: string;
  q?: string;
  sort_by?: string;
  sort_order?: string;
  page?: number;
  page_size?: number;
}

export interface FindingListResponse {
  items: Finding[];
  total: number;
}

export interface ProjectResultOverview {
  project_id: string;
  version_id?: string | null;
  job_id?: string | null;
  total_findings: number;
  severity_dist: Record<string, number>;
  status_dist: Record<string, number>;
  top_vuln_types: Array<{ vuln_type: string; count: number }>;
}

export interface FindingLabelRequest {
  status: string;
  fp_reason?: string | null;
  comment?: string | null;
}

export interface FindingLabel {
  id: string;
  finding_id: string;
  status: string;
  fp_reason?: string | null;
  comment?: string | null;
  created_by?: string | null;
  created_at: string;
}

export interface FindingLabelActionResponse {
  finding: Finding;
  label: FindingLabel;
}

export interface FindingPathStep {
  step_id: number;
  labels: string[];
  file?: string | null;
  line?: number | null;
  func_name?: string | null;
  code_snippet?: string | null;
  node_ref: string;
}

export interface FindingPath {
  path_id: number;
  path_length: number;
  steps: FindingPathStep[];
}

export interface FindingPathListResponse {
  finding_id: string;
  mode: string;
  items: FindingPath[];
}

export interface FindingPathNodeContext {
  finding_id: string;
  step_id: number;
  file: string;
  line: number;
  start_line: number;
  end_line: number;
  lines: string[];
}
