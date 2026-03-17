import React from 'react';
import { Segmented, Tag, Tooltip, Typography } from 'antd';
import {
  ArrowDownOutlined,
  CodeOutlined,
  FileOutlined,
  NodeIndexOutlined,
} from '@ant-design/icons';

import type { FindingPath, FindingPathStep } from '../../types/finding';
import {
  buildFindingPathGraph,
  type FindingPathGraphEdge,
  type FindingPathGraphNode,
} from './findingPathGraph';
import '../ProjectVersion/CodeBrowser.css';

const { Text } = Typography;

const hasValidLine = (line?: number | null) => typeof line === 'number' && line > 0;

const formatLocation = (filePath?: string | null, line?: number | null) => {
  if (!filePath) {
    return '-';
  }
  return hasValidLine(line) ? `${filePath}:${line}` : filePath;
};

const getRoleMeta = (index: number, total: number) => {
  if (total === 1) {
    return { label: 'Match', color: 'default' as const, accent: '#0f766e' };
  }
  if (index === 0) {
    return { label: 'Source', color: 'success' as const, accent: '#16a34a' };
  }
  if (index === total - 1) {
    return { label: 'Sink', color: 'error' as const, accent: '#dc2626' };
  }
  return { label: 'Propagation', color: 'processing' as const, accent: '#2563eb' };
};

interface FindingPathViewerProps {
  paths: FindingPath[];
  selectedPathId?: number | null;
  selectedStepId?: number | null;
  onPathSelect: (path: FindingPath) => void;
  onStepClick: (step: FindingPathStep) => void;
}

type ViewMode = 'graph' | 'raw';

const cardBaseStyle: React.CSSProperties = {
  background: '#ffffff',
  borderRadius: 14,
  border: '1px solid #dbe4f0',
  padding: 12,
  cursor: 'pointer',
  transition: 'all 0.2s ease',
};

