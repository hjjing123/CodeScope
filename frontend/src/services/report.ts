import request from '../utils/request';
import type {
  ReportContentPayload,
  ReportDeletePayload,
  ReportJobCreateRequest,
  ReportJobTriggerPayload,
  ReportListParams,
  ReportListPayload,
  ReportPayload,
} from '../types/report';
import type { Job } from '../types/scan';

export class ReportService {
  static async createReportJob(data: ReportJobCreateRequest): Promise<ReportJobTriggerPayload> {
    const res = await request.post('/report-jobs', data);
    return res.data;
  }

  static async listReports(params?: ReportListParams): Promise<ReportListPayload> {
    const res = await request.get('/reports', { params });
    return res.data;
  }

  static async getReport(reportId: string): Promise<ReportPayload> {
    const res = await request.get(`/reports/${reportId}`);
    return res.data;
  }

  static async getReportContent(reportId: string): Promise<ReportContentPayload> {
    const res = await request.get(`/reports/${reportId}/content`);
    return res.data;
  }

  static async downloadReport(reportId: string): Promise<Blob> {
    return request.get<Blob, Blob>(`/reports/${reportId}/download`, {
      responseType: 'blob',
    });
  }

  static async deleteReport(reportId: string): Promise<ReportDeletePayload> {
    const res = await request.delete(`/reports/${reportId}`);
    return res.data;
  }

  static async getReportJob(jobId: string): Promise<Job> {
    const res = await request.get(`/jobs/${jobId}`);
    return res.data;
  }
}
