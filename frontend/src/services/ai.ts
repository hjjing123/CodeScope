import request from '../utils/request';
import { openSseStream, type SseEventPayload } from '../utils/sse';
import type {
  AIAssessmentChatSessionTriggerPayload,
  AIChatSessionDeletePayload,
  AIChatMessageCreateRequest,
  AIChatSessionCreateRequest,
  AIChatSessionPayload,
  AIEnrichmentJobPayload,
  AIModelCatalogPayload,
  AIProviderOptionsPayload,
  AIProviderSelectionRequest,
  AIProviderTestPayload,
  FindingAIAssessmentContextPayload,
  FindingAIAssessmentPayload,
  OllamaModelPayload,
  SystemOllamaConfigPayload,
  SystemOllamaConfigRequest,
  SystemOllamaPullJob,
  UserAIProviderCreateRequest,
  UserAIProviderPayload,
  UserAIProviderUpdateRequest,
} from '../types/ai';
import type { JobTriggerPayload } from '../types/scan';

export type AIChatStreamEvent =
  | SseEventPayload
  | {
      event: 'user_message' | 'assistant_delta' | 'assistant_message' | 'error' | 'done';
      data: unknown;
      id?: string;
    };

type ApiEnvelope<T> = { data: T };

const unwrap = async <T>(promise: Promise<ApiEnvelope<T>>): Promise<T> => {
  const response = await promise;
  return response.data;
};

export const getSystemOllamaConfig = async () =>
  unwrap<SystemOllamaConfigPayload>(request.get('/system/ai/ollama'));

export const updateSystemOllamaConfig = async (data: SystemOllamaConfigRequest) =>
  unwrap<SystemOllamaConfigPayload>(request.patch('/system/ai/ollama', data));

export const testSystemOllamaConfig = async () =>
  unwrap<AIProviderTestPayload>(request.post('/system/ai/ollama/test'));

export const listOllamaModels = async () =>
  unwrap<{ items: OllamaModelPayload[] }>(request.get('/system/ai/ollama/models'));

export const pullOllamaModel = async (name: string) =>
  unwrap<{ ok: boolean; result: Record<string, unknown> }>(
    request.post('/system/ai/ollama/pull', { name })
  );

export const listOllamaPullJobs = async (params: { active_only?: boolean; limit?: number } = {}) =>
  unwrap<{ items: SystemOllamaPullJob[]; total: number }>(
    request.get('/system/ai/ollama/pull-jobs', { params })
  );

export const deleteOllamaModel = async (name: string) =>
  unwrap<{ ok: boolean; result: Record<string, unknown> }>(
    request.delete(`/system/ai/ollama/models/${encodeURIComponent(name)}`)
  );

export const getMyAIOptions = async () =>
  unwrap<AIProviderOptionsPayload>(request.get('/me/ai/options'));

export const getMyAIModelCatalog = async () =>
  unwrap<AIModelCatalogPayload>(request.get('/me/ai/model-catalog'));

export const listMyAIProviders = async () =>
  unwrap<{ items: UserAIProviderPayload[]; total: number }>(request.get('/me/ai/providers'));

export const createMyAIProvider = async (data: UserAIProviderCreateRequest) =>
  unwrap<UserAIProviderPayload>(request.post('/me/ai/providers', data));

export const updateMyAIProvider = async (
  providerId: string,
  data: UserAIProviderUpdateRequest
) => unwrap<UserAIProviderPayload>(request.patch(`/me/ai/providers/${providerId}`, data));

export const deleteMyAIProvider = async (providerId: string) =>
  unwrap<{ ok: boolean; provider_id: string }>(request.delete(`/me/ai/providers/${providerId}`));

export const testMyAIProvider = async (providerId: string) =>
  unwrap<AIProviderTestPayload>(request.post(`/me/ai/providers/${providerId}/test`));

export const getScanAIEnrichment = async (jobId: string) =>
  unwrap<AIEnrichmentJobPayload>(request.get(`/jobs/${jobId}/ai-enrichment`));

export const listFindingAIAssessments = async (findingId: string) =>
  unwrap<{ items: FindingAIAssessmentPayload[]; total: number }>(
    request.get(`/findings/${findingId}/ai/assessments`)
  );

export const getLatestFindingAIAssessment = async (findingId: string) =>
  unwrap<FindingAIAssessmentPayload | null>(request.get(`/findings/${findingId}/ai/assessment/latest`));

export const getLatestFindingAIAssessmentContext = async (findingId: string) =>
  unwrap<FindingAIAssessmentContextPayload>(request.get(`/findings/${findingId}/ai/assessment/latest/context`));

export const retryFindingAI = async (
  findingId: string,
  data: AIProviderSelectionRequest
) => unwrap<JobTriggerPayload>(request.post(`/findings/${findingId}/ai/retry`, data));

export const createAssessmentSeedChatSession = async (findingId: string) =>
  unwrap<AIAssessmentChatSessionTriggerPayload>(
    request.post(`/findings/${findingId}/ai/chat/sessions/from-latest-assessment`)
  );

export const listMyChatSessions = async (findingId?: string) =>
  unwrap<{ items: AIChatSessionPayload[]; total: number }>(
    request.get('/me/ai/chat/sessions', { params: { finding_id: findingId } })
  );

export const createGeneralChatSession = async (data: AIChatSessionCreateRequest) =>
  unwrap<AIChatSessionPayload>(request.post('/me/ai/chat/sessions', data));

export const listFindingChatSessions = async (findingId: string) =>
  unwrap<{ items: AIChatSessionPayload[]; total: number }>(
    request.get(`/findings/${findingId}/ai/chat/sessions`)
  );

export const createChatSession = async (
  findingId: string,
  data: AIChatSessionCreateRequest
) => unwrap<AIChatSessionPayload>(request.post(`/findings/${findingId}/ai/chat/sessions`, data));

export const getChatSession = async (sessionId: string) =>
  unwrap<AIChatSessionPayload>(request.get(`/ai/chat/sessions/${sessionId}`));

export const deleteChatSession = async (sessionId: string) =>
  unwrap<AIChatSessionDeletePayload>(request.delete(`/ai/chat/sessions/${sessionId}`));

export const sendChatMessageStream = async (
  sessionId: string,
  data: AIChatMessageCreateRequest,
  options: {
    signal: AbortSignal;
    onEvent: (event: AIChatStreamEvent) => void;
  }
) =>
  openSseStream({
    url: `/api/v1/ai/chat/sessions/${sessionId}/messages/stream`,
    method: 'POST',
    body: JSON.stringify(data),
    signal: options.signal,
    onEvent: options.onEvent,
  });

export const updateChatSessionSelection = async (
  sessionId: string,
  data: AIProviderSelectionRequest
) => unwrap<AIChatSessionPayload>(request.patch(`/ai/chat/sessions/${sessionId}/selection`, data));