const FindingPathViewer: React.FC<FindingPathViewerProps> = ({
  paths,
  selectedPathId,
  selectedStepId,
  onPathSelect,
  onStepClick,
}) => {
  const [viewMode, setViewMode] = React.useState<ViewMode>('graph');

  if (!paths.length) {
    return null;
  }

  const activePath = paths.find((item) => item.path_id === selectedPathId) ?? paths[0];
  const graph = React.useMemo(() => buildFindingPathGraph(activePath), [activePath]);
  const stepMap = React.useMemo(
    () => new Map(activePath.steps.map((step) => [step.step_id, step])),
    [activePath.steps],
  );

  const handleGraphNodeClick = (node: FindingPathGraphNode) => {
    const step = stepMap.get(node.stepId);
    if (step) {
      onStepClick(step);
    }
  };

  const renderGraphEdge = (edge: FindingPathGraphEdge) => (
    <div
      key={edge.key}
      style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        gap: 6,
        padding: '2px 0',
      }}
    >
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          width: 28,
          height: 28,
          borderRadius: 999,
          background: '#e2e8f0',
          color: '#475569',
        }}
      >
        <ArrowDownOutlined style={{ fontSize: 12 }} />
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 2 }}>
        <Tag color="blue" style={{ margin: 0, borderRadius: 999, paddingInline: 10 }}>
          {edge.label}
        </Tag>
        {edge.detail ? (
          <Text type="secondary" style={{ fontSize: 11, textAlign: 'center' }}>
            {edge.detail}
          </Text>
        ) : null}
      </div>
    </div>
  );

  const renderGraphNode = (node: FindingPathGraphNode, index: number) => {
    const role = getRoleMeta(index, graph.nodes.length);
    const isSelected = selectedStepId === node.stepId;

    return (
      <div
        key={node.key}
        onClick={() => handleGraphNodeClick(node)}
        style={{
          ...cardBaseStyle,
          borderColor: isSelected ? '#60a5fa' : '#dbe4f0',
          boxShadow: isSelected
            ? '0 12px 24px -16px rgba(37, 99, 235, 0.55)'
            : '0 10px 18px -18px rgba(15, 23, 42, 0.55)',
          background: isSelected ? 'linear-gradient(180deg, #ffffff 0%, #f8fbff 100%)' : '#ffffff',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8, marginBottom: 10 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            {index === 0 ? (
              <FileOutlined style={{ color: role.accent }} />
            ) : index === graph.nodes.length - 1 ? (
              <NodeIndexOutlined style={{ color: role.accent }} />
            ) : (
              <CodeOutlined style={{ color: role.accent }} />
            )}
            <Tag color={role.color} style={{ margin: 0 }}>
              {role.label}
            </Tag>
          </div>
          <Text type="secondary" style={{ fontSize: 11 }}>
            Node {index + 1}/{graph.nodes.length}
          </Text>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          <div>
            <div
              style={{
                color: '#0f172a',
                fontSize: 17,
                fontWeight: 600,
                lineHeight: 1.2,
                wordBreak: 'break-word',
              }}
            >
              {node.title}
            </div>
            {node.subtitle ? (
              <Text type="secondary" style={{ fontSize: 12 }}>
                {node.subtitle}
              </Text>
            ) : null}
          </div>

          <Tooltip title={formatLocation(node.file, node.line)}>
            <div
              style={{
                color: '#334155',
                fontFamily: 'var(--cs-font-mono)',
                fontSize: 12,
                background: '#f8fafc',
                padding: '6px 8px',
                borderRadius: 8,
                border: '1px solid #e2e8f0',
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                whiteSpace: 'nowrap',
              }}
            >
              {formatLocation(node.file, node.line)}
            </div>
          </Tooltip>

          {node.codeSnippet ? (
            <Tooltip title={node.codeSnippet}>
              <div
                style={{
                  color: '#1e293b',
                  fontFamily: 'var(--cs-font-mono)',
                  fontSize: 12,
                  background: '#eff6ff',
                  padding: '6px 8px',
                  borderRadius: 8,
                  border: '1px solid #bfdbfe',
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  whiteSpace: 'nowrap',
                }}
              >
                {node.codeSnippet}
              </div>
            </Tooltip>
          ) : null}

          {node.labels.length ? (
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
              {node.labels.slice(0, 4).map((label) => (
                <Tag key={`${node.key}-${label}`} style={{ margin: 0, borderRadius: 999 }}>
                  {label}
                </Tag>
              ))}
            </div>
          ) : null}
        </div>
      </div>
    );
  };

  const renderRawStep = (step: FindingPathStep, index: number) => {
    const isSelected = selectedStepId === step.step_id;
    const role = getRoleMeta(index, activePath.steps.length);
    const headline = step.display_name || step.symbol_name || step.func_name || `Step ${index + 1}`;

    return (
      <React.Fragment key={`${activePath.path_id}-${step.step_id}`}>
        {index > 0 ? renderGraphEdge({
          key: `${activePath.path_id}-raw-${index}`,
          fromStepId: activePath.steps[index - 1].step_id,
          toStepId: step.step_id,
          label: '原始节点',
        }) : null}

        <div
          onClick={() => onStepClick(step)}
          style={{
            ...cardBaseStyle,
            borderColor: isSelected ? '#60a5fa' : '#dbe4f0',
            boxShadow: isSelected
              ? '0 12px 24px -16px rgba(37, 99, 235, 0.55)'
              : '0 10px 18px -18px rgba(15, 23, 42, 0.55)',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8, marginBottom: 10 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <CodeOutlined style={{ color: role.accent }} />
              <Tag color={role.color} style={{ margin: 0 }}>
                {role.label}
              </Tag>
            </div>
            <Text type="secondary" style={{ fontSize: 11 }}>
              Step {index + 1}/{activePath.steps.length}
            </Text>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            <div style={{ color: '#0f172a', fontSize: 15, fontWeight: 600, wordBreak: 'break-word' }}>
              {headline}
            </div>
            <Tooltip title={formatLocation(step.file, step.line)}>
              <div
                style={{
                  color: '#334155',
                  fontFamily: 'var(--cs-font-mono)',
                  fontSize: 12,
                  background: '#f8fafc',
                  padding: '6px 8px',
                  borderRadius: 8,
                  border: '1px solid #e2e8f0',
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  whiteSpace: 'nowrap',
                }}
              >
                {formatLocation(step.file, step.line)}
              </div>
            </Tooltip>
            {step.code_snippet ? (
              <Tooltip title={step.code_snippet}>
                <div
                  style={{
                    color: '#1e293b',
                    fontFamily: 'var(--cs-font-mono)',
                    fontSize: 12,
                    background: '#eff6ff',
                    padding: '6px 8px',
                    borderRadius: 8,
                    border: '1px solid #bfdbfe',
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    whiteSpace: 'nowrap',
                  }}
                >
                  {step.code_snippet.trim()}
                </div>
              </Tooltip>
            ) : null}
          </div>
        </div>
      </React.Fragment>
    );
  };

  return (
    <div
      className="code-browser-tree-panel"
      style={{ height: '100%', borderRight: 'none', borderLeft: '1px solid #e5e7eb' }}
    >
      <div
        className="code-browser-tree-header"
        style={{ padding: '10px 16px', flexDirection: 'column', alignItems: 'stretch', gap: 10 }}
      >
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
          <span className="code-browser-tree-title">Propagation Trace</span>
          <Tag className="code-browser-tree-width">{activePath.path_length} hops</Tag>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {paths.length > 1 ? (
            <Segmented
              size="small"
              value={activePath.path_id}
              options={paths.map((path, index) => ({ label: `Path ${index + 1}`, value: path.path_id }))}
              onChange={(value) => {
                const nextPath = paths.find((item) => item.path_id === value);
                if (nextPath) {
                  onPathSelect(nextPath);
                }
              }}
            />
          ) : null}

          <Segmented<ViewMode>
            size="small"
            value={viewMode}
            options={[
              { label: 'Graph', value: 'graph' },
              { label: 'Raw', value: 'raw' },
            ]}
            onChange={(value) => setViewMode(value)}
          />
        </div>

        {viewMode === 'graph' ? (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
            <Text type="secondary" style={{ fontSize: 11 }}>
              {graph.nodes.length} visible nodes / {graph.rawNodeCount} raw nodes
            </Text>
            {graph.isStructuralOnly ? (
              <Text type="warning" style={{ fontSize: 11 }}>
                当前展示结构命中链，尚未识别到变量传播节点；可切换到 Raw 对照底层结果
              </Text>
            ) : null}
            {graph.edges.length === 0 && graph.rawNodeCount > 1 && !graph.isStructuralOnly ? (
              <Text type="warning" style={{ fontSize: 11 }}>
                当前只命中结构路径，未识别出参数传播链；可切换到 Raw 对照底层结果
              </Text>
            ) : null}
          </div>
        ) : (
          <Text type="secondary" style={{ fontSize: 11 }}>
            查看原始命中路径节点，便于和底层图结果对照
          </Text>
        )}
      </div>

      <div className="code-browser-tree-body" style={{ background: '#f8fafc' }}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12, padding: '12px 10px' }}>
          {viewMode === 'graph'
            ? graph.nodes.map((node, index) => (
                <React.Fragment key={node.key}>
                  {index > 0 && graph.edges[index - 1] ? renderGraphEdge(graph.edges[index - 1]) : null}
                  {renderGraphNode(node, index)}
                </React.Fragment>
              ))
            : activePath.steps.map((step, index) => renderRawStep(step, index))}
        </div>
      </div>
    </div>
  );
};

export default FindingPathViewer;
