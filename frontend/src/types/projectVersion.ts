export interface ApiResponse<T> {
  request_id: string;
  data: T;
  meta: Record<string, unknown>;
}

export type ProjectStatus = 'NEW' | 'IMPORTED' | 'SCANNABLE';
export type ProjectRole = 'Owner' | 'Maintainer' | 'Reader';

export interface ProjectPayload {
  id: string;
  name: string;
  description: string | null;
  status: ProjectStatus;
  baseline_version_id: string | null;
  my_project_role: ProjectRole | null;
  created_at: string;
  updated_at: string;
}

export interface ProjectListPayload {
  items: ProjectPayload[];
  total: number;
}

export interface ProjectCreateRequest {
  name: string;
  description?: string | null;
}

export interface ProjectUpdateRequest {
  description?: string | null;
}

export type VersionSource = 'UPLOAD' | 'GIT' | 'PATCHED';
export type VersionStatus = 'READY' | 'ARCHIVED' | 'DELETED';

export interface VersionPayload {
  id: string;
  project_id: string;
  name: string;
  source: VersionSource;
  note: string | null;
  tag: string | null;
  git_repo_url: string | null;
  git_ref: string | null;
  baseline_of_version_id: string | null;
  snapshot_object_key: string | null;
  status: VersionStatus;
  is_baseline: boolean;
  created_at: string;
  updated_at: string;
}

export interface VersionListPayload {
  items: VersionPayload[];
  total: number;
  baseline_version_id: string | null;
}

export interface VersionCreateRequest {
  name: string;
  source: VersionSource;
  note?: string | null;
  tag?: string | null;
  git_repo_url?: string | null;
  git_ref?: string | null;
  baseline_of_version_id?: string | null;
  snapshot_object_key: string;
}

export interface VersionBaselinePayload {
  project_id: string;
  baseline_version_id: string;
}

export interface VersionTreeEntryPayload {
  name: string;
  path: string;
  node_type: 'dir' | 'file';
  size_bytes: number | null;
}

export interface VersionTreePayload {
  root_path: string;
  items: VersionTreeEntryPayload[];
}

export interface VersionFilePayload {
  path: string;
  content: string;
  truncated: boolean;
  total_lines: number;
}

export type ImportType = 'UPLOAD' | 'GIT';
export type ImportJobStatus = 'PENDING' | 'RUNNING' | 'SUCCEEDED' | 'FAILED' | 'CANCELED' | 'TIMEOUT';

export interface ImportJobPayload {
  id: string;
  project_id: string;
  version_id: string | null;
  import_type: ImportType;
  payload: Record<string, unknown>;
  status: ImportJobStatus;
  stage: string;
  failure_code: string | null;
  failure_hint: string | null;
  created_by: string | null;
  created_at: string;
  updated_at: string;
}

export interface ImportJobTriggerPayload {
  import_job_id: string;
  idempotent_replay: boolean;
}

export interface GitImportRequest {
  repo_url: string;
  ref_type: 'branch' | 'tag' | 'commit';
  ref_value: string;
  credential_id?: string | null;
  version_name?: string | null;
  note?: string | null;
}

export interface GitImportTestRequest {
  repo_url: string;
  ref_type: 'branch' | 'tag' | 'commit';
  ref_value: string;
  credential_id?: string | null;
}

export interface GitImportTestPayload {
  ok: boolean;
  resolved_ref: string;
}

export interface TaskLogEntryPayload {
  stage: string;
  lines: string[];
  line_count: number;
  truncated: boolean;
}

export interface TaskLogPayload {
  task_type: string;
  task_id: string;
  items: TaskLogEntryPayload[];
}
