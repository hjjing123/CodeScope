import React from 'react';
import { Button, Drawer, Empty, Space, Spin, Tag, Typography } from 'antd';
import dayjs from 'dayjs';
import type { ReportPayload } from '../../types/report';

const { Paragraph, Text, Title } = Typography;

interface ReportPreviewDrawerProps {
  open: boolean;
  loading: boolean;
  report: ReportPayload | null;
  content: string;
  onClose: () => void;
  onDownload: () => void;
  downloading?: boolean;
}

const ReportPreviewDrawer: React.FC<ReportPreviewDrawerProps> = ({
  open,
  loading,
  report,
  content,
  onClose,
  onDownload,
  downloading = false,
}) => {
  return (
    <Drawer
      title={report?.title || '报告预览'}
      open={open}
      onClose={onClose}
      size="large"
      extra={
        <Space>
          <Button onClick={onClose}>关闭</Button>
          <Button type="primary" onClick={onDownload} disabled={!report} loading={downloading}>
            下载报告
          </Button>
        </Space>
      }
      destroyOnClose={false}
    >
      {loading ? (
        <div style={{ display: 'flex', justifyContent: 'center', padding: '64px 0' }}>
          <Spin />
        </div>
      ) : !report ? (
        <Empty description="未找到可预览的报告" />
      ) : (
        <Space orientation="vertical" size={16} style={{ width: '100%' }}>
          <div
            style={{
              border: '1px solid #e5e7eb',
              borderRadius: 12,
              padding: 16,
              background: '#f8fafc',
            }}
          >
            <Space orientation="vertical" size={8} style={{ width: '100%' }}>
              <Title level={5} style={{ margin: 0 }}>
                {report.title || report.file_name || `report-${report.id.slice(0, 8)}`}
              </Title>
              <Space size={[8, 8]} wrap>
                <Tag color="blue">{report.report_type}</Tag>
                {report.template_key ? <Tag color="geekblue">{report.template_key}</Tag> : null}
                <Tag color="gold">{report.format}</Tag>
                <Tag color="green">{dayjs(report.created_at).format('YYYY-MM-DD HH:mm:ss')}</Tag>
                {typeof report.finding_count === 'number' && report.report_type === 'SCAN' ? (
                  <Tag color="cyan">{report.finding_count} 条漏洞</Tag>
                ) : null}
              </Space>
              {report.summary_text ? (
                <Paragraph type="secondary" style={{ margin: 0 }}>
                  {report.summary_text}
                </Paragraph>
              ) : null}
            </Space>
          </div>

          {content ? (
            <div
              style={{
                border: '1px solid #e5e7eb',
                borderRadius: 12,
                background: '#ffffff',
                padding: 20,
              }}
            >
              <Text strong style={{ display: 'block', marginBottom: 12 }}>
                Markdown 预览
              </Text>
              <pre
                style={{
                  margin: 0,
                  whiteSpace: 'pre-wrap',
                  wordBreak: 'break-word',
                  fontFamily: 'Consolas, Monaco, monospace',
                  fontSize: 13,
                  lineHeight: 1.7,
                  color: '#111827',
                }}
              >
                {content}
              </pre>
            </div>
          ) : (
            <Empty description="报告内容为空" />
          )}
        </Space>
      )}
    </Drawer>
  );
};

export default ReportPreviewDrawer;
