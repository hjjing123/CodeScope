import type {
  Finding,
  FindingPath,
  FindingPathEdge,
  FindingPathNode,
  FindingPathStep,
} from '../../types/finding';

type FindingLocation = {
  displayName: string;
  file: string;
  line: number | null;
  labels: string[];
  nodeKind?: string;
  codeSnippet?: string | null;
  nodeRef: string;
};

const KNOWN_NODE_KINDS = new Set(['Var', 'Call', 'Method', 'File', 'Lit']);

const toText = (value: unknown): string | null => {
  if (typeof value !== 'string') {
    return null;
  }
  const trimmed = value.trim();
  return trimmed || null;
};

const toPositiveInt = (value: unknown): number | null => {
  if (typeof value === 'number' && Number.isInteger(value) && value > 0) {
    return value;
  }
  if (typeof value === 'string' && value.trim()) {
    const parsed = Number(value);
    if (Number.isInteger(parsed) && parsed > 0) {
      return parsed;
    }
  }
  return null;
};

const toRecord = (value: unknown): Record<string, unknown> => {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return {};
  }
  return value as Record<string, unknown>;
};

const toStringArray = (value: unknown): string[] => {
  if (!Array.isArray(value)) {
    return [];
  }
  return value
    .map((item) => toText(item))
    .filter((item): item is string => Boolean(item));
};

const dedupeStrings = (items: string[]): string[] => Array.from(new Set(items));

const sameLocation = (
  left: FindingLocation | null | undefined,
  right: FindingLocation | null | undefined
) => Boolean(left && right && left.file === right.file && left.line === right.line);

const buildFallbackNodeRef = (
  findingId: string,
  role: string,
  file: string,
  line: number | null,
  preferredNodeRef?: string | null
) => {
  if (preferredNodeRef) {
    return preferredNodeRef;
  }
  return `${findingId}:${role}:${file}:${line ?? 'na'}`;
};

const buildPathStep = (location: FindingLocation, index: number): FindingPathStep => ({
  step_id: index,
  labels: location.labels,
  file: location.file,
  line: location.line,
  column: null,
  display_name: location.displayName,
  node_kind: location.nodeKind ?? null,
  code_snippet: location.codeSnippet ?? null,
  node_ref: location.nodeRef,
});

const buildPathNode = (location: FindingLocation, index: number): FindingPathNode => ({
  node_id: index,
  labels: location.labels,
  file: location.file,
  line: location.line,
  column: null,
  display_name: location.displayName,
  node_kind: location.nodeKind ?? null,
  code_snippet: location.codeSnippet ?? null,
  node_ref: location.nodeRef,
  raw_props: {
    fallback: true,
  },
});

const buildPathEdge = (
  from: FindingLocation,
  to: FindingLocation,
  index: number
): FindingPathEdge => ({
  edge_id: index,
  edge_type: 'STEP_NEXT',
  from_node_id: index,
  to_node_id: index + 1,
  from_step_id: index,
  to_step_id: index + 1,
  from_node_ref: from.nodeRef,
  to_node_ref: to.nodeRef,
  label: '定位关联',
  is_hidden: false,
  props_json: {
    fallback: true,
  },
});

const buildFallbackPath = (locations: FindingLocation[]): FindingPath => {
  const steps = locations.map((location, index) => buildPathStep(location, index));
  const nodes = locations.map((location, index) => buildPathNode(location, index));
  const edges = locations.slice(0, -1).map((location, index) => buildPathEdge(location, locations[index + 1], index));

  return {
    path_id: 0,
    path_length: edges.length,
    steps,
    nodes,
    edges,
  };
};

const mergeLocation = (
  left: FindingLocation,
  right: FindingLocation,
  displayName: string
): FindingLocation => ({
  ...left,
  displayName,
  labels: dedupeStrings([...left.labels, ...right.labels]),
});

export const buildFallbackFindingPaths = (finding: Finding): FindingPath[] => {
  const evidence = toRecord(finding.evidence_json);
  const codeContext = toRecord(evidence.code_context);
  const focusContext = toRecord(codeContext.focus);
  const evidenceLabels = toStringArray(evidence.labels);
  const evidenceNodeRef = toText(evidence.node_ref);
  const focusFile = toText(focusContext.file_path);
  const focusLine = toPositiveInt(focusContext.start_line) ?? toPositiveInt(focusContext.line);
  const focusSnippet = toText(focusContext.snippet);
  const inferredNodeKind = evidenceLabels.find((label) => KNOWN_NODE_KINDS.has(label)) ?? undefined;

  const focusFilePath = toText(finding.file_path) ?? toText(finding.sink_file) ?? toText(finding.source_file) ?? focusFile;
  const focusLineNumber = toPositiveInt(finding.line_start) ?? toPositiveInt(finding.sink_line) ?? toPositiveInt(finding.source_line) ?? focusLine;

  const hasSourceHint = Boolean(toText(finding.source_file) || toPositiveInt(finding.source_line));
  const hasSinkHint = Boolean(toText(finding.sink_file) || toPositiveInt(finding.sink_line));

  const source = hasSourceHint && focusFilePath
    ? {
        displayName: 'Source',
        file: toText(finding.source_file) ?? focusFilePath,
        line: toPositiveInt(finding.source_line),
        labels: dedupeStrings(['Source', ...evidenceLabels]),
        nodeKind: inferredNodeKind,
        codeSnippet: focusSnippet,
        nodeRef: buildFallbackNodeRef(
          finding.id,
          'source',
          toText(finding.source_file) ?? focusFilePath,
          toPositiveInt(finding.source_line),
          evidenceNodeRef
        ),
      }
    : null;

  const sink = hasSinkHint && (toText(finding.sink_file) ?? focusFilePath)
    ? {
        displayName: 'Sink',
        file: (toText(finding.sink_file) ?? focusFilePath) as string,
        line: toPositiveInt(finding.sink_line) ?? toPositiveInt(finding.line_start),
        labels: dedupeStrings(['Sink', ...evidenceLabels]),
        nodeKind: inferredNodeKind,
        codeSnippet: focusSnippet,
        nodeRef: buildFallbackNodeRef(
          finding.id,
          'sink',
          (toText(finding.sink_file) ?? focusFilePath) as string,
          toPositiveInt(finding.sink_line) ?? toPositiveInt(finding.line_start),
          evidenceNodeRef
        ),
      }
    : null;

  const focus = focusFilePath
    ? {
        displayName: 'Matched Location',
        file: focusFilePath,
        line: focusLineNumber,
        labels: dedupeStrings(['Match', ...evidenceLabels]),
        nodeKind: inferredNodeKind,
        codeSnippet: focusSnippet,
        nodeRef: buildFallbackNodeRef(
          finding.id,
          'match',
          focusFilePath,
          focusLineNumber,
          evidenceNodeRef
        ),
      }
    : null;

  if (source && sink) {
    if (sameLocation(source, sink)) {
      return [buildFallbackPath([mergeLocation(source, sink, 'Source / Sink')])];
    }
    return [buildFallbackPath([source, sink])];
  }

  if (source && focus && !sameLocation(source, focus)) {
    return [buildFallbackPath([source, focus])];
  }

  const single = sink ?? focus ?? source;
  return single ? [buildFallbackPath([single])] : [];
};
