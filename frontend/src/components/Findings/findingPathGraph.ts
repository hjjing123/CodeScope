import type {
  FindingPath,
  FindingPathEdge,
  FindingPathNode,
  FindingPathStep,
} from '../../types/finding';

const DECL_KIND_LABELS: Record<string, string> = {
  Param: '参数',
  Local: '局部变量',
  Identifier: '变量使用',
  Field: '字段',
  FieldIdentifier: '字段引用',
  Expr: '表达式',
};

const NODE_KIND_LABELS: Record<string, string> = {
  Var: '变量',
  Call: '调用',
  Method: '方法',
  File: '文件',
  Lit: '字面量',
};

const VARIABLE_LABELS = new Set([
  'var',
  'param',
  'identifier',
  'reference',
  'decl',
  'fielddeclaration',
  'fieldidentifier',
  'localdeclaration',
  'assignleft',
]);

const STRUCTURAL_EDGE_TYPES = new Set(['HAS_CALL', 'IN_FILE', 'STEP_NEXT']);
const SYNTHETIC_NAME_PATTERNS = [/^\$stack\d+$/i, /^\$[a-z]\d+$/i, /^tmp\$/i];
const GENERIC_NODE_TITLES = new Set(['local', 'decl', 'expr', 'identifier']);

export interface FindingPathGraphNode {
  key: string;
  stepId: number;
  nodeId: number;
  title: string;
  subtitle?: string;
  location?: string;
  codeSnippet?: string;
  labels: string[];
  file?: string | null;
  line?: number | null;
}

export interface FindingPathGraphEdge {
  key: string;
  fromStepId: number;
  toStepId: number;
  label: string;
  detail?: string;
}

export interface FindingPathGraphModel {
  rawNodeCount: number;
  rawEdgeCount: number;
  isStructuralOnly: boolean;
  nodes: FindingPathGraphNode[];
  edges: FindingPathGraphEdge[];
}

const hasValidLine = (line?: number | null) => typeof line === 'number' && line > 0;

const toText = (value: unknown): string | undefined => {
  if (typeof value !== 'string') {
    return undefined;
  }
  const trimmed = value.trim();
  return trimmed || undefined;
};

const toNumber = (value: unknown): number | undefined => {
  if (typeof value === 'number' && Number.isFinite(value)) {
    return value;
  }
  if (typeof value === 'string' && value.trim()) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : undefined;
  }
  return undefined;
};

const shortText = (value?: string | null, maxLength = 120): string | undefined => {
  const text = toText(value);
  if (!text) {
    return undefined;
  }
  const normalized = text.replace(/\s+/g, ' ').trim();
  if (normalized.length <= maxLength) {
    return normalized;
  }
  return `${normalized.slice(0, maxLength)}...`;
};

const formatLocation = (file?: string | null, line?: number | null) => {
  if (!file) {
    return undefined;
  }
  return hasValidLine(line) ? `${file}:${line}` : file;
};

const getRawProps = (node: FindingPathNode): Record<string, unknown> =>
  node.raw_props && typeof node.raw_props === 'object' ? node.raw_props : {};

const getDeclKind = (node: FindingPathNode) => toText(getRawProps(node).declKind);

const primaryNodeName = (node: FindingPathNode) =>
  toText(node.symbol_name)
  || toText(getRawProps(node).name)
  || toText(node.display_name)
  || toText(node.code_snippet);

const isSyntheticNodeName = (value?: string) => {
  const text = toText(value);
  if (!text) {
    return false;
  }
  const lowered = text.toLowerCase();
  if (GENERIC_NODE_TITLES.has(lowered)) {
    return true;
  }
  return SYNTHETIC_NAME_PATTERNS.some((pattern) => pattern.test(text));
};

const isMeaningfulVariableNode = (node: FindingPathNode) => {
  const name = primaryNodeName(node);
  if (!name) {
    return false;
  }
  return !isSyntheticNodeName(name);
};

