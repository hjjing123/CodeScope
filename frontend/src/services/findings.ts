import request from '../utils/request';
import type {
  Finding,
  FindingListResponse,
  FindingListParams,
  ProjectResultOverview,
  FindingLabelRequest,
  FindingLabelActionResponse,
  FindingPathListResponse,
  FindingPathNodeContext,
  ScanResultListParams,
  ScanResultListResponse,
} from '../types/finding';

export class FindingService {
  static async listScanResults(params: ScanResultListParams): Promise<ScanResultListResponse> {
    const res = await request.get('/scan-results', { params });
    return res.data;
  }

  static async getProjectResults(
    projectId: string,
    versionId?: string,
    jobId?: string
  ): Promise<ProjectResultOverview> {
    const res = await request.get(`/projects/${projectId}/results`, {
      params: { version_id: versionId, job_id: jobId },
    });
    return res.data;
  }

  static async listFindings(params: FindingListParams): Promise<FindingListResponse> {
    const res = await request.get('/findings', { params });
    return res.data;
  }

  static async getFinding(findingId: string): Promise<Finding> {
    const res = await request.get(`/findings/${findingId}`);
    return res.data;
  }

  static async labelFinding(
    findingId: string,
    payload: FindingLabelRequest
  ): Promise<FindingLabelActionResponse> {
    const res = await request.post(`/findings/${findingId}/labels`, payload);
    return res.data;
  }

  static async getFindingPaths(
    findingId: string,
    params?: { mode?: 'shortest' | 'all'; limit?: number }
  ): Promise<FindingPathListResponse> {
    const res = await request.get(`/findings/${findingId}/paths`, {
      params,
      skipErrorToast: true,
    });
    return res.data;
  }

  static async getPathNodeContext(
    findingId: string,
    stepId: number
  ): Promise<FindingPathNodeContext> {
    const res = await request.get(`/findings/${findingId}/path-nodes/${stepId}/context`, {
      skipErrorToast: true,
    });
    return res.data;
  }
}
