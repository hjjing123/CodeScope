import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import ImportWizard from './ImportWizard';
import * as projectVersionService from '../../services/projectVersion';

vi.mock('../../services/projectVersion', () => ({
  testGitImport: vi.fn(),
  triggerGitImport: vi.fn(),
  uploadImportFile: vi.fn(),
  getImportJob: vi.fn(),
}));

const mockedProjectVersion = vi.mocked(projectVersionService);

describe('ImportWizard', () => {
  beforeEach(() => {
    class ResizeObserverMock {
      observe() {}
      unobserve() {}
      disconnect() {}
    }

    vi.stubGlobal('ResizeObserver', ResizeObserverMock);
    Element.prototype.scrollIntoView = vi.fn();
    vi.clearAllMocks();
    mockedProjectVersion.getImportJob.mockResolvedValue({
      request_id: 'req-1',
      data: {
        id: 'job-1',
        project_id: 'project-1',
        import_type: 'GIT',
        payload: {},
        status: 'RUNNING',
        stage: 'Validate',
        progress: {
          current_stage: 'Validate',
          percent: 10,
          completed_stages: 0,
          total_stages: 4,
          is_terminal: false,
          stages: [],
        },
        result_summary: {},
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      },
      meta: {},
    } as never);
  });

  it('shows public/private git guidance and optional ref support', async () => {
    mockedProjectVersion.testGitImport.mockResolvedValue({
      request_id: 'req-1',
      data: {
        ok: true,
        resolved_ref: 'branch:master',
        resolved_ref_type: 'branch',
        resolved_ref_value: 'master',
        auto_detected: true,
      },
      meta: {},
    } as never);

    render(
      <ImportWizard
        open
        onCancel={vi.fn()}
        onSuccess={vi.fn()}
        projectId="project-1"
      />
    );

    fireEvent.click(screen.getAllByText('Git 仓库')[0]);

    expect(await screen.findByText('公开仓库')).toBeInTheDocument();
    expect(screen.getByText('私有仓库')).toBeInTheDocument();
    expect(screen.queryByPlaceholderText('请输入 HTTPS Token')).not.toBeInTheDocument();

    fireEvent.change(screen.getByPlaceholderText('例如: snapshot-2026-03-07'), {
      target: { value: 'hello-sec' },
    });
    fireEvent.change(screen.getByPlaceholderText('https://github.com/user/repo.git'), {
      target: { value: 'https://github.com/j3ers3/Hello-Java-Sec' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Git 测试' }));

    await waitFor(() => {
      expect(mockedProjectVersion.testGitImport).toHaveBeenCalledWith('project-1', {
        repo_url: 'https://github.com/j3ers3/Hello-Java-Sec',
        repo_visibility: 'public',
        auth_type: 'none',
        username: undefined,
        access_token: undefined,
        ssh_private_key: undefined,
        ssh_passphrase: undefined,
        ref_type: undefined,
        ref_value: undefined,
        version_name: undefined,
        note: undefined,
      });
    });

    expect(await screen.findByText('已自动识别默认引用：branch:master')).toBeInTheDocument();
  });

  it('shows private auth fields when private repository is selected', async () => {
    render(
      <ImportWizard
        open
        onCancel={vi.fn()}
        onSuccess={vi.fn()}
        projectId="project-1"
      />
    );

    fireEvent.click(screen.getAllByText('Git 仓库')[0]);
    fireEvent.click(await screen.findByText('私有仓库'));

    expect(await screen.findByPlaceholderText('请输入 HTTPS Token')).toBeInTheDocument();
  });
});
