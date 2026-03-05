import request from '../utils/request';
import { getAuthToken } from '../utils/authToken';
import type {
  ApiResponse,
  GitImportRequest,
  GitImportTestPayload,
  GitImportTestRequest,
  ImportJobPayload,
  ImportJobTriggerPayload,
  ProjectCreateRequest,
  ProjectListPayload,
  ProjectPayload,
  ProjectUpdateRequest,
  TaskLogPayload,
  VersionBaselinePayload,
  VersionCreateRequest,
  VersionFilePayload,
  VersionListPayload,
  VersionPayload,
  VersionTreePayload,
} from '../types/projectVersion';

interface PaginationParams {
  page?: number;
  page_size?: number;
}

interface UploadImportParams {
  version_name?: string;
  note?: string;
}

const parseFilenameFromHeader = (contentDisposition: string | null): string | null => {
  if (!contentDisposition) {
    return null;
  }

  const utf8Match = contentDisposition.match(/filename\*=UTF-8''([^;]+)/i);
  if (utf8Match?.[1]) {
    return decodeURIComponent(utf8Match[1].replace(/"/g, ''));
  }

  const simpleMatch = contentDisposition.match(/filename="?([^";]+)"?/i);
  if (simpleMatch?.[1]) {
    return simpleMatch[1];
  }

  return null;
};

const downloadByPath = async (path: string, fallbackName: string): Promise<string> => {
  const token = getAuthToken();
  const url = new URL(path, window.location.origin);

  const response = await fetch(url.toString(), {
    method: 'GET',
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });

  if (!response.ok) {
    let message = '文件下载失败';
    try {
      const payload = await response.json();
      if (payload?.error?.message) {
        message = String(payload.error.message);
      }
    } catch {
      // ignore
    }
    throw new Error(message);
  }

  const blob = await response.blob();
  const contentDisposition = response.headers.get('content-disposition');
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

export const getProjects = (params: PaginationParams) => {
  return request.get<unknown, ApiResponse<ProjectListPayload>>('/projects', { params });
};

export const createProject = (data: ProjectCreateRequest) => {
  return request.post<unknown, ApiResponse<ProjectPayload>>('/projects', data);
};

export const updateProject = (projectId: string, data: ProjectUpdateRequest) => {
  return request.patch<unknown, ApiResponse<ProjectPayload>>(`/projects/${projectId}`, data);
};

export const deleteProject = (projectId: string) => {
  return request.delete<unknown, ApiResponse<{ deleted: boolean }>>(`/projects/${projectId}`);
};

export const getVersions = (projectId: string, params: PaginationParams) => {
  return request.get<unknown, ApiResponse<VersionListPayload>>(`/projects/${projectId}/versions`, { params });
};

export const createVersion = (projectId: string, data: VersionCreateRequest) => {
  return request.post<unknown, ApiResponse<VersionPayload>>(`/projects/${projectId}/versions`, data);
};

export const getVersion = (versionId: string) => {
  return request.get<unknown, ApiResponse<VersionPayload>>(`/versions/${versionId}`);
};

export const setVersionBaseline = (versionId: string) => {
  return request.post<unknown, ApiResponse<VersionBaselinePayload>>(`/versions/${versionId}/baseline`);
};

export const archiveVersion = (versionId: string) => {
  return request.post<unknown, ApiResponse<{ archived: boolean }>>(`/versions/${versionId}/archive`);
};

export const deleteVersion = (versionId: string) => {
  return request.delete<unknown, ApiResponse<{ deleted: boolean }>>(`/versions/${versionId}`);
};

export const getVersionTree = (versionId: string, path?: string) => {
  return request.get<unknown, ApiResponse<VersionTreePayload>>(`/versions/${versionId}/tree`, {
    params: { path },
  });
};

export const getVersionFile = (versionId: string, path: string) => {
  return request.get<unknown, ApiResponse<VersionFilePayload>>(`/versions/${versionId}/file`, {
    params: { path },
  });
};

export const downloadVersionSnapshot = async (versionId: string): Promise<string> => {
  return downloadByPath(`/api/v1/versions/${versionId}/download`, `version_${versionId}_snapshot.tar.gz`);
};

export const uploadImportArchive = (
  projectId: string,
  file: File,
  params: UploadImportParams,
  idempotencyKey?: string
) => {
  const formData = new FormData();
  formData.append('file', file);

  const headers: Record<string, string> = {};
  if (idempotencyKey && idempotencyKey.trim()) {
    headers['Idempotency-Key'] = idempotencyKey.trim();
  }

  return request.post<unknown, ApiResponse<ImportJobTriggerPayload>>(
    `/projects/${projectId}/imports/upload`,
    formData,
    {
      params,
      headers,
    }
  );
};

export const triggerGitImport = (projectId: string, payload: GitImportRequest, idempotencyKey?: string) => {
  const headers: Record<string, string> = {};
  if (idempotencyKey && idempotencyKey.trim()) {
    headers['Idempotency-Key'] = idempotencyKey.trim();
  }
  return request.post<unknown, ApiResponse<ImportJobTriggerPayload>>(`/projects/${projectId}/imports/git`, payload, {
    headers,
  });
};

export const testGitImportSource = (projectId: string, payload: GitImportTestRequest) => {
  return request.post<unknown, ApiResponse<GitImportTestPayload>>(`/projects/${projectId}/imports/git/test`, payload);
};

export const triggerGitSync = (projectId: string, note?: string, idempotencyKey?: string) => {
  const headers: Record<string, string> = {};
  if (idempotencyKey && idempotencyKey.trim()) {
    headers['Idempotency-Key'] = idempotencyKey.trim();
  }
  return request.post<unknown, ApiResponse<ImportJobTriggerPayload>>(
    `/projects/${projectId}/imports/git/sync`,
    null,
    {
      params: { note },
      headers,
    }
  );
};

export const getImportJob = (jobId: string) => {
  return request.get<unknown, ApiResponse<ImportJobPayload>>(`/import-jobs/${jobId}`);
};

export const getImportJobLogs = (jobId: string, params: { stage?: string; tail?: number }) => {
  return request.get<unknown, ApiResponse<TaskLogPayload>>(`/import-jobs/${jobId}/logs`, { params });
};

export const downloadImportJobLogs = async (jobId: string, stage?: string): Promise<string> => {
  const search = new URLSearchParams();
  if (stage && stage.trim()) {
    search.set('stage', stage.trim());
  }
  const path = `/api/v1/import-jobs/${jobId}/logs/download${search.toString() ? `?${search.toString()}` : ''}`;
  const fallbackName = stage ? `${jobId}_${stage}.log` : `import_job_${jobId}_logs.zip`;
  return downloadByPath(path, fallbackName);
};
