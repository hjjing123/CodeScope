import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import LogCenterPage from './LogCenterPage';
import { logCenterActionGroupOptions } from './logCenterOptions';
import {
  batchDeleteLogs,
  deleteSingleLog,
  downloadTaskLogs,
  getAuditLogs,
  getTaskLogs,
} from '../services/logCenter';
import { ScanService } from '../services/scan';
import { useAuthStore } from '../store/useAuthStore';

vi.mock('../services/logCenter', () => ({
  getAuditLogs: vi.fn(),
  getTaskLogs: vi.fn(),
  deleteSingleLog: vi.fn(),
  batchDeleteLogs: vi.fn(),
  downloadTaskLogs: vi.fn(),
}));

vi.mock('../services/scan', () => ({
  ScanService: {
    listJobs: vi.fn(),
  },
}));

vi.mock('../store/useAuthStore', () => ({
  useAuthStore: vi.fn(),
}));

const mockedGetAuditLogs = vi.mocked(getAuditLogs);
const mockedGetTaskLogs = vi.mocked(getTaskLogs);
const mockedDeleteSingleLog = vi.mocked(deleteSingleLog);
const mockedBatchDeleteLogs = vi.mocked(batchDeleteLogs);
const mockedDownloadTaskLogs = vi.mocked(downloadTaskLogs);
const mockedListJobs = vi.mocked(ScanService.listJobs);
const mockedUseAuthStore = vi.mocked(useAuthStore);

let mockUserRole = 'Admin';

const baseAuditItem = {
  id: 'log-1',
  request_id: 'req-1',
  operator_user_id: 'user-1',
  action: 'auth.revoke',
  action_zh: '撤销会话',
  action_group: 'AUTH',
  resource_type: 'SESSION',
  resource_id: 'session-1',
  result: 'SUCCEEDED',
  summary_zh: '撤销会话',
  detail_json: { source: 'test' },
  created_at: '2026-03-30T14:24:31Z',
};

const recentScanJob = {
  id: 'scan-job-1',
  project_id: 'project-1',
  project_name: 'Demo Project',
  version_id: 'version-1',
  version_name: 'v1',
  job_type: 'SCAN',
  payload: {},
  status: 'SUCCEEDED',
  stage: 'aggregate',
  progress: {
    total_steps: 4,
    completed_steps: 4,
    percent: 100,
  },
  steps: [],
  result_summary: {},
  created_at: '2026-03-31T12:00:00Z',
  updated_at: '2026-03-31T12:05:00Z',
  started_at: '2026-03-31T12:00:30Z',
  finished_at: '2026-03-31T12:05:00Z',
} satisfies Awaited<ReturnType<typeof ScanService.listJobs>>['items'][number];

const LocationProbe = () => {
  const location = useLocation();
  return <div data-testid="location-search">{location.search}</div>;
};

const renderLogCenterPage = (initialEntry = '/log-center') =>
  render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <Routes>
        <Route
          path="/log-center"
          element={
            <>
              <LogCenterPage />
              <LocationProbe />
            </>
          }
        />
      </Routes>
    </MemoryRouter>
  );

const getActiveTaskPanel = (container: HTMLElement): HTMLElement => {
  const activePanel = container.querySelector<HTMLElement>('.ant-tabs-tabpane-active');

  if (!activePanel) {
    throw new Error('Active task panel not found');
  }

  return activePanel;
};

