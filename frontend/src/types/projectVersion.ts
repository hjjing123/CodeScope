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
  snapshot_object_key?: string | null;
  status: string;
  created_at: string;
  updated_at: string;
}

export interface VersionListResponse {
  items: Version[];
  total: number;
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
  ref_type?: string | null;
  ref_value?: string | null;
  repo_visibility?: 'public' | 'private' | null;
  auth_type?: 'none' | 'https_token' | 'ssh_key' | null;
  username?: string | null;
  access_token?: string | null;
  ssh_private_key?: string | null;
  ssh_passphrase?: string | null;
  credential_id?: string | null;
  version_name?: string | null;
  note?: string | null;
}

export interface GitImportTestRequest {
  repo_url: string;
  ref_type?: string | null;
  ref_value?: string | null;
  repo_visibility?: 'public' | 'private' | null;
  auth_type?: 'none' | 'https_token' | 'ssh_key' | null;
  username?: string | null;
  access_token?: string | null;
  ssh_private_key?: string | null;
  ssh_passphrase?: string | null;
  credential_id?: string | null;
}

export interface ImportJobTriggerResponse {
  import_job_id: string;
  idempotent_replay: boolean;
}

export interface ScanJobCreateRequest {
  project_id: string;
  version_id: string;
  rule_set_keys?: string[];
  rule_keys?: string[];
  note?: string;
}

export interface ScanJobTriggerResponse {
  job_id: string;
  idempotent_replay: boolean;
}

export interface ImportJobProgressStage {
  stage: string;
  display_name: string;
  order: number;
  status: string;
}

export interface ImportJobProgress {
  current_stage: string;
  percent: number;
  completed_stages: number;
  total_stages: number;
  is_terminal: boolean;
  stages: ImportJobProgressStage[];
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
  progress?: ImportJobProgress;
  result_summary?: Record<string, unknown>;
  created_by?: string | null;
  created_at: string;
  updated_at: string;
}

export interface GitImportTestResponse {
  ok: boolean;
  resolved_ref: string;
  resolved_ref_type: string;
  resolved_ref_value: string;
  auto_detected: boolean;
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
