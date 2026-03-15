import type { AxiosProgressEvent } from 'axios';

import request from '../utils/request';
import type {
  ApiResponse,
  Project,
  ProjectCreateRequest,
  ProjectListResponse,
  ProjectUpdateRequest,
  Version,
  VersionCreateRequest,
  VersionFileResponse,
  VersionListResponse,
  VersionTreeResponse,
  GitImportRequest,
  GitImportTestRequest,
  GitImportTestResponse,
  ImportJobTriggerResponse,
  ImportJob,
  ScanJobCreateRequest,
  ScanJobTriggerResponse,
  TaskLogResponse,
} from '../types/projectVersion';

type PageQuery = {
  page: number;
  page_size: number;
};

// Projects
export const getProjects = (params: PageQuery) => {
  return request.get<unknown, ApiResponse<ProjectListResponse>>('/projects', { params });
};

export const createProject = (data: ProjectCreateRequest) => {
  return request.post<unknown, ApiResponse<Project>>('/projects', data);
};

export const getProject = (id: string) => {
  return request.get<unknown, ApiResponse<Project>>(`/projects/${id}`);
};

export const updateProject = (id: string, data: ProjectUpdateRequest) => {
  return request.patch<unknown, ApiResponse<Project>>(`/projects/${id}`, data);
};

export const deleteProject = (id: string) => {
  return request.delete<unknown, ApiResponse<{ deleted: boolean }>>(`/projects/${id}`);
};

// Versions
export const getVersions = (projectId: string, params: PageQuery) => {
  return request.get<unknown, ApiResponse<VersionListResponse>>(
    `/projects/${projectId}/versions`,
    { params }
  );
};

export const createVersion = (projectId: string, data: VersionCreateRequest) => {
  return request.post<unknown, ApiResponse<Version>>(`/projects/${projectId}/versions`, data);
};

export const getVersion = (versionId: string) => {
  return request.get<unknown, ApiResponse<Version>>(`/versions/${versionId}`);
};

export const archiveVersion = (versionId: string) => {
  return request.post<unknown, ApiResponse<{ archived: boolean }>>(`/versions/${versionId}/archive`);
};

export const deleteVersion = (versionId: string) => {
  return request.delete<unknown, ApiResponse<{ deleted: boolean }>>(`/versions/${versionId}`);
};

export const triggerScanJob = (data: ScanJobCreateRequest) => {
  return request.post<unknown, ApiResponse<ScanJobTriggerResponse>>('/scan-jobs', data);
};

// Source Browser
export const getVersionTree = (versionId: string, path = '') => {
  return request.get<unknown, ApiResponse<VersionTreeResponse>>(`/versions/${versionId}/tree`, {
    params: { path },
  });
};

export const getVersionFile = (versionId: string, path: string) => {
  return request.get<unknown, ApiResponse<VersionFileResponse>>(`/versions/${versionId}/file`, {
    params: { path },
  });
};

export const downloadVersionSnapshot = (versionId: string) => {
  return request.get<Blob, Blob>(`/versions/${versionId}/download`, { responseType: 'blob' });
};

// Imports
export const triggerGitImport = (projectId: string, data: GitImportRequest) => {
  return request.post<unknown, ApiResponse<ImportJobTriggerResponse>>(
    `/projects/${projectId}/imports/git`,
    data
  );
};

export const triggerGitSync = (projectId: string, params?: { note?: string }) => {
  return request.post<unknown, ApiResponse<ImportJobTriggerResponse>>(
    `/projects/${projectId}/imports/git/sync`,
    null,
    { params }
  );
};

export const uploadImportFile = (
  projectId: string,
  file: File,
  params: { version_name?: string; note?: string },
  options?: { onUploadProgress?: (event: AxiosProgressEvent) => void }
) => {
  const formData = new FormData();
  formData.append('file', file);
  if (params.version_name) formData.append('version_name', params.version_name);
  if (params.note) formData.append('note', params.note);

  return request.post<unknown, ApiResponse<ImportJobTriggerResponse>>(
    `/projects/${projectId}/imports/upload`,
    formData,
    {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
      timeout: 30 * 60 * 1000,
      onUploadProgress: options?.onUploadProgress,
    }
  );
};

export const testGitImport = (projectId: string, data: GitImportTestRequest) => {
  return request.post<unknown, ApiResponse<GitImportTestResponse>>(
    `/projects/${projectId}/imports/git/test`,
    data
  );
};

export const getImportJob = (jobId: string) => {
  return request.get<unknown, ApiResponse<ImportJob>>(`/import-jobs/${jobId}`);
};

export const getImportJobLogs = (jobId: string, params?: { stage?: string; tail?: number }) => {
  return request.get<unknown, ApiResponse<TaskLogResponse>>(`/import-jobs/${jobId}/logs`, {
    params,
  });
};
