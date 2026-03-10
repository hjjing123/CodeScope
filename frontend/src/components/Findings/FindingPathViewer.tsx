import React from 'react';
import { Typography, Tag } from 'antd';
import { ArrowDownOutlined, CodeOutlined, FileOutlined } from '@ant-design/icons';
import type { FindingPath, FindingPathStep } from '../../types/finding';
import '../ProjectVersion/CodeBrowser.css';

const { Text } = Typography;

interface FindingPathViewerProps {
  path: FindingPath;
  selectedStepId?: number | null;
  onStepClick: (step: FindingPathStep) => void;
}

const FindingPathViewer: React.FC<FindingPathViewerProps> = ({
  path,
  selectedStepId,
  onStepClick,
}) => {
  if (!path || !path.steps) return null;

  return (
    <div className="code-browser-tree-panel" style={{ height: '100%', borderRight: 'none', borderLeft: '1px solid #e5e7eb' }}>
      <div className="code-browser-tree-header" style={{ padding: '10px 16px' }}>
        <span className="code-browser-tree-title">Propagation Path</span>
        <Tag className="code-browser-tree-width">{path.path_length} steps</Tag>
      </div>

      <div className="code-browser-tree-body" style={{ background: '#f8fafc' }}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12, padding: '12px 8px' }}>
          {path.steps.map((step, index) => {
            const isSelected = selectedStepId === step.step_id;
            const isFirst = index === 0;
            const isLast = index === path.steps.length - 1;

            return (
              <React.Fragment key={step.step_id}>
                {/* Arrow Connector */}
                {!isFirst && (
                  <div style={{ display: 'flex', justifyContent: 'center', color: '#94a3b8' }}>
                    <ArrowDownOutlined style={{ fontSize: 14 }} />
                  </div>
                )}

                {/* Path Node Card (Light Theme) */}
                <div
                  onClick={() => onStepClick(step)}
                  style={{
                    background: '#ffffff',
                    border: `1px solid ${isSelected ? '#3b82f6' : '#e2e8f0'}`,
                    borderRadius: 8,
                    padding: 12,
                    cursor: 'pointer',
                    transition: 'all 0.2s',
                    boxShadow: isSelected 
                      ? '0 4px 6px -1px rgba(59, 130, 246, 0.1), 0 2px 4px -1px rgba(59, 130, 246, 0.06)' 
                      : '0 1px 2px 0 rgba(0, 0, 0, 0.05)',
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
                    {isFirst ? (
                      <FileOutlined style={{ color: '#16a34a' }} />
                    ) : (
                      <CodeOutlined style={{ color: isLast ? '#dc2626' : '#3b82f6' }} />
                    )}
                    <Tag
                      color={isFirst ? 'success' : isLast ? 'error' : 'processing'}
                      style={{ margin: 0, fontSize: 11, lineHeight: '18px' }}
                    >
                      {step.node_ref}
                    </Tag>
                  </div>

                  <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                    <div
                      style={{
                        color: '#334155',
                        fontFamily: 'var(--cs-font-mono)',
                        fontSize: 12,
                        background: '#f1f5f9',
                        padding: '6px 8px',
                        borderRadius: 4,
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        whiteSpace: 'nowrap',
                        border: '1px solid #e2e8f0'
                      }}
                      title={step.code_snippet || ''}
                    >
                      {step.code_snippet ? step.code_snippet.trim() : '(No snippet)'}
                    </div>

                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <Text type="secondary" style={{ fontSize: 11 }}>
                        Line {step.line}
                      </Text>
                      {step.func_name && (
                        <Text type="secondary" style={{ fontSize: 11, maxWidth: 120 }} ellipsis>
                          {step.func_name}
                        </Text>
                      )}
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
