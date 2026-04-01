import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import FindingDetailPanel from './FindingDetailPanel';
import type { Finding, FindingLabelActionResponse } from '../../types/finding';
import { FindingService } from '../../services/findings';
import { getVersionFile } from '../../services/projectVersion';

const messageMocks = vi.hoisted(() => ({
  success: vi.fn(),
  error: vi.fn(),
}));

vi.mock('antd', async () => {
  const actual = await vi.importActual<typeof import('antd')>('antd');
  return {
    ...actual,
    message: {
      success: messageMocks.success,
      error: messageMocks.error,
    },
  };
});

vi.mock('../../services/findings', () => ({
  FindingService: {
    labelFinding: vi.fn(),
    getFindingPaths: vi.fn(),
    getPathNodeContext: vi.fn(),
  },
}));

vi.mock('../../services/projectVersion', () => ({
  getVersionFile: vi.fn(),
}));

vi.mock('./FindingPathViewer', () => ({
  default: () => <div data-testid="path-viewer" />,
}));

vi.mock('./FindingAIReviewPanel', () => ({
  default: () => <div data-testid="ai-review-panel" />,
}));

vi.mock('./CodeViewer', () => ({
  default: ({ code }: { code: string }) => <pre>{code}</pre>,
}));

const mockedLabelFinding = vi.mocked(FindingService.labelFinding);
const mockedGetVersionFile = vi.mocked(getVersionFile);

const buildFinding = (overrides: Partial<Finding> = {}): Finding => ({
  id: 'finding-1',
  project_id: 'project-1',
  version_id: 'version-1',
  job_id: 'job-1',
  rule_key: 'any_any_xss',
  vuln_type: 'XSS',
  vuln_display_name: 'Cross-Site Scripting',
  severity: 'HIGH',
  status: 'OPEN',
  file_path: 'src/App.java',
  line_start: 12,
  line_end: 12,
  entry_display: 'GET /demo',
  entry_kind: 'route',
  has_path: false,
  path_length: null,
  source_file: 'src/App.java',
  source_line: 8,
  sink_file: 'src/App.java',
  sink_line: 12,
  evidence_json: {},
  ai_review: {
    has_assessment: false,
  },
  created_at: '2026-03-18T00:00:00Z',
  ...overrides,
});

const buildLabelResponse = (finding: Finding): FindingLabelActionResponse => ({
  finding,
  label: {
    id: 'label-1',
    finding_id: finding.id,
    status: finding.status,
    created_at: '2026-03-18T00:00:00Z',
    fp_reason: null,
    comment: null,
    created_by: 'user-1',
  },
});

describe('FindingDetailPanel', () => {
  beforeEach(() => {
    class ResizeObserverMock {
      observe() {}
      unobserve() {}
      disconnect() {}
    }

    vi.stubGlobal('ResizeObserver', ResizeObserverMock);
    vi.clearAllMocks();
    mockedGetVersionFile.mockResolvedValue({
      data: {
        content: 'class Demo {}',
        total_lines: 1,
        truncated: false,
      },
    } as never);
  });

  it('submits TP status from the confirm action and hides the fixed action', async () => {
    const onClose = vi.fn();
    const onUpdate = vi.fn();
    mockedLabelFinding.mockResolvedValue(buildLabelResponse(buildFinding({ status: 'TP' })));

    render(
      <FindingDetailPanel
        visible
        finding={buildFinding()}
        onClose={onClose}
        onUpdate={onUpdate}
      />
    );

    expect(screen.queryByRole('button', { name: 'Fixed' })).not.toBeInTheDocument();

    fireEvent.click(screen.getAllByRole('button', { name: /Confirm/i })[0]);

    await waitFor(() => {
      expect(mockedLabelFinding).toHaveBeenCalledWith('finding-1', {
        status: 'TP',
        fp_reason: undefined,
      });
    });
    expect(messageMocks.success).toHaveBeenCalledWith('Finding marked as TP');
    expect(onUpdate).toHaveBeenCalledTimes(1);
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('submits FP status from the ignore action', async () => {
    mockedLabelFinding.mockResolvedValue(buildLabelResponse(buildFinding({ status: 'FP' })));

    render(
      <FindingDetailPanel
        visible
        finding={buildFinding()}
        onClose={vi.fn()}
        onUpdate={vi.fn()}
      />
    );

    fireEvent.click(screen.getAllByRole('button', { name: /Ignore/i })[0]);

    await waitFor(() => {
      expect(mockedLabelFinding).toHaveBeenCalledWith('finding-1', {
        status: 'FP',
        fp_reason: 'Manually marked as FP',
      });
    });
  });

  it('submits NEEDS_REVIEW status from the review action', async () => {
    mockedLabelFinding.mockResolvedValue(
      buildLabelResponse(buildFinding({ status: 'NEEDS_REVIEW' }))
    );

    render(
      <FindingDetailPanel
        visible
        finding={buildFinding()}
        onClose={vi.fn()}
        onUpdate={vi.fn()}
      />
    );

    const reviewButton = screen
      .getAllByRole('button')
      .find((button) => button.textContent?.includes('Review'));

    expect(reviewButton).toBeDefined();
    fireEvent.click(reviewButton as HTMLButtonElement);

    await waitFor(() => {
      expect(mockedLabelFinding).toHaveBeenCalledWith('finding-1', {
        status: 'NEEDS_REVIEW',
        fp_reason: undefined,
      });
    });
  });

  it('shows the backend business error only once when label update fails', async () => {
    mockedLabelFinding.mockRejectedValue({
      response: {
        data: {
          error: {
            message: '标注状态不合法',
          },
        },
      },
    });

    render(
      <FindingDetailPanel
        visible
        finding={buildFinding()}
        onClose={vi.fn()}
        onUpdate={vi.fn()}
      />
    );

    fireEvent.click(screen.getAllByRole('button', { name: /Confirm/i })[0]);

    await waitFor(() => {
      expect(messageMocks.error).toHaveBeenCalledWith('标注状态不合法');
    });
    expect(messageMocks.error).toHaveBeenCalledTimes(1);
  });
});
