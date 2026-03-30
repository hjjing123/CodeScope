import React, { useEffect, useMemo, useState } from 'react';
import { Alert, Modal, Space, Switch, Tag, Typography } from 'antd';
import { FileTextOutlined } from '@ant-design/icons';
import { ReportService } from '../../services/report';
import type { Finding } from '../../types/finding';
import type { ReportJobCreateRequest, ReportJobTriggerPayload } from '../../types/report';

const { Text } = Typography;

const getVulnDisplayName = (finding: Finding) => {
  return finding.vuln_display_name || finding.vuln_type || finding.rule_key || finding.id;
};

export interface ReportGenerationContext {
  projectId: string;
  versionId: string;
  jobId: string;
  generationMode: ReportJobCreateRequest['generation_mode'];
  findings: Finding[];
  findingCount: number;
}

interface ReportGenerationModalProps {
  open: boolean;
  context: ReportGenerationContext | null;
  onCancel: () => void;
  onSuccess: (payload: ReportJobTriggerPayload, context: ReportGenerationContext) => void;
}

const ReportGenerationModal: React.FC<ReportGenerationModalProps> = ({
  open,
  context,
  onCancel,
  onSuccess,
}) => {
  const [includeCodeSnippets, setIncludeCodeSnippets] = useState(true);
  const [includeAISections, setIncludeAISections] = useState(true);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!open) {
      return;
    }
    setIncludeCodeSnippets(true);
    setIncludeAISections(true);
  }, [open, context]);

  const previewFindings = useMemo(() => {
    if (!context || context.generationMode !== 'FINDING_SET') {
      return [];
    }
    return context.findings.slice(0, 3);
  }, [context]);

  const description = useMemo(() => {
    if (!context) {
      return '';
    }

    if (context.generationMode === 'JOB_ALL') {
      return `将为当前扫描任务下的 ${context.findingCount} 条漏洞分别生成 Markdown 报告。`;
    }

    if (context.findingCount === 1) {
      return '将为当前漏洞生成 1 份 Markdown 报告。';
    }

    return `将为选中的 ${context.findingCount} 条漏洞分别生成 Markdown 报告，并提供打包下载。`;
  }, [context]);

  const handleSubmit = async () => {
    if (!context) {
      return;
    }

    setSubmitting(true);
    try {
      const payload: ReportJobCreateRequest = {
        report_type: 'FINDING',
        generation_mode: context.generationMode,
        project_id: context.projectId,
        version_id: context.versionId,
        job_id: context.jobId,
        finding_ids:
          context.generationMode === 'FINDING_SET'
            ? context.findings.map((item) => item.id)
            : undefined,
        options: {
          format: 'MARKDOWN',
          include_code_snippets: includeCodeSnippets,
          include_ai_sections: includeAISections,
        },
      };
      const result = await ReportService.createReportJob(payload);
      onSuccess(result, context);
    } catch (error) {
      console.error('Failed to create report job:', error);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal
      title="生成漏洞报告"
      open={open}
      onCancel={onCancel}
      onOk={() => {
        void handleSubmit();
      }}
      confirmLoading={submitting}
      okText="提交生成任务"
      cancelText="取消"
      destroyOnHidden
    >
      <Space direction="vertical" size={16} style={{ width: '100%' }}>
        <Alert
          type="info"
          showIcon
          message="当前仅支持漏洞报告"
          description="后端现阶段只支持 FINDING 类型 Markdown 报告。提交后会异步生成，并可在报告中心查看结果。"
        />

        <div
          style={{
            border: '1px solid #dbe3ee',
            borderRadius: 8,
            padding: 12,
            background: '#f8fafc',
          }}
        >
          <Space direction="vertical" size={8} style={{ width: '100%' }}>
            <Text strong>{description}</Text>
            <Space size={[8, 8]} wrap>
              <Tag color="blue" icon={<FileTextOutlined />}>
                Markdown
              </Tag>
              <Tag color="geekblue">任务 {context?.jobId.slice(0, 8)}</Tag>
              {context?.generationMode === 'JOB_ALL' ? (
                <Tag color="gold">全量漏洞</Tag>
              ) : (
                <Tag color="cyan">已选 {context?.findingCount} 条</Tag>
              )}
            </Space>
            {previewFindings.length > 0 && (
              <Space direction="vertical" size={4}>
                {previewFindings.map((item) => (
                  <Text key={item.id} type="secondary">
                    - {getVulnDisplayName(item)}
                  </Text>
                ))}
                {context && context.findingCount > previewFindings.length && (
                  <Text type="secondary">
                    以及其余 {context.findingCount - previewFindings.length} 条漏洞
                  </Text>
                )}
              </Space>
            )}
          </Space>
        </div>

        <Space direction="vertical" size={12} style={{ width: '100%' }}>
          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              gap: 12,
            }}
          >
            <div>
              <Text strong>包含源码片段</Text>
              <br />
              <Text type="secondary">将漏洞附近的关键代码片段写入报告正文。</Text>
            </div>
            <Switch checked={includeCodeSnippets} onChange={setIncludeCodeSnippets} />
          </div>

          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              gap: 12,
            }}
          >
            <div>
              <Text strong>包含 AI 研判段落</Text>
              <br />
              <Text type="secondary">若漏洞已有 AI 研判结果，则一并写入报告。</Text>
            </div>
            <Switch checked={includeAISections} onChange={setIncludeAISections} />
          </div>
        </Space>
      </Space>
    </Modal>
  );
};

export default ReportGenerationModal;
