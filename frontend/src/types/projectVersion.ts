export interface ApiResponse<T> {
  request_id: string;
  data: T;
  meta: Record<string, unknown>;
}

export interface ProjectCreateRequest {
  name: string;
  description?: string;
}

export interface ProjectUpdateRequest {
  description?: string;
}

export interface Project {
  id: string;
  name: string;
  description?: string | null;
  status: string;
  baseline_version_id?: string | null;
  my_project_role?: string | null;
  created_at: string;
  updated_at: string;
}

export interface ProjectListResponse {
  items: Project[];
  total: number;
}

export interface VersionCreateRequest {
  name: string;
  source: string;
  note?: string | null;
  tag?: string | null;
  git_repo_url?: string | null;
  git_ref?: string | null;
  baseline_of_version_id?: string | null;
  snapshot_object_key?: string | null;
}

export interface Version {
  id: string;
  project_id: string;
  name: string;
  source: string;
  note?: string | null;
  tag?: string | null;
  git_repo_url?: string | null;
  git_ref?: string | null;
  baseline_of_version_id?: string | null;
  snapshot_object_key?: string | null;
  status: string;
  is_baseline: boolean;
  created_at: string;
  updated_at: string;
}

export interface VersionListResponse {
  items: Version[];
  total: number;
  baseline_version_id?: string | null;
}

export interface VersionBaselineResponse {
  project_id: string;
  baseline_version_id: string;
}

export interface VersionTreeEntry {
  name: string;
  path: string;
  node_type: 'dir' | 'file';
  size_bytes?: number | null;
}

export interface VersionTreeResponse {
  root_path: string;
  items: VersionTreeEntry[];
}

export interface VersionFileResponse {
  path: string;
  content: string;
  truncated: boolean;
  total_lines: number;
}

export interface GitImportRequest {
  repo_url: string;
  ref_type: string;
  ref_value: string;
  credential_id?: string | null;
  version_name?: string | null;
  note?: string | null;
}

export interface GitImportTestRequest {
  repo_url: string;
  ref_type: string;
  ref_value: string;
  credential_id?: string | null;
}

export interface ImportJobTriggerResponse {
  import_job_id: string;
  idempotent_replay: boolean;
}

export interface ImportJob {
  id: string;
  project_id: string;
  version_id?: string | null;
  import_type: string;
  payload: Record<string, unknown>;
  status: string;
  stage: string;
  failure_code?: string | null;
  failure_hint?: string | null;
  created_by?: string | null;
  created_at: string;
  updated_at: string;
}

export interface GitImportTestResponse {
  ok: boolean;
  resolved_ref: string;
}

export interface TaskLogEntry {
  stage: string;
  lines: string[];
  line_count: number;
  truncated: boolean;
}

export interface TaskLogResponse {
  task_type: string;
  task_id: string;
  items: TaskLogEntry[];
}
