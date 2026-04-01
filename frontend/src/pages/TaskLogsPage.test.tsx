import { render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import TaskLogsPage from './TaskLogsPage';
import { downloadTaskLogs, getTaskLogs } from '../services/logCenter';
import { useAuthStore } from '../store/useAuthStore';

vi.mock('../services/logCenter', () => ({
  getTaskLogs: vi.fn(),
  downloadTaskLogs: vi.fn(),
}));

vi.mock('../store/useAuthStore', () => ({
  useAuthStore: vi.fn(),
}));

const mockedGetTaskLogs = vi.mocked(getTaskLogs);
const mockedDownloadTaskLogs = vi.mocked(downloadTaskLogs);
const mockedUseAuthStore = vi.mocked(useAuthStore);

let mockUserRole = 'User';

describe('TaskLogsPage', () => {
  beforeEach(() => {
    class ResizeObserverMock {
      observe() {}
      unobserve() {}
      disconnect() {}
    }

    vi.stubGlobal('ResizeObserver', ResizeObserverMock);
    vi.clearAllMocks();
    mockUserRole = 'User';

    mockedUseAuthStore.mockReturnValue({
      user: {
        id: 'user-1',
        email: 'tester@example.com',
        display_name: 'tester',
        role: mockUserRole,
      },
    } as ReturnType<typeof useAuthStore>);

    mockedGetTaskLogs.mockResolvedValue({
      request_id: 'req-task-logs',
      data: {
        task_type: 'SCAN',
        task_id: 'scan-job-1',
        items: [],
      },
      meta: {},
    });

    mockedDownloadTaskLogs.mockResolvedValue('scan-job-1.log');
  });

  it('falls back to SCAN for regular users and auto-runs deep-linked queries', async () => {
    render(
      <MemoryRouter initialEntries={['/task-logs?task_type=SELFTEST&task_id=scan-job-1&tail=120']}>
        <TaskLogsPage />
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(mockedGetTaskLogs).toHaveBeenCalledWith('SCAN', 'scan-job-1', {
        stage: undefined,
        tail: 120,
      });
    });

    expect(screen.getByText('任务日志')).toBeInTheDocument();
    expect(screen.queryByText('规则自测')).not.toBeInTheDocument();
  });

  it('keeps SELFTEST available for admins', async () => {
    mockUserRole = 'Admin';
    mockedUseAuthStore.mockReturnValue({
      user: {
        id: 'admin-1',
        email: 'admin@example.com',
        display_name: 'admin',
        role: mockUserRole,
      },
    } as ReturnType<typeof useAuthStore>);

    render(
      <MemoryRouter initialEntries={['/task-logs?task_type=SELFTEST&task_id=selftest-job-1']}>
        <TaskLogsPage />
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(mockedGetTaskLogs).toHaveBeenCalledWith('SELFTEST', 'selftest-job-1', {
        stage: undefined,
        tail: 200,
      });
    });

    expect(screen.getByText('规则自测')).toBeInTheDocument();
  });
});
