const normalizeFilePath = (filePath?: string | null) => {
  if (!filePath) {
    return null;
  }
  const normalized = filePath.replace(/\\+/g, '/').trim();
  return normalized || null;
};

export const formatLocation = (filePath?: string | null, line?: number | null) => {
  const normalized = normalizeFilePath(filePath);
  if (!normalized) {
    return '-';
  }
  return typeof line === 'number' && line > 0 ? `${normalized}:${line}` : normalized;
};

export const compactFilePath = (filePath?: string | null, preserveSegments = 4) => {
  const normalized = normalizeFilePath(filePath);
  if (!normalized) {
    return null;
  }
  const segments = normalized.split('/').filter(Boolean);
  if (segments.length <= preserveSegments) {
    return normalized;
  }
  return `.../${segments.slice(-preserveSegments).join('/')}`;
};

export const formatCompactLocation = (
  filePath?: string | null,
  line?: number | null,
  preserveSegments = 4
) => {
  const compact = compactFilePath(filePath, preserveSegments);
  if (!compact) {
    return '-';
  }
  return typeof line === 'number' && line > 0 ? `${compact}:${line}` : compact;
};