describe('LogCenterPage', () => {
  beforeEach(() => {
    class ResizeObserverMock {
      observe() {}
      unobserve() {}
      disconnect() {}
    }

    vi.stubGlobal('ResizeObserver', ResizeObserverMock);
    vi.clearAllMocks();
    mockUserRole = 'Admin';
    mockedUseAuthStore.mockReturnValue({
      user: {
        id: 'user-1',
        email: 'tester@example.com',
        display_name: 'tester',
        role: mockUserRole,
      },
    } as ReturnType<typeof useAuthStore>);

    mockedGetAuditLogs.mockResolvedValue({
      data: {
        items: [baseAuditItem],
        total: 1,
      },
      request_id: 'req-page',
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
    mockedListJobs.mockResolvedValue({
      items: [recentScanJob],
      total: 1,
    });
  });

  it('renders only audit and task tabs after simplification', async () => {
    renderLogCenterPage();

    await waitFor(() => {
      expect(mockedGetAuditLogs).toHaveBeenCalledTimes(1);
    });

    expect(screen.getAllByRole('tab')).toHaveLength(2);

    fireEvent.click(screen.getAllByRole('tab')[1]);
    expect(screen.getByPlaceholderText('task_id (UUID)')).toBeTruthy();
  });

  it('renders chinese AI audit actions and exposes AI/system filters', async () => {
    mockedGetAuditLogs.mockResolvedValueOnce({
      data: {
        items: [
          {
            id: 'log-ai-1',
            request_id: 'req-ai-1',
            operator_user_id: 'user-1',
            action: 'ai.chat.session.created',
            action_zh: '创建通用 AI 会话',
            action_group: 'ai',
            resource_type: 'AI_CHAT_SESSION',
            resource_id: 'session-1',
            result: 'SUCCEEDED',
            summary_zh: '创建通用 AI 会话',
            detail_json: {},
            created_at: '2026-03-30T14:24:31Z',
          },
        ],
        total: 1,
      },
      request_id: 'req-ai-page',
      meta: {},
    });

    renderLogCenterPage();

    await waitFor(() => {
      expect(mockedGetAuditLogs).toHaveBeenCalledTimes(1);
    });

    expect(screen.getByText('ai.chat.session.created')).toBeTruthy();
    expect(logCenterActionGroupOptions.map((option) => option.value)).toEqual(
      expect.arrayContaining(['AI', 'SYSTEM'])
    );
  });

  it('keeps action codes visible while deprecated audit columns stay removed', async () => {
    const { container } = renderLogCenterPage();

    await waitFor(() => {
      expect(mockedGetAuditLogs).toHaveBeenCalledTimes(1);
    });

    expect(container.querySelector('input[placeholder="项目 ID"]')).toBeNull();
    expect(container.querySelector('input[placeholder="动作编码"]')).toBeNull();
    expect(container.textContent).not.toContain('高价值');
    expect(container.textContent).not.toContain('错误码');
    expect(screen.getAllByText('auth.revoke').length).toBeGreaterThan(0);

    fireEvent.click(screen.getAllByText('auth.revoke')[0]);

    await waitFor(() => {
      expect(screen.getByRole('dialog')).toBeTruthy();
    });

    expect(screen.getAllByText('auth.revoke').length).toBeGreaterThan(0);
  });

  it('hides audit log delete actions for regular users', async () => {
    mockUserRole = 'User';
    mockedUseAuthStore.mockReturnValue({
      user: {
        id: 'user-1',
        email: 'tester@example.com',
        display_name: 'tester',
        role: mockUserRole,
      },
    } as ReturnType<typeof useAuthStore>);

    const { container } = renderLogCenterPage();

    await waitFor(() => {
      expect(mockedGetAuditLogs).toHaveBeenCalledTimes(1);
    });

    expect(container.querySelectorAll('.ant-btn-dangerous')).toHaveLength(0);

    fireEvent.click(screen.getAllByText('auth.revoke')[0]);

    await waitFor(() => {
      expect(screen.getByRole('dialog')).toBeTruthy();
    });

    expect(container.querySelectorAll('.ant-btn-dangerous')).toHaveLength(0);
  });

  it('keeps audit log delete actions visible for admins', async () => {
    const { container } = renderLogCenterPage();

    await waitFor(() => {
      expect(mockedGetAuditLogs).toHaveBeenCalledTimes(1);
    });

    expect(container.querySelectorAll('.ant-btn-dangerous').length).toBeGreaterThan(0);
  });

  it('auto-runs task log queries from url params', async () => {
    const view = renderLogCenterPage('/log-center?tab=task&task_type=SCAN&task_id=scan-job-1&tail=120');

    await waitFor(() => {
      expect(mockedGetTaskLogs).toHaveBeenCalledWith('SCAN', 'scan-job-1', {
        stage: undefined,
        tail: 120,
      });
    });

    expect(within(getActiveTaskPanel(view.container)).getByDisplayValue('scan-job-1')).toBeInTheDocument();
  });

  it('shows recent scan tasks instead of the old empty state', async () => {
    const view = renderLogCenterPage('/log-center?tab=task');

    await waitFor(() => {
      expect(mockedGetAuditLogs).toHaveBeenCalledTimes(1);
    });

    await waitFor(() => {
      expect(mockedListJobs).toHaveBeenCalled();
    });

    expect((await within(view.container).findAllByText('Recent Scan Tasks')).length).toBeGreaterThan(0);
    expect(
      within(getActiveTaskPanel(view.container)).queryByText(
        'Failed to load recent scan tasks. You can still search by task ID.'
      )
    ).not.toBeInTheDocument();
  });

  it('clicking a recent scan fetches logs', async () => {
    const view = renderLogCenterPage();

    await waitFor(() => {
      expect(mockedGetAuditLogs).toHaveBeenCalledTimes(1);
    });

    fireEvent.click(within(view.container).getAllByRole('tab')[1]);

    const [viewLogsButton] = await within(view.container).findAllByText('View Logs');
    fireEvent.click(viewLogsButton);

    await waitFor(() => {
      expect(mockedGetTaskLogs).toHaveBeenCalledWith('SCAN', 'scan-job-1', {
        stage: undefined,
        tail: 200,
      });
    });
    expect(within(getActiveTaskPanel(view.container)).getByTestId('task-log-reset-button')).toBeInTheDocument();
  });

  it('returns to recent scans after clicking the reset button', async () => {
    const view = renderLogCenterPage('/log-center?tab=task&task_type=SCAN&task_id=scan-job-1&tail=120');

    await waitFor(() => {
      expect(mockedGetTaskLogs).toHaveBeenCalledWith('SCAN', 'scan-job-1', {
        stage: undefined,
        tail: 120,
      });
    });

    expect(within(getActiveTaskPanel(view.container)).getByTestId('task-log-download-current')).not.toBeDisabled();
    expect(within(getActiveTaskPanel(view.container)).getByTestId('task-log-download-all')).not.toBeDisabled();

    fireEvent.click(within(getActiveTaskPanel(view.container)).getByTestId('task-log-reset-button'));

    await waitFor(() => {
      expect(within(view.container).getByTestId('location-search')).toHaveTextContent('?tab=task');
    });

    expect((await within(view.container).findAllByText('Recent Scan Tasks')).length).toBeGreaterThan(0);
    expect(within(getActiveTaskPanel(view.container)).getByPlaceholderText('task_id (UUID)')).toHaveValue('');
    expect(within(getActiveTaskPanel(view.container)).getByRole('spinbutton')).toHaveValue('200');
    expect(within(getActiveTaskPanel(view.container)).getByTestId('task-log-download-current')).toBeDisabled();
    expect(within(getActiveTaskPanel(view.container)).getByTestId('task-log-download-all')).toBeDisabled();
    expect(within(getActiveTaskPanel(view.container)).queryByText('请输入任务 ID')).not.toBeInTheDocument();
  });

  it('clearing task_id returns the task log tab to the initial state', async () => {
    const view = renderLogCenterPage('/log-center?tab=task&task_type=SCAN&task_id=scan-job-1&tail=120');

    await waitFor(() => {
      expect(mockedGetTaskLogs).toHaveBeenCalledWith('SCAN', 'scan-job-1', {
        stage: undefined,
        tail: 120,
      });
    });

    const taskIdInput = within(getActiveTaskPanel(view.container)).getByDisplayValue('scan-job-1');
    fireEvent.change(taskIdInput, {
      target: { value: '' },
    });

    await waitFor(() => {
      expect(within(view.container).getByTestId('location-search')).toHaveTextContent('?tab=task');
    });

    expect((await within(view.container).findAllByText('Recent Scan Tasks')).length).toBeGreaterThan(0);
    expect(within(getActiveTaskPanel(view.container)).getByPlaceholderText('task_id (UUID)')).toHaveValue('');
    expect(within(getActiveTaskPanel(view.container)).queryByTestId('task-log-reset-button')).not.toBeInTheDocument();
    expect(within(getActiveTaskPanel(view.container)).queryByText('请输入任务 ID')).not.toBeInTheDocument();
    expect(
      within(getActiveTaskPanel(view.container)).queryByText(
        'Failed to load recent scan tasks. You can still search by task ID.'
      )
    ).not.toBeInTheDocument();
  });

  it('manual task queries still work', async () => {
    const view = renderLogCenterPage();

    await waitFor(() => {
      expect(mockedGetAuditLogs).toHaveBeenCalledTimes(1);
    });

    fireEvent.click(within(view.container).getAllByRole('tab')[1]);
    const taskIdInput = within(getActiveTaskPanel(view.container)).getByPlaceholderText('task_id (UUID)');
    expect(taskIdInput).toBeTruthy();

    fireEvent.change(taskIdInput!, {
      target: { value: 'scan-job-2' },
    });
    fireEvent.submit(taskIdInput!.closest('form')!);

    await waitFor(() => {
      expect(mockedGetTaskLogs).toHaveBeenCalledWith(
        'SCAN',
        'scan-job-2',
        expect.objectContaining({
          stage: undefined,
        })
      );
    });

  });

  it('keeps manual search available when recent scans fail to load', async () => {
    mockedListJobs.mockRejectedValueOnce(new Error('network'));

    const view = renderLogCenterPage();

    await waitFor(() => {
      expect(mockedGetAuditLogs).toHaveBeenCalledTimes(1);
    });

    fireEvent.click(within(view.container).getAllByRole('tab')[1]);

    const taskIdInput = within(getActiveTaskPanel(view.container)).getByPlaceholderText('task_id (UUID)');
    expect(taskIdInput).toBeTruthy();

    fireEvent.change(taskIdInput!, {
      target: { value: 'scan-job-3' },
    });
    fireEvent.submit(taskIdInput!.closest('form')!);

    await waitFor(() => {
      expect(mockedGetTaskLogs).toHaveBeenCalledWith(
        'SCAN',
        'scan-job-3',
        expect.objectContaining({
          stage: undefined,
        })
      );
    });
  });
});
