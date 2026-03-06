import request from '../utils/request';
import { getAuthToken } from '../utils/authToken';
import type {
  ApiResponse,
  AuditLogItem,
  AuditLogQuery,
  BatchDeleteLogsPayload,
  CorrelationQuery,
  LogCorrelationPayload,
  PagedPayload,
  RuntimeLogItem,
  RuntimeLogQuery,
  TaskLogPayload,
  TaskType,
} from '../types/logCenter';

const resolveTaskPath = (taskType: TaskType, taskId: string): string => {
  if (taskType === 'SCAN') {
    return `/jobs/${taskId}`;
  }
  if (taskType === 'IMPORT') {
    return `/import-jobs/${taskId}`;
  }
  return `/rules/selftest/${taskId}`;
};

export const getAuditLogs = (params: AuditLogQuery) => {
  return request.get<any, ApiResponse<PagedPayload<AuditLogItem>>>('/audit-logs', { params });
};

export const getRuntimeLogs = (params: RuntimeLogQuery) => {
  return request.get<any, ApiResponse<PagedPayload<RuntimeLogItem>>>('/runtime-logs', { params });
};

export const getLogCorrelation = (params: CorrelationQuery) => {
  return request.get<any, ApiResponse<LogCorrelationPayload>>('/log-center/correlation', { params });
};

export const getTaskLogs = (
  taskType: TaskType,
  taskId: string,
  params: { stage?: string; tail?: number }
) => {
  const path = resolveTaskPath(taskType, taskId);
  return request.get<any, ApiResponse<TaskLogPayload>>(`${path}/logs`, { params });
};

export const deleteSingleLog = (logId: string) => {
  return request.delete<any, ApiResponse<{ deleted: boolean; deleted_count: number }>>(
    `/log-center/logs/${logId}`
  );
};

export const batchDeleteLogs = (payload: BatchDeleteLogsPayload) => {
  return request.post<any, ApiResponse<{ deleted_count: number }>>(
    '/log-center/logs/batch-delete',
    payload
  );
};

const parseFilenameFromHeader = (contentDisposition: string | null): string | null => {
  if (!contentDisposition) {
    return null;
  }

  const utf8Match = contentDisposition.match(/filename\*=UTF-8''([^;]+)/i);
  if (utf8Match?.[1]) {
    return decodeURIComponent(utf8Match[1].replace(/\"/g, ''));
  }

  const simpleMatch = contentDisposition.match(/filename="?([^\";]+)"?/i);
  if (simpleMatch?.[1]) {
    return simpleMatch[1];
  }

  return null;
};

export const downloadTaskLogs = async (
  taskType: TaskType,
  taskId: string,
  stage?: string
): Promise<string> => {
  const token = getAuthToken();
  const path = resolveTaskPath(taskType, taskId);
  const url = new URL(`/api/v1${path}/logs/download`, window.location.origin);
  if (stage && stage.trim()) {
    url.searchParams.set('stage', stage.trim());
  }

  const response = await fetch(url.toString(), {
    method: 'GET',
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });

  if (!response.ok) {
    let message = '日志下载失败';
    try {
      const errorPayload = await response.json();
      if (errorPayload?.error?.message) {
        message = String(errorPayload.error.message);
      }
    } catch {
      // Ignore JSON parse failures for binary responses.
    }
    throw new Error(message);
  }

  const blob = await response.blob();
  const contentDisposition = response.headers.get('content-disposition');
  const fallbackName = stage ? `${taskType.toLowerCase()}_${taskId}_${stage}.log` : `${taskType.toLowerCase()}_${taskId}_logs.zip`;
  const fileName = parseFilenameFromHeader(contentDisposition) ?? fallbackName;

  const blobUrl = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = blobUrl;
  anchor.download = fileName;
  document.body.appendChild(anchor);
  anchor.click();
  document.body.removeChild(anchor);
  URL.revokeObjectURL(blobUrl);
  return fileName;
};
