import { describe, expect, it } from 'vitest';

import {
  FINDING_STATUS_FILTER_OPTIONS,
  MANUAL_FINDING_STATUS_ACTIONS,
  getFindingStatusBadgeStatus,
  getFindingStatusLabel,
} from './findingStatus';

describe('findingStatus', () => {
  it('exposes aligned findings filter options', () => {
    expect(FINDING_STATUS_FILTER_OPTIONS).toEqual([
      { value: 'OPEN', label: 'Open' },
      { value: 'TP', label: 'TP' },
      { value: 'FP', label: 'FP' },
      { value: 'FIXED', label: 'Fixed' },
      { value: 'NEEDS_REVIEW', label: 'Review' },
    ]);
  });

  it('keeps manual label actions scoped to TP, FP and NEEDS_REVIEW', () => {
    expect(MANUAL_FINDING_STATUS_ACTIONS.map((item) => item.value)).toEqual([
      'TP',
      'FP',
      'NEEDS_REVIEW',
    ]);
  });

  it('formats status labels and badge variants from the backend enum values', () => {
    expect(getFindingStatusLabel('OPEN')).toBe('Open');
    expect(getFindingStatusLabel('NEEDS_REVIEW')).toBe('Review');
    expect(getFindingStatusBadgeStatus('OPEN')).toBe('processing');
    expect(getFindingStatusBadgeStatus('TP')).toBe('error');
    expect(getFindingStatusBadgeStatus('FP')).toBe('success');
  });
});
