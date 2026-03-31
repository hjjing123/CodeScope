import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import ReportHistoryTable from './ReportHistoryTable';
import { ReportService } from '../../services/report';
import type { ReportContentPayload, ReportPayload } from '../../types/report';

vi.mock('../../services/report', () => ({
  ReportService: {
    listReports: vi.fn(),
    getReportContent: vi.fn(),
    downloadReport: vi.fn(),
    deleteReport: vi.fn(),
  },
}));

const mockedListReports = vi.mocked(ReportService.listReports);
const mockedGetReportContent = vi.mocked(ReportService.getReportContent);
const mockedDownloadReport = vi.mocked(ReportService.downloadReport);
const mockedDeleteReport = vi.mocked(ReportService.deleteReport);

const buildReport = (overrides: Partial<ReportPayload> = {}): ReportPayload => ({
  id: 'report-1',
  project_id: 'project-1',
  version_id: 'version-1',
  job_id: 'job-1',
  report_job_id: 'report-job-1',
  finding_id: undefined,
  report_type: 'SCAN',
  status: 'DRAFT',
  format: 'MARKDOWN',
  object_key: 'jobs/report-job-1/generated/scan.md',
  file_name: 'scan.md',
  title: '统一扫描报告',
  template_key: 'standard_scan_v1',
  summary_text: '汇总 3 条漏洞，其中高危 1 条。',
  finding_count: 3,
  created_by: 'user-1',
  created_at: '2026-03-30T08:00:00Z',
  rule_key: undefined,
  vuln_type: undefined,
  vuln_display_name: undefined,
  severity: undefined,
  finding_status: undefined,
  entry_display: undefined,
  entry_kind: undefined,
  ...overrides,
});

const buildReportContent = (
  overrides: Partial<ReportContentPayload> = {}
): ReportContentPayload => ({
  report: buildReport(),
  content: '# 统一扫描报告\n\n## 一、报告概况',
  mime_type: 'text/markdown',
  ...overrides,
});

describe('ReportHistoryTable', () => {
  beforeEach(() => {
    class ResizeObserverMock {
      observe() {}
      unobserve() {}
      disconnect() {}
    }

    vi.stubGlobal('ResizeObserver', ResizeObserverMock);
    vi.clearAllMocks();
    mockedListReports.mockResolvedValue({
      items: [buildReport()],
      total: 1,
    });
    mockedGetReportContent.mockResolvedValue(buildReportContent());
    mockedDownloadReport.mockResolvedValue(new Blob(['demo']));
    mockedDeleteReport.mockResolvedValue({
      ok: true,
      report_id: 'report-1',
      report_job_id: 'report-job-1',
      remaining_report_count: 0,
      deleted_report_file: true,
      deleted_report_job_root: true,
      deleted_report_job_files_count: 1,
      deleted_task_log_index_count: 3,
      deleted_log_files_count: 3,
    });
  });

  const confirmReportDeletion = async (title: string) => {
    const deleteTriggers = screen.getAllByLabelText(`删除报告 ${title}`);
    fireEvent.click(deleteTriggers[0]);
    const deleteButtons = await screen.findAllByRole('button', { name: /删\s*除/ });
    fireEvent.click(deleteButtons[deleteButtons.length - 1]);
  };

  it('opens report preview from the list', async () => {
    render(<ReportHistoryTable filters={{}} />);

    expect(await screen.findByText('统一扫描报告')).toBeInTheDocument();

    fireEvent.click(await screen.findByRole('button', { name: /预览报告 统一扫描报告/i }));

    await waitFor(() => {
      expect(mockedGetReportContent).toHaveBeenCalledWith('report-1');
    });
    expect((await screen.findAllByText('Markdown 预览')).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/汇总 3 条漏洞，其中高危 1 条/).length).toBeGreaterThan(0);
  });

  it('auto-opens preview when initialPreviewReportId is provided', async () => {
    render(<ReportHistoryTable filters={{}} initialPreviewReportId="report-1" />);

    await waitFor(() => {
      expect(mockedGetReportContent).toHaveBeenCalledWith('report-1');
    });
    expect((await screen.findAllByText('Markdown 预览')).length).toBeGreaterThan(0);
  });

  it('deletes a report and refreshes the list', async () => {
    mockedListReports
      .mockResolvedValueOnce({ items: [buildReport()], total: 1 })
      .mockResolvedValueOnce({ items: [], total: 0 });

    render(
      <ReportHistoryTable filters={{}} initialPreviewReportId="report-1" />
    );

    await waitFor(() => {
      expect(mockedGetReportContent).toHaveBeenCalledWith('report-1');
    });

    await confirmReportDeletion('统一扫描报告');

    await waitFor(() => {
      expect(mockedDeleteReport).toHaveBeenCalledWith('report-1');
    });
    await waitFor(() => {
      expect(mockedListReports).toHaveBeenCalledTimes(2);
    });
  });
});
