import React, { useEffect, useMemo, useState } from 'react';
import { Alert, Modal, Space, Switch, Tag, Typography } from 'antd';
import { FileTextOutlined } from '@ant-design/icons';
import { ReportService } from '../../services/report';
import type { Finding } from '../../types/finding';
import type { ReportJobCreateRequest, ReportJobTriggerPayload } from '../../types/report';

const { Paragraph, Text } = Typography;

const getVulnDisplayName = (finding?: Finding | null) => {
  if (!finding) {
    return '-';
  }
  return finding.vuln_display_name || finding.vuln_type || finding.rule_key || finding.id;
};

export interface ReportGenerationContext {
  reportType: ReportJobCreateRequest['report_type'];
  projectId: string;
  versionId: string;
  jobId: string;
  findingId?: string;
  finding?: Finding | null;
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

  const description = useMemo(() => {
    if (!context) {
      return '';
    }

    if (context.reportType === 'SCAN') {
      return `将为当前扫描任务生成 1 份统一扫描报告，汇总 ${context.findingCount} 条漏洞，并按“结论摘要 + 技术附录”组织内容。`;
    }

    return '将为当前漏洞生成 1 份单漏洞报告，前半部分给老师/管理者看结论，后半部分提供开发与安全复核细节。';
  }, [context]);

  const handleSubmit = async () => {
    if (!context) {
      return;
    }

    setSubmitting(true);
    try {
      const payload: ReportJobCreateRequest = {
        report_type: context.reportType,
        project_id: context.projectId,
        version_id: context.versionId,
        job_id: context.jobId,
        finding_id: context.reportType === 'FINDING' ? context.findingId : undefined,
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
      title={context?.reportType === 'SCAN' ? '生成扫描报告' : '生成漏洞报告'}
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
      <Space orientation="vertical" size={16} style={{ width: '100%' }}>
        <Alert
          type="info"
          showIcon
          message="当前支持扫描报告与单漏洞报告"
          description="报告会先生成 Markdown 文件，随后可在报告中心中直接预览与下载。"
        />

        <div
          style={{
            border: '1px solid #dbe3ee',
            borderRadius: 8,
            padding: 12,
            background: '#f8fafc',
          }}
        >
          <Space orientation="vertical" size={8} style={{ width: '100%' }}>
            <Text strong>{description}</Text>
            <Space size={[8, 8]} wrap>
              <Tag color="blue" icon={<FileTextOutlined />}>
                Markdown
              </Tag>
              <Tag color="geekblue">任务 {context?.jobId.slice(0, 8)}</Tag>
              <Tag color={context?.reportType === 'SCAN' ? 'gold' : 'cyan'}>
                {context?.reportType === 'SCAN' ? `扫描报告 · ${context?.findingCount ?? 0} 条漏洞` : '单漏洞报告'}
              </Tag>
            </Space>
            {context?.reportType === 'FINDING' && context.finding ? (
              <Paragraph type="secondary" style={{ marginBottom: 0 }}>
                当前漏洞：{getVulnDisplayName(context.finding)}
              </Paragraph>
            ) : null}
          </Space>
        </div>

        <Space orientation="vertical" size={12} style={{ width: '100%' }}>
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
              <Text type="secondary">在技术附录中带上关键代码片段，方便研发快速定位。</Text>
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
              <Text type="secondary">若已有 AI 研判结果，则将摘要并入技术附录。</Text>
            </div>
            <Switch checked={includeAISections} onChange={setIncludeAISections} />
          </div>
        </Space>
      </Space>
    </Modal>
  );
};

export default ReportGenerationModal;
