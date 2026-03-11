import React from 'react';
import { Segmented, Tag, Tooltip, Typography } from 'antd';
import { ArrowDownOutlined, CodeOutlined, FileOutlined, NodeIndexOutlined } from '@ant-design/icons';
import type { FindingPath, FindingPathStep } from '../../types/finding';
import '../ProjectVersion/CodeBrowser.css';

const { Text } = Typography;

const hasValidLine = (line?: number | null) => typeof line === 'number' && line > 0;

const formatLocation = (filePath?: string | null, line?: number | null) => {
  if (!filePath) {
    return '-';
  }
  return hasValidLine(line) ? `${filePath}:${line}` : filePath;
};

const getStepRole = (index: number, total: number) => {
  if (index === 0) {
    return { label: 'Source', color: 'success' as const, accent: '#16a34a' };
  }
  if (index === total - 1) {
    return { label: 'Sink', color: 'error' as const, accent: '#dc2626' };
  }
  return {
    label: `Propagation ${index}`,
    color: 'processing' as const,
    accent: '#2563eb',
  };
};

interface FindingPathViewerProps {
  paths: FindingPath[];
  selectedPathId?: number | null;
  selectedStepId?: number | null;
  onPathSelect: (path: FindingPath) => void;
  onStepClick: (step: FindingPathStep) => void;
}

const FindingPathViewer: React.FC<FindingPathViewerProps> = ({
  paths,
  selectedPathId,
  selectedStepId,
  onPathSelect,
  onStepClick,
}) => {
  if (!paths.length) {
    return null;
  }

  const activePath =
    paths.find((item) => item.path_id === selectedPathId) ?? paths[0];

  return (
    <div className="code-browser-tree-panel" style={{ height: '100%', borderRight: 'none', borderLeft: '1px solid #e5e7eb' }}>
      <div className="code-browser-tree-header" style={{ padding: '10px 16px', flexDirection: 'column', alignItems: 'stretch' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
          <span className="code-browser-tree-title">Propagation Path</span>
          <Tag className="code-browser-tree-width">{activePath.path_length} hops</Tag>
        </div>
        {paths.length > 1 && (
          <Segmented
            size="small"
            value={activePath.path_id}
            options={paths.map((path, index) => ({
              label: `Path ${index + 1}`,
              value: path.path_id,
            }))}
            onChange={(value) => {
              const nextPath = paths.find((item) => item.path_id === value);
              if (nextPath) {
                onPathSelect(nextPath);
              }
            }}
          />
        )}
      </div>

      <div className="code-browser-tree-body" style={{ background: '#f8fafc' }}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12, padding: '12px 8px' }}>
          {activePath.steps.map((step, index) => {
            const isSelected = selectedStepId === step.step_id;
            const isFirst = index === 0;
            const role = getStepRole(index, activePath.steps.length);

            return (
              <React.Fragment key={`${activePath.path_id}-${step.step_id}`}>
                {!isFirst && (
                  <div style={{ display: 'flex', justifyContent: 'center', color: '#94a3b8' }}>
                    <ArrowDownOutlined style={{ fontSize: 14 }} />
                  </div>
                )}

                <div
                  onClick={() => onStepClick(step)}
                  style={{
                    background: '#ffffff',
                    border: `1px solid ${isSelected ? '#3b82f6' : '#e2e8f0'}`,
                    borderRadius: 10,
                    padding: 12,
                    cursor: 'pointer',
                    transition: 'all 0.2s',
                    boxShadow: isSelected
                      ? '0 4px 10px -2px rgba(59, 130, 246, 0.16)'
                      : '0 1px 2px 0 rgba(15, 23, 42, 0.06)',
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8, marginBottom: 10 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, minWidth: 0 }}>
                      {index === 0 ? (
                        <FileOutlined style={{ color: role.accent }} />
                      ) : index === activePath.steps.length - 1 ? (
                        <NodeIndexOutlined style={{ color: role.accent }} />
                      ) : (
                        <CodeOutlined style={{ color: role.accent }} />
                      )}
                      <Tag color={role.color} style={{ margin: 0 }}>{role.label}</Tag>
                    </div>
                    <Text type="secondary" style={{ fontSize: 11 }}>
                      Step {index + 1}/{activePath.steps.length}
                    </Text>
                  </div>

                  <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                    <Tooltip title={formatLocation(step.file, step.line)}>
                      <div
                        style={{
                          color: '#334155',
                          fontFamily: 'var(--cs-font-mono)',
                          fontSize: 12,
                          background: '#f8fafc',
                          padding: '6px 8px',
                          borderRadius: 6,
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
                            borderRadius: 6,
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

                    <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                      {step.func_name && (
                        <Text type="secondary" style={{ fontSize: 11 }} ellipsis>
                          Function: {step.func_name}
                        </Text>
                      )}
                      {!!step.labels.length && (
                        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                          {step.labels.slice(0, 4).map((label) => (
                            <Tag key={`${step.step_id}-${label}`} style={{ margin: 0 }}>
                              {label}
                            </Tag>
                          ))}
                        </div>
                      )}
                      <Tooltip title={step.node_ref}>
                        <Text type="secondary" style={{ fontSize: 11 }} ellipsis>
                          Ref: {step.node_ref}
                        </Text>
                      </Tooltip>
                    </div>
                  </div>
                </div>
              </React.Fragment>
            );
          })}
        </div>
      </div>
    </div>
  );
};

export default FindingPathViewer;
