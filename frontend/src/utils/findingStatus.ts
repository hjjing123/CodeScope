import type { FindingStatus, ManualFindingLabelStatus } from '../types/finding';

type BadgeStatus = 'success' | 'processing' | 'error' | 'default' | 'warning';
export const FINDING_FP_DOT_COLOR = '#39ff14';
export const FINDING_STATUS_DOT_COLORS: Record<FindingStatus, string> = {
  OPEN: '#2f54eb',
  TP: '#ff4d4f',
  FP: FINDING_FP_DOT_COLOR,
  FIXED: '#52c41a',
  NEEDS_REVIEW: '#faad14',
};

export const FINDING_STATUS_LABELS: Record<FindingStatus, string> = {
  OPEN: 'Open',
  TP: 'TP',
  FP: 'FP',
  FIXED: 'Fixed',
  NEEDS_REVIEW: 'Review',
};

export const FINDING_STATUS_BADGE_STATUS: Record<FindingStatus, BadgeStatus> = {
  OPEN: 'processing',
  TP: 'error',
  FP: 'success',
  FIXED: 'success',
  NEEDS_REVIEW: 'warning',
};

export const FINDING_STATUS_FILTER_OPTIONS: Array<{
  value: FindingStatus;
  label: string;
}> = [
  { value: 'OPEN', label: FINDING_STATUS_LABELS.OPEN },
  { value: 'TP', label: FINDING_STATUS_LABELS.TP },
  { value: 'FP', label: FINDING_STATUS_LABELS.FP },
  { value: 'FIXED', label: FINDING_STATUS_LABELS.FIXED },
  { value: 'NEEDS_REVIEW', label: FINDING_STATUS_LABELS.NEEDS_REVIEW },
];

export const MANUAL_FINDING_STATUS_ACTIONS: Array<{
  value: ManualFindingLabelStatus;
  label: string;
  fpReason?: string;
  danger?: boolean;
}> = [
  { value: 'TP', label: 'Confirm', danger: true },
  { value: 'FP', label: 'Ignore', fpReason: 'Manually marked as FP' },
  { value: 'NEEDS_REVIEW', label: 'Review' },
];

export const getFindingStatusLabel = (status?: string | null): string => {
  if (!status) {
    return '-';
  }
  return FINDING_STATUS_LABELS[status as FindingStatus] ?? status.replace(/_/g, ' ');
};

export const getFindingStatusBadgeStatus = (status?: string | null): BadgeStatus => {
  if (!status) {
    return 'default';
  }
  return FINDING_STATUS_BADGE_STATUS[status as FindingStatus] ?? 'default';
};

export const getFindingStatusDotColor = (status?: string | null): string | null => {
  if (!status) {
    return null;
  }
  return FINDING_STATUS_DOT_COLORS[status as FindingStatus] ?? null;
};
