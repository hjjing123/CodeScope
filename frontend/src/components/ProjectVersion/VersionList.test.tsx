import { render, screen, waitFor, within } from '@testing-library/react';
import dayjs from 'dayjs';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import VersionList from './VersionList';
import * as projectVersionService from '../../services/projectVersion';

const navigateMock = vi.fn();

vi.mock('../../services/projectVersion', () => ({
  getVersions: vi.fn(),
  deleteVersion: vi.fn(),
  triggerGitSync: vi.fn(),
}));

vi.mock('./ImportWizard', () => ({
  default: () => null,
}));

vi.mock('./CodeBrowser', () => ({
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

describe('VersionList', () => {
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

  it('formats version created_at consistently and falls back for invalid values', async () => {
    const validCreatedAt = '2026-03-31T08:20:52Z';
    const expectedFormatted = dayjs(validCreatedAt).format('YYYY-MM-DD HH:mm:ss');
    const localeFormatted = new Date(validCreatedAt).toLocaleString();

    mockedProjectVersion.getVersions.mockResolvedValue({
      request_id: 'req-versions',
      data: {
        items: [
          {
            id: 'version-1',
            project_id: 'project-1',
            name: 'snapshot-v1',
            source: 'UPLOAD',
            note: null,
            tag: null,
            git_repo_url: null,
            git_ref: null,
            snapshot_object_key: null,
            status: 'READY',
            created_at: validCreatedAt,
            updated_at: validCreatedAt,
          },
          {
            id: 'version-2',
            project_id: 'project-1',
            name: 'snapshot-invalid',
            source: 'GIT',
            note: null,
            tag: null,
            git_repo_url: null,
            git_ref: null,
            snapshot_object_key: null,
            status: 'FAILED',
            created_at: 'not-a-date',
            updated_at: validCreatedAt,
          },
        ],
        total: 2,
      },
      meta: {},
    } as never);

    render(<VersionList projectId="project-1" />);

    await waitFor(() => {
      expect(mockedProjectVersion.getVersions).toHaveBeenCalledWith('project-1', {
        page: 1,
        page_size: 10,
      });
    });

    expect(await screen.findByText('snapshot-v1')).toBeInTheDocument();
    expect(screen.getByText(expectedFormatted)).toBeInTheDocument();

    if (localeFormatted !== expectedFormatted) {
      expect(screen.queryByText(localeFormatted)).not.toBeInTheDocument();
    }

    const invalidRow = screen.getByText('snapshot-invalid').closest('tr');
    expect(invalidRow).not.toBeNull();
    expect(within(invalidRow as HTMLTableRowElement).getByText('-')).toBeInTheDocument();
  });
});
