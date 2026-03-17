import React from 'react';
import { Card, Descriptions, Tag, Typography, Empty, Space } from 'antd';
import { BugOutlined, FileTextOutlined, WarningOutlined } from '@ant-design/icons';
import type { Finding } from '../../types/finding';

const { Text, Title } = Typography;

const toRecord = (value: unknown): Record<string, unknown> =>
  value && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};

const toText = (value: unknown): string | null => {
  if (typeof value !== 'string') {
    return null;
  }
  const normalized = value.trim();
  return normalized || null;
};

const toPositiveInt = (value: unknown): number | null => {
  if (typeof value === 'number' && Number.isFinite(value) && value > 0) {
    return Math.trunc(value);
  }
  if (typeof value === 'string') {
    const parsed = Number.parseInt(value, 10);
    return Number.isFinite(parsed) && parsed > 0 ? parsed : null;
  }
  return null;
};

interface FindingContextPanelProps {
  finding?: Finding | null;
  loading?: boolean;
}

const FindingContextPanel: React.FC<FindingContextPanelProps> = ({ finding, loading }) => {
  const evidence = toRecord(finding?.evidence_json);
  const codeContext = toRecord(evidence.code_context);
  const focusContext = toRecord(codeContext.focus);
  const llmPayload = toRecord(evidence.llm_payload);
  const lineNumber =
    toPositiveInt(finding?.line_start) ??
    toPositiveInt(finding?.sink_line) ??
    toPositiveInt(finding?.source_line) ??
    toPositiveInt(focusContext.start_line) ??
    toPositiveInt(focusContext.line);
  const codeSnippet =
    toText(focusContext.snippet) ??
    toText((focusContext as { code_snippet?: unknown }).code_snippet) ??
    toText((llmPayload as { code_snippet?: unknown }).code_snippet);
  const cweId =
    toText(evidence.cwe_id) ??
    toText((llmPayload as { cwe_id?: unknown }).cwe_id) ??
    null;

  if (loading) {
    return <Card loading bordered={false} />;
  }

  if (!finding) {
    return (
      <div style={{ padding: 24, textAlign: 'center', color: '#999' }}>
        <Empty description="未关联漏洞上下文" image={Empty.PRESENTED_IMAGE_SIMPLE} />
      </div>
    );
  }

  return (
    <div style={{ padding: 16 }}>
      <div style={{ marginBottom: 16, display: 'flex', alignItems: 'center', gap: 8 }}>
        <BugOutlined style={{ fontSize: 20, color: '#ff4d4f' }} />
        <Title level={5} style={{ margin: 0 }} ellipsis={{ tooltip: finding.vuln_display_name }}>
          {finding.vuln_display_name || '未知漏洞'}
        </Title>
      </div>

      <Card size="small" bordered={false} style={{ background: '#fafafa', marginBottom: 16 }}>
        <Descriptions column={1} size="small">
          <Descriptions.Item label="严重程度">
            <Tag color={finding.severity === 'High' ? 'red' : finding.severity === 'Medium' ? 'orange' : 'blue'}>
              {finding.severity}
            </Tag>
          </Descriptions.Item>
          <Descriptions.Item label="文件路径">
            <Text code copyable ellipsis={{ tooltip: finding.file_path }}>
              {finding.file_path}
            </Text>
          </Descriptions.Item>
          <Descriptions.Item label="行号">
            {lineNumber ? `L${lineNumber}` : '-'}
          </Descriptions.Item>
        </Descriptions>
      </Card>

      <div style={{ marginBottom: 16 }}>
        <Space align="center" style={{ marginBottom: 8 }}>
          <FileTextOutlined />
          <Text strong>代码片段</Text>
        </Space>
        <div style={{ 
          background: '#1e1e1e', 
          color: '#d4d4d4', 
          padding: 12, 
          borderRadius: 6, 
          fontFamily: 'Consolas, monospace',
          fontSize: 12,
          overflowX: 'auto',
          maxHeight: 300
        }}>
          <pre style={{ margin: 0 }}>
            {codeSnippet || '// 无代码片段'}
          </pre>
        </div>
      </div>
      
      {cweId && (
        <div style={{ marginTop: 16 }}>
           <Space>
             <WarningOutlined />
             <Text type="secondary">CWE-{cweId}</Text>
           </Space>
        </div>
      )}
    </div>
  );
};

export default FindingContextPanel;