const isVariableLikeNode = (node: FindingPathNode) => {
  const kind = (node.node_kind || '').toLowerCase();
  if (kind === 'var') {
    return isMeaningfulVariableNode(node);
  }
  if (kind && kind !== 'var') {
    return false;
  }
  if (getDeclKind(node)) {
    return isMeaningfulVariableNode(node);
  }
  return isMeaningfulVariableNode(node)
    && node.labels.some((label) => VARIABLE_LABELS.has(label.toLowerCase()));
};

const isStructuralNode = (node: FindingPathNode) => {
  const kind = (node.node_kind || '').toLowerCase();
  if (kind === 'file' || kind === 'method') {
    return true;
  }
  return node.labels.some((label) => ['file', 'method'].includes(label.toLowerCase()));
};

const isFileNode = (node: FindingPathNode) => {
  const kind = (node.node_kind || '').toLowerCase();
  if (kind === 'file') {
    return true;
  }
  return node.labels.some((label) => label.toLowerCase() === 'file');
};

const nodeTitle = (node: FindingPathNode) =>
  shortText(primaryNodeName(node))
  || shortText(node.code_snippet)
  || shortText(node.func_name)
  || node.node_ref;

const nodeSubtitle = (node: FindingPathNode) => {
  const declKind = getDeclKind(node);
  const parts = [
    declKind ? DECL_KIND_LABELS[declKind] || declKind : undefined,
    node.node_kind ? NODE_KIND_LABELS[node.node_kind] || node.node_kind : undefined,
    shortText(node.owner_method, 48),
  ].filter((item): item is string => Boolean(item));

  return parts.slice(0, 2).join(' · ') || undefined;
};

const normalizePathNodes = (path: FindingPath): FindingPathNode[] => {
  if (path.nodes?.length) {
    return [...path.nodes].sort((left, right) => left.node_id - right.node_id);
  }
  return path.steps.map((step) => ({
    node_id: step.step_id,
    labels: step.labels,
    file: step.file,
    line: step.line,
    column: step.column,
    func_name: step.func_name,
    display_name: step.display_name,
    symbol_name: step.symbol_name,
    owner_method: step.owner_method,
    type_name: step.type_name,
    node_kind: step.node_kind,
    code_snippet: step.code_snippet,
    node_ref: step.node_ref,
    raw_props: {},
  }));
};

const normalizePathEdges = (path: FindingPath, nodes: FindingPathNode[]): FindingPathEdge[] => {
  if (path.edges?.length) {
    return [...path.edges].sort((left, right) => left.edge_id - right.edge_id);
  }

  return nodes.slice(0, -1).map((node, index) => ({
    edge_id: index,
    edge_type: 'STEP_NEXT',
    from_node_id: node.node_id,
    to_node_id: nodes[index + 1]?.node_id,
    from_step_id: node.node_id,
    to_step_id: nodes[index + 1]?.node_id,
    from_node_ref: node.node_ref,
    to_node_ref: nodes[index + 1]?.node_ref,
    label: '步骤连接',
    is_hidden: false,
    props_json: {},
  }));
};

const buildVisibleNodeList = (nodes: FindingPathNode[]) => {
  let visible = nodes.filter((node, index) => {
    if (isVariableLikeNode(node)) {
      return true;
    }
    if ((index === 0 || index === nodes.length - 1) && !isStructuralNode(node)) {
      return true;
    }
    return false;
  });

  if (visible.length < 2) {
    visible = nodes.filter((node) => !isStructuralNode(node));
  }
  if (!visible.length) {
    visible = nodes;
  }
  return visible;
};

