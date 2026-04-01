import { fireEvent, render, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import DashboardPage from './DashboardPage';
import { getProjects } from '../services/projectVersion';
import { ScanService } from '../services/scan';
import { FindingService } from '../services/findings';
import { getAuditLogs } from '../services/logCenter';
import { useAuthStore } from '../store/useAuthStore';

const navigateMock = vi.fn();

vi.mock('../services/projectVersion', () => ({
  getProjects: vi.fn(),
}));

vi.mock('../services/scan', () => ({
  ScanService: {
    listJobs: vi.fn(),
  },
}));

vi.mock('../services/findings', () => ({
  FindingService: {
    listFindings: vi.fn(),
  },
}));

vi.mock('../services/logCenter', () => ({
  getAuditLogs: vi.fn(),
}));

vi.mock('../store/useAuthStore', () => ({
  useAuthStore: vi.fn(),
}));

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom');
  return {
    ...actual,
    useNavigate: () => navigateMock,
  };
});

const mockedGetProjects = vi.mocked(getProjects);
const mockedListJobs = vi.mocked(ScanService.listJobs);
const mockedListFindings = vi.mocked(FindingService.listFindings);
const mockedGetAuditLogs = vi.mocked(getAuditLogs);
const mockedUseAuthStore = vi.mocked(useAuthStore);

let mockUserRole = 'Admin';

const mockRecentScans = [
  {
    id: 'scan-job-1',
    project_id: 'project-1',
    project_name: 'Demo Project',
    status: 'SUCCEEDED',
    created_at: '2026-03-31T08:00:00Z',
  },
  {
    id: 'scan-job-2',
    project_id: 'project-2',
    project_name: 'Another Project',
    status: 'RUNNING',
    created_at: '2026-03-31T07:30:00Z',
  },
];

describe('DashboardPage', () => {
  beforeEach(() => {
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

    mockedGetProjects.mockResolvedValue({
      request_id: 'req-projects',
      data: {
        items: [],
        total: 3,
      },
      meta: {},
    });

    mockedListJobs.mockResolvedValue({
      items: mockRecentScans as Awaited<ReturnType<typeof ScanService.listJobs>>['items'],
      total: mockRecentScans.length,
    });

    mockedListFindings.mockResolvedValue({
      items: [
        {
          id: 'finding-1',
          project_id: 'project-1',
          rule_key: 'Weak Password',
          severity: 'medium',
          created_at: '2026-03-31T08:05:00Z',
        },
      ] as Awaited<ReturnType<typeof FindingService.listFindings>>['items'],
      total: 1,
    });

    mockedGetAuditLogs.mockResolvedValue({
      request_id: 'req-audits',
      data: {
        items: [
          {
            id: 'audit-1',
            request_id: 'req-audit-1',
            operator_user_id: 'user-self',
            action: 'finding.label',
            action_zh: '标记漏洞',
            action_group: 'finding',
            resource_type: 'FINDING',
            resource_id: 'finding-1',
            result: 'SUCCEEDED',
            summary_zh: '标记漏洞',
            detail_json: {},
            created_at: '2026-03-31T08:10:00Z',
          },
        ],
        total: 1,
      },
      meta: {},
    });
  });

  it('renders recent audit activity for admins and keeps the audit card clickable', async () => {
    const view = render(<DashboardPage />);
    const scoped = within(view.container);

    await waitFor(() => {
      expect(mockedGetProjects).toHaveBeenCalledTimes(1);
      expect(mockedListJobs).toHaveBeenCalledTimes(1);
      expect(mockedListFindings).toHaveBeenCalledTimes(1);
      expect(mockedGetAuditLogs).toHaveBeenCalledWith({ page: 1, page_size: 10 });
    });

    expect(scoped.getByTestId('audit-count-card')).toBeInTheDocument();
    expect(scoped.getByTestId('recent-audit-card')).toBeInTheDocument();
    expect(scoped.queryByTestId('task-log-summary-card')).not.toBeInTheDocument();
    expect(scoped.getByText('user-self')).toBeInTheDocument();
    expect(scoped.getAllByText('标记漏洞').length).toBeGreaterThan(0);

    fireEvent.click(scoped.getByTestId('audit-count-card'));
    expect(navigateMock).toHaveBeenCalledWith('/log-center');
  });

  it('hides the audit KPI for regular users and only shows task log summary', async () => {
    mockUserRole = 'User';
    mockedUseAuthStore.mockReturnValue({
      user: {
        id: 'user-2',
        email: 'user@example.com',
        display_name: 'normal-user',
        role: mockUserRole,
      },
    } as ReturnType<typeof useAuthStore>);

    const view = render(<DashboardPage />);
    const scoped = within(view.container);

    await waitFor(() => {
      expect(mockedGetProjects).toHaveBeenCalledTimes(1);
      expect(mockedListJobs).toHaveBeenCalledTimes(1);
      expect(mockedListFindings).toHaveBeenCalledTimes(1);
    });

    expect(mockedGetAuditLogs).not.toHaveBeenCalled();
    expect(scoped.queryByTestId('audit-count-card')).not.toBeInTheDocument();
    expect(scoped.queryByTestId('recent-audit-card')).not.toBeInTheDocument();
    const taskLogSummaryCard = scoped.getByTestId('task-log-summary-card');
    const taskLogSummaryScoped = within(taskLogSummaryCard);

    expect(taskLogSummaryCard).toBeInTheDocument();
    expect(scoped.getByText('任务日志摘要')).toBeInTheDocument();
    expect(scoped.getAllByText('扫描任务: scan-job...').length).toBeGreaterThan(0);
    expect(
      taskLogSummaryScoped.queryByRole('button', { name: '查看全部' })
    ).not.toBeInTheDocument();

    fireEvent.click(taskLogSummaryScoped.getAllByRole('button', { name: '查看日志' })[0]);
    expect(navigateMock).toHaveBeenCalledWith('/task-logs?task_type=SCAN&task_id=scan-job-1');
  });
});
