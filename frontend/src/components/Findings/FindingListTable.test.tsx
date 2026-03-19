import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import FindingListTable from './FindingListTable';
import type { Finding } from '../../types/finding';

const buildFinding = (overrides: Partial<Finding> = {}): Finding => ({
  id: 'finding-1',
  project_id: 'project-1',
  version_id: 'version-1',
  job_id: 'job-1',
  rule_key: 'any_any_xss',
  vuln_type: 'XSS',
  vuln_display_name: 'Cross-Site Scripting',
  severity: 'HIGH',
  status: 'new',
  file_path: 'src/app.ts',
  line_start: 12,
  line_end: 12,
  entry_display: 'GET /demo',
  entry_kind: 'route',
  has_path: true,
  path_length: 4,
  source_file: 'src/app.ts',
  source_line: 8,
  sink_file: 'src/app.ts',
  sink_line: 12,
  evidence_json: {},
  ai_review: {
    has_assessment: true,
    assessment_id: 'assessment-1',
    status: 'SUCCEEDED',
    verdict: 'TP',
    confidence: 'high',
    updated_at: '2026-03-18T00:00:00Z',
  },
  created_at: '2026-03-18T00:00:00Z',
  ...overrides,
});

describe('FindingListTable', () => {
  beforeEach(() => {
    class ResizeObserverMock {
      observe() {}
      unobserve() {}
      disconnect() {}
    }

    vi.stubGlobal('ResizeObserver', ResizeObserverMock);
  });

  it('renders AI review column and opens seeded session handler', async () => {
    const onViewDetail = vi.fn();
    const onOpenAIReview = vi.fn();

    render(
      <FindingListTable
        loading={false}
        data={[buildFinding()]}
        total={1}
        currentPage={1}
        pageSize={20}
        onChange={vi.fn()}
        onViewDetail={onViewDetail}
        onOpenAIReview={onOpenAIReview}
        openingFindingId={null}
      />
    );

    const reviewButton = await screen.findByRole('button', { name: /high · TP/i });
    fireEvent.click(reviewButton);

    expect(onOpenAIReview).toHaveBeenCalledTimes(1);
    expect(onViewDetail).not.toHaveBeenCalled();
  });
});
