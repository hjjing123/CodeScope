import { render, screen, waitFor, within } from '@testing-library/react';
import dayjs from 'dayjs';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import ProjectList from './ProjectList';
import * as projectVersionService from '../../services/projectVersion';

const navigateMock = vi.fn();

vi.mock('../../services/projectVersion', () => ({
  getProjects: vi.fn(),
  deleteProject: vi.fn(),
}));

vi.mock('./ProjectCreateModal', () => ({
  default: () => null,
}));

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom');
  return {
    ...actual,
    useNavigate: () => navigateMock,
  };
});

const mockedProjectVersion = vi.mocked(projectVersionService);

describe('ProjectList', () => {
  beforeEach(() => {
    class ResizeObserverMock {
      observe() {}
      unobserve() {}
      disconnect() {}
    }

    vi.stubGlobal('ResizeObserver', ResizeObserverMock);
    Element.prototype.scrollIntoView = vi.fn();
    vi.clearAllMocks();
  });

  it('formats project created_at consistently and falls back for invalid values', async () => {
    const validCreatedAt = '2026-03-31T08:20:52Z';
    const expectedFormatted = dayjs(validCreatedAt).format('YYYY-MM-DD HH:mm:ss');
    const localeFormatted = new Date(validCreatedAt).toLocaleString();

    mockedProjectVersion.getProjects.mockResolvedValue({
      request_id: 'req-projects',
      data: {
        items: [
          {
            id: 'project-1',
            name: 'demo-project',
            description: 'demo',
            status: 'SCANNABLE',
            my_project_role: 'Owner',
            created_at: validCreatedAt,
            updated_at: validCreatedAt,
          },
          {
            id: 'project-2',
            name: 'broken-project',
            description: 'broken',
            status: 'NEW',
            my_project_role: 'Reader',
            created_at: 'not-a-date',
            updated_at: validCreatedAt,
          },
        ],
        total: 2,
      },
      meta: {},
    } as never);

    render(<ProjectList />);

    await waitFor(() => {
      expect(mockedProjectVersion.getProjects).toHaveBeenCalledWith({
        page: 1,
        page_size: 10,
      });
    });

    expect(await screen.findByText('demo-project')).toBeInTheDocument();
    expect(screen.getByText(expectedFormatted)).toBeInTheDocument();

    if (localeFormatted !== expectedFormatted) {
      expect(screen.queryByText(localeFormatted)).not.toBeInTheDocument();
    }

    const brokenRow = screen.getByText('broken-project').closest('tr');
    expect(brokenRow).not.toBeNull();
    expect(within(brokenRow as HTMLTableRowElement).getByText('-')).toBeInTheDocument();
  });
});
