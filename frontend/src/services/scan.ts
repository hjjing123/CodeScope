import request from '../utils/request';
import type {
  ScanJobCreateRequest,
  ScanJobDeletePayload,
  ScanJobDeleteRequest,
  Job,
  JobLog,
  JobTriggerPayload,
  JobActionPayload,
  JobListParams,
  JobListResponse,
} from '../types/scan';

export class ScanService {
  static async listJobs(params: JobListParams): Promise<JobListResponse> {
    const res = await request.get('/jobs', { params });
    return res.data;
  }

  static async createScanJob(
    projectId: string,
    payload: ScanJobCreateRequest
  ): Promise<JobTriggerPayload> {
    const res = await request.post('/scan-jobs', {
      ...payload,
      project_id: projectId,
    });
    return res.data;
  }

  static async getJob(jobId: string): Promise<Job> {
    const res = await request.get(`/jobs/${jobId}`);
    return res.data;
  }

  static async cancelJob(jobId: string): Promise<JobActionPayload> {
    const res = await request.post(`/jobs/${jobId}/cancel`);
    return res.data;
  }

  static async retryJob(jobId: string): Promise<JobTriggerPayload> {
    const res = await request.post(`/jobs/${jobId}/retry`);
    return res.data;
  }

  static async deleteJob(
    jobId: string,
    payload: ScanJobDeleteRequest
  ): Promise<ScanJobDeletePayload> {
    const res = await request.post(`/jobs/${jobId}/delete`, payload);
    return res.data;
  }

  static async getJobLogs(jobId: string, stage?: string, tail?: number): Promise<JobLog> {
    const res = await request.get(`/jobs/${jobId}/logs`, {
      params: { stage, tail },
    });
    return res.data;
  }

  static buildJobLogsStreamUrl(jobId: string, seq = 0): string {
    const params = new URLSearchParams({ seq: String(seq) });
    return `/api/v1/jobs/${jobId}/logs/stream?${params.toString()}`;
  }

  static buildJobEventsStreamUrl(jobId: string, afterId = 0): string {
    const params = new URLSearchParams({ after_id: String(afterId) });
    return `/api/v1/jobs/${jobId}/events/stream?${params.toString()}`;
  }
}
