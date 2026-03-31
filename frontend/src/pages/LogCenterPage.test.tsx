import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import LogCenterPage from './LogCenterPage';
import {
  batchDeleteLogs,
  deleteSingleLog,
  downloadTaskLogs,
  getAuditLogs,
  getLogCorrelation,
  getTaskLogs,
} from '../services/logCenter';

vi.mock('../services/logCenter', () => ({
  getAuditLogs: vi.fn(),
  getLogCorrelation: vi.fn(),
  getTaskLogs: vi.fn(),
  deleteSingleLog: vi.fn(),
  batchDeleteLogs: vi.fn(),
  downloadTaskLogs: vi.fn(),
}));

const mockedGetAuditLogs = vi.mocked(getAuditLogs);
const mockedGetLogCorrelation = vi.mocked(getLogCorrelation);
const mockedGetTaskLogs = vi.mocked(getTaskLogs);
const mockedDeleteSingleLog = vi.mocked(deleteSingleLog);
const mockedBatchDeleteLogs = vi.mocked(batchDeleteLogs);
const mockedDownloadTaskLogs = vi.mocked(downloadTaskLogs);

describe('LogCenterPage', () => {
  beforeEach(() => {
    class ResizeObserverMock {
      observe() {}
      unobserve() {}
      disconnect() {}
    }

    vi.stubGlobal('ResizeObserver', ResizeObserverMock);
    vi.clearAllMocks();

    mockedGetAuditLogs.mockResolvedValue({
      data: {
        items: [
          {
            id: 'log-1',
            request_id: 'req-1',
            operator_user_id: 'user-1',
            action: 'auth.revoke',
            action_zh: 'Session revoked',
            action_group: 'AUTH',
            resource_type: 'SESSION',
            resource_id: 'session-1',
            project_id: null,
            result: 'SUCCEEDED',
            error_code: null,
            summary_zh: 'Signed out session',
            is_high_value: true,
            detail_json: {},
            created_at: '2026-03-30T14:24:31Z',
          },
        ],
        total: 1,
      },
      request_id: 'req-page',
      meta: {},
    });
    mockedGetLogCorrelation.mockResolvedValue({
      data: {
        audit_logs: [],
        task_log_previews: [],
      },
      request_id: 'req-correlation',
      meta: {},
    });
    mockedGetTaskLogs.mockResolvedValue({
      data: {
        task_type: 'SCAN',
        task_id: 'task-1',
        items: [],
      },
      request_id: 'req-task',
      meta: {},
    });
    mockedDeleteSingleLog.mockResolvedValue({
      data: { deleted: true, deleted_count: 1 },
      request_id: 'req-delete',
      meta: {},
    });
    mockedBatchDeleteLogs.mockResolvedValue({
      data: { deleted_count: 1 },
      request_id: 'req-batch',
      meta: {},
    });
    mockedDownloadTaskLogs.mockResolvedValue('scan_task-1.log');
  });

  it('hides resource and request_id from the visible log center UI', async () => {
    render(<LogCenterPage />);

    await waitFor(() => {
      expect(mockedGetAuditLogs).toHaveBeenCalledTimes(1);
    });

    expect(screen.queryByRole('columnheader', { name: /request_id/i })).toBeNull();
    expect(screen.getAllByRole('columnheader')).toHaveLength(7);

    fireEvent.click(screen.getAllByRole('tab')[2]);

    const hiddenRequestIdInput = screen.queryByPlaceholderText('request_id');
    if (hiddenRequestIdInput) {
      expect(hiddenRequestIdInput).not.toBeVisible();
    }

    expect(screen.queryByRole('columnheader', { name: /request_id/i })).toBeNull();
  });
});
