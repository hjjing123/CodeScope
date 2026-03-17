export type AISource = 'system_ollama' | 'user_external';

export interface AIProviderSelectionRequest {
  ai_source?: AISource;
  ai_provider_id?: string;
  ai_model?: string;
}

export interface SystemOllamaConfigPayload {
  id: string | null;
  provider_key: string;
  display_name: string;
  provider_type: string;
  base_url: string;
  enabled: boolean;
  default_model: string | null;
  published_models: string[];
  timeout_seconds: number;
  temperature: number;
  is_configured: boolean;
  auto_configured: boolean;
  connection_ok?: boolean | null;
  connection_detail: Record<string, unknown>;
  created_at: string | null;
  updated_at: string | null;
}

export interface SystemOllamaConfigRequest {
  display_name: string;
  base_url: string;
  enabled: boolean;
  default_model?: string | null;
  published_models?: string[];
  timeout_seconds: number;
  temperature: number;
}

export interface OllamaModelPayload {
  name: string;
  size?: number | null;
  digest?: string | null;
  modified_at?: string | null;
  details: Record<string, unknown>;
}

export type SystemOllamaPullJobStatus =
  | 'PENDING'
  | 'RUNNING'
  | 'SUCCEEDED'
  | 'FAILED'
  | 'CANCELED'
  | 'TIMEOUT';

export type SystemOllamaPullJobStage = 'Prepare' | 'Pull' | 'Verify' | 'Finalize';

export interface SystemOllamaPullJobProgress {
  phase?: string | null;
  status_text?: string | null;
  percent?: number | null;
  completed?: number | null;
  total?: number | null;
  digest?: string | null;
  verified?: boolean;
}

export interface SystemOllamaPullJob {
  id: string;
  provider_id: string;
  model_name: string;
  status: SystemOllamaPullJobStatus;
  stage: SystemOllamaPullJobStage;
  failure_code?: string | null;
  failure_hint?: string | null;
  progress: SystemOllamaPullJobProgress;
  result_summary: Record<string, unknown>;
  created_by?: string | null;
  started_at?: string | null;
  finished_at?: string | null;
  created_at: string;
  updated_at: string;
}

export interface AIProviderTestPayload {
  ok: boolean;
  provider_type: string;
  provider_label: string;
  detail: Record<string, unknown>;
}

export interface UserAIProviderPayload {
  id: string;
  user_id: string;
  display_name: string;
  vendor_name: string;
  provider_type: string;
  base_url: string;
  default_model: string;
  timeout_seconds: number;
  temperature: number;
  enabled: boolean;
  is_default: boolean;
  has_api_key: boolean;
  api_key_masked?: string | null;
  created_at: string;
  updated_at: string;
}

export interface UserAIProviderCreateRequest {
  display_name: string;
  vendor_name: string;
  base_url: string;
  api_key: string;
  default_model: string;
  timeout_seconds: number;
  temperature: number;
  enabled: boolean;
  is_default: boolean;
}

export interface UserAIProviderUpdateRequest {
  display_name?: string;
  vendor_name?: string;
  base_url?: string;
  api_key?: string;
  default_model?: string;
  timeout_seconds?: number;
  temperature?: number;
  enabled?: boolean;
  is_default?: boolean;
}

export interface SystemAIOptionPayload {
  available: boolean;
  provider_key: string;
  display_name: string;
  provider_type: string;
  default_model?: string | null;
  published_models: string[];
  connection_ok?: boolean | null;
}

export interface AIProviderOptionsPayload {
  system_ollama: SystemAIOptionPayload;
  user_providers: UserAIProviderPayload[];
  default_selection: Record<string, unknown>;
}

export interface AISelectableModelPayload {
  name: string;
  label: string;
  is_default: boolean;
  details: Record<string, unknown>;
}

export interface AIModelCatalogProviderPayload {
  provider_source: string;
  provider_id: string | null;
  provider_key: string | null;
  provider_label: string;
  provider_type: string;
  enabled: boolean;
  models: AISelectableModelPayload[];
}

export interface AIModelCatalogPayload {
  items: AIModelCatalogProviderPayload[];
  default_selection: Record<string, unknown>;
}

export interface FindingAIAssessmentPayload {
  id: string;
  finding_id: string;
  job_id: string;
  scan_job_id?: string | null;
  project_id: string;
  version_id: string;
  provider_source: string;
  provider_type: string;
  provider_label: string;
  model_name: string;
  status: string;
  summary_json: Record<string, unknown>;
  response_text?: string | null;
  error_code?: string | null;
  error_message?: string | null;
  created_by?: string | null;
  created_at: string;
  updated_at: string;
}

export interface AIEnrichmentJobSummary {
  id: string;
  status: string;
  stage: string;
  failure_code?: string | null;
  failure_stage?: string | null;
  failure_hint?: string | null;
  created_at: string;
  updated_at: string;
  finished_at?: string | null;
  result_summary: Record<string, unknown>;
}

export interface AIEnrichmentJobPayload {
  scan_job_id: string;
  enabled: boolean;
  latest_job_id?: string | null;
  latest_status?: string | null;
  jobs: AIEnrichmentJobSummary[];
}

export interface AIChatMessagePayload {
  id: string;
  session_id: string;
  role: 'user' | 'assistant' | string;
  content: string;
  meta_json: Record<string, unknown>;
  created_at: string;
}

export interface AIChatSessionPayload {
  id: string;
  session_mode: 'general' | 'finding_context' | string;
  finding_id: string | null;
  project_id: string | null;
  version_id: string | null;
  provider_source: string;
  provider_type: string;
  provider_label: string;
  model_name: string;
  title: string | null;
  provider_snapshot: Record<string, unknown>;
  created_by: string | null;
  created_at: string;
  updated_at: string;
  messages: AIChatMessagePayload[];
}

export interface AIChatSessionDeletePayload {
  ok: boolean;
  session_id: string;
}

export interface AIChatSessionCreateRequest extends AIProviderSelectionRequest {
  title?: string;
}

export interface AIChatMessageCreateRequest {
  content: string;
}
