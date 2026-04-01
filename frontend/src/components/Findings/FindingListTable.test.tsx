import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import FindingListTable from './FindingListTable';
import type { Finding } from '../../types/finding';
import {
  FINDING_FP_DOT_COLOR,
  FINDING_STATUS_DOT_COLORS,
} from '../../utils/findingStatus';

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

  it('renders severity from finding data instead of AI review confidence', () => {
    render(
      <FindingListTable
        loading={false}
        data={[
          buildFinding({
            severity: 'LOW',
            ai_review: {
              has_assessment: true,
              assessment_id: 'assessment-2',
              status: 'SUCCEEDED',
              verdict: 'TP',
              confidence: 'high',
              updated_at: '2026-03-18T00:00:00Z',
            },
          }),
        ]}
        total={1}
        currentPage={1}
        pageSize={20}
        onChange={vi.fn()}
        onViewDetail={vi.fn()}
      />
    );

    expect(screen.getByText('LOW')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /high/i })).toBeInTheDocument();
  });

  it('renders aligned finding status labels', () => {
    render(
      <FindingListTable
        loading={false}
        data={[
          buildFinding({ id: 'finding-open', status: 'OPEN' }),
          buildFinding({ id: 'finding-tp', status: 'TP' }),
          buildFinding({ id: 'finding-needs-review', status: 'NEEDS_REVIEW' }),
          buildFinding({ id: 'finding-fp', status: 'FP' }),
        ]}
        total={4}
        currentPage={1}
        pageSize={20}
        onChange={vi.fn()}
        onViewDetail={vi.fn()}
      />
    );

    expect(screen.getAllByText('Open')[0]).toBeInTheDocument();
    expect(screen.getByText('TP')).toBeInTheDocument();
    expect(screen.getByText('Review')).toBeInTheDocument();
    expect(screen.getByText('FP')).toBeInTheDocument();

    const openDot = document.querySelector('[data-status-dot="OPEN"]') as HTMLElement | null;
    const tpDot = document.querySelector('[data-status-dot="TP"]') as HTMLElement | null;
    const fpDot = document.querySelector('[data-status-dot="FP"]') as HTMLElement | null;
    const reviewDot = document.querySelector('[data-status-dot="NEEDS_REVIEW"]') as HTMLElement | null;

    expect(openDot).not.toBeNull();
    expect(tpDot).not.toBeNull();
    expect(fpDot).not.toBeNull();
    expect(reviewDot).not.toBeNull();
    expect(openDot?.style.backgroundColor).toBe('rgb(47, 84, 235)');
    expect(tpDot?.style.backgroundColor).toBe('rgb(255, 77, 79)');
    expect(fpDot?.style.backgroundColor).toBe('rgb(57, 255, 20)');
    expect(reviewDot?.style.backgroundColor).toBe('rgb(250, 173, 20)');
    expect(fpDot?.style.boxShadow).toContain(FINDING_FP_DOT_COLOR);
    expect(openDot?.style.boxShadow).toContain(FINDING_STATUS_DOT_COLORS.OPEN);
  });
});