const buildEdgeLabel = (
  fromNode: FindingPathNode,
  toNode: FindingPathNode,
  segmentEdges: FindingPathEdge[],
) => {
  const edgeTypes = Array.from(new Set(segmentEdges.map((edge) => edge.edge_type).filter(Boolean)));
  const assignRight = toText(getRawProps(toNode).assignRight) || toText(getRawProps(fromNode).assignRight);
  const sourceName = toText(fromNode.symbol_name) || toText(fromNode.display_name);
  const argIndex = segmentEdges
    .map((edge) => toNumber(edge.props_json?.argIndex))
    .find((value) => typeof value === 'number' && value >= 0);

  if (assignRight && sourceName && assignRight.includes(sourceName) && getDeclKind(toNode)) {
    return '赋值/拼接';
  }
  if (edgeTypes.includes('CALLS')) {
    return '跨方法传递';
  }
  if (edgeTypes.includes('PARAM_PASS')) {
    return typeof argIndex === 'number' ? `跨函数参数传递 #${argIndex}` : '跨函数参数传递';
  }
  if (edgeTypes.includes('REF')) {
    return '引用传播';
  }
  if (edgeTypes.includes('ARG')) {
    return typeof argIndex === 'number' ? `参数传递 #${argIndex}` : '参数传递';
  }
  if (edgeTypes.includes('AST')) {
    return '表达式传播';
  }
  return segmentEdges.find((edge) => !edge.is_hidden)?.label || segmentEdges[0]?.label || '传播';
};

const buildEdgeDetail = (segmentEdges: FindingPathEdge[], hiddenNodes: number) => {
  const parts: string[] = [];
  const types = Array.from(new Set(segmentEdges.map((edge) => edge.edge_type).filter(Boolean)));
  if (types.length > 1) {
    parts.push(types.join(' · '));
  }
  if (hiddenNodes > 0) {
    parts.push(`折叠 ${hiddenNodes} 个中间节点`);
  }
  return parts.join(' · ') || undefined;
};

const hasSemanticSupport = (
  fromNode: FindingPathNode,
  toNode: FindingPathNode,
  segmentEdges: FindingPathEdge[],
  hiddenNodes: FindingPathNode[],
) => {
  const edgeTypes = new Set(segmentEdges.map((edge) => edge.edge_type).filter(Boolean));
  const hasNonStructuralEdge = Array.from(edgeTypes).some((edgeType) => !STRUCTURAL_EDGE_TYPES.has(edgeType));
  const hasHiddenVariable = hiddenNodes.some((node) => isVariableLikeNode(node));
  const assignRight = toText(getRawProps(toNode).assignRight) || toText(getRawProps(fromNode).assignRight);
  const sourceName = toText(fromNode.symbol_name) || toText(fromNode.display_name);

  if (assignRight && sourceName && assignRight.includes(sourceName)) {
    return true;
  }
  if (edgeTypes.has('REF') || edgeTypes.has('CALLS')) {
    return true;
  }
  if (edgeTypes.has('PARAM_PASS')) {
    return true;
  }
  if (edgeTypes.has('ARG') && !edgeTypes.has('HAS_CALL') && !hiddenNodes.some((node) => isStructuralNode(node))) {
    return true;
  }
  if (hasHiddenVariable) {
    return true;
  }
  return hasNonStructuralEdge && hiddenNodes.every((node) => !isStructuralNode(node));
};

export const buildFindingPathGraph = (path: FindingPath): FindingPathGraphModel => {
  const rawNodes = normalizePathNodes(path);
  const rawEdges = normalizePathEdges(path, rawNodes);
  const visibleNodes = buildVisibleNodeList(rawNodes);
  const rawIndexByNodeId = new Map(rawNodes.map((node, index) => [node.node_id, index]));

  const graphNodes: FindingPathGraphNode[] = [];
  const edges: FindingPathGraphEdge[] = [];
  const retainedVisibleNodes: FindingPathNode[] = [];

  if (visibleNodes.length) {
    retainedVisibleNodes.push(visibleNodes[0]);
  }

  for (let index = 0; index < visibleNodes.length - 1; index += 1) {
    const current = visibleNodes[index];
    const next = visibleNodes[index + 1];
    const currentRawIndex = rawIndexByNodeId.get(current.node_id) ?? index;
    const nextRawIndex = rawIndexByNodeId.get(next.node_id) ?? index + 1;
    const segmentEdges = rawEdges.filter((edge) => {
      const fromId = edge.from_node_id ?? edge.from_step_id;
      const fromIndex = typeof fromId === 'number' ? rawIndexByNodeId.get(fromId) : undefined;
      return typeof fromIndex === 'number' && fromIndex >= currentRawIndex && fromIndex < nextRawIndex;
    });
    const hiddenNodes = rawNodes.slice(currentRawIndex + 1, nextRawIndex);

    if (!hasSemanticSupport(current, next, segmentEdges, hiddenNodes)) {
      continue;
    }

    if (!retainedVisibleNodes.some((node) => node.node_id === next.node_id)) {
      retainedVisibleNodes.push(next);
    }

    edges.push({
      key: `${path.path_id}-${current.node_id}-${next.node_id}`,
      fromStepId: current.node_id,
      toStepId: next.node_id,
      label: buildEdgeLabel(current, next, segmentEdges),
      detail: buildEdgeDetail(segmentEdges, hiddenNodes.length),
    });
  }

  const finalNodes = retainedVisibleNodes.length > 1
    ? retainedVisibleNodes
    : buildVisibleNodeList(rawNodes).slice(0, 1);

  let nodesToRender = finalNodes;
  let edgesToRender = edges;
  let isStructuralOnly = false;

  if (!edgesToRender.length && rawNodes.length > 1) {
    const structuralNodes = rawNodes.filter((node) => !isFileNode(node));
    if (structuralNodes.length > 1) {
      const structuralEdges: FindingPathGraphEdge[] = [];
      for (let index = 0; index < structuralNodes.length - 1; index += 1) {
        const current = structuralNodes[index];
        const next = structuralNodes[index + 1];
        const currentRawIndex = rawIndexByNodeId.get(current.node_id) ?? index;
        const nextRawIndex = rawIndexByNodeId.get(next.node_id) ?? index + 1;
        const segmentEdges = rawEdges.filter((edge) => {
          const fromId = edge.from_node_id ?? edge.from_step_id;
          const fromIndex = typeof fromId === 'number' ? rawIndexByNodeId.get(fromId) : undefined;
          return typeof fromIndex === 'number' && fromIndex >= currentRawIndex && fromIndex < nextRawIndex;
        });
        const hiddenNodes = rawNodes.slice(currentRawIndex + 1, nextRawIndex);
        structuralEdges.push({
          key: `${path.path_id}-struct-${current.node_id}-${next.node_id}`,
          fromStepId: current.node_id,
          toStepId: next.node_id,
          label: buildEdgeLabel(current, next, segmentEdges),
          detail: buildEdgeDetail(segmentEdges, hiddenNodes.length),
        });
      }
      nodesToRender = structuralNodes;
      edgesToRender = structuralEdges;
      isStructuralOnly = true;
    }
  }

  nodesToRender.forEach((node) => {
    graphNodes.push({
      key: `${path.path_id}-${node.node_id}`,
      stepId: node.node_id,
      nodeId: node.node_id,
      title: nodeTitle(node),
      subtitle: nodeSubtitle(node),
      location: formatLocation(node.file, node.line),
      codeSnippet: shortText(node.code_snippet, 92),
      labels: node.labels,
      file: node.file,
      line: node.line,
    });
  });

  return {
    rawNodeCount: rawNodes.length,
    rawEdgeCount: rawEdges.length,
    isStructuralOnly,
    nodes: graphNodes,
    edges: edgesToRender,
  };
};

export const pickPreferredPathStep = (path: FindingPath): FindingPathStep | null => {
  if (!path.steps.length) {
    return null;
  }

  const graph = buildFindingPathGraph(path);
  if (graph.nodes.length) {
    const preferred = graph.nodes.find((node) => node.file) || graph.nodes[0];
    const matched = path.steps.find((step) => step.step_id === preferred.stepId);
    if (matched) {
      return matched;
    }
  }

  return path.steps.find((step) => step.file) || path.steps[0];
};
