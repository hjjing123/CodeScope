import React, { useMemo } from 'react';
import { Breadcrumb, Button, Layout, Space, Typography, theme } from 'antd';
import { useNavigate, useSearchParams } from 'react-router-dom';
import ReportHistoryTable from '../components/reports/ReportHistoryTable';
import type { ReportListParams } from '../types/report';

const { Content } = Layout;
const { Title } = Typography;

const ReportsPage: React.FC = () => {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const {
    token: { colorBgContainer, borderRadiusLG },
  } = theme.useToken();

  const reportJobId = searchParams.get('report_job_id') || undefined;
  const jobId = searchParams.get('job_id') || undefined;
  const previewReportId = searchParams.get('report_id') || undefined;

  const reportFilters = useMemo<ReportListParams>(
    () => ({
      report_job_id: reportJobId,
      job_id: jobId,
    }),
    [jobId, reportJobId]
  );

  const handleDeletedReportId = (deletedReportId: string) => {
    if (searchParams.get('report_id') !== deletedReportId) {
      return;
    }
    const next = new URLSearchParams(searchParams);
    next.delete('report_id');
    setSearchParams(next, { replace: true });
  };

  return (
    <Layout style={{ padding: '0 24px 24px', background: 'transparent' }}>
      <Breadcrumb
        style={{ margin: '16px 0' }}
        items={[{ title: '首页' }, { title: '报告中心' }]}
      />
      <Content
        style={{
          padding: '12px 24px 24px',
          margin: 0,
          minHeight: 280,
          background: colorBgContainer,
          borderRadius: borderRadiusLG,
        }}
      >
        <Space orientation="vertical" size={12} style={{ width: '100%' }}>
          <Title level={4} style={{ margin: 0 }}>
            报告中心
          </Title>

          {(reportJobId || jobId) && (
            <div
              style={{
                padding: '12px 16px',
                border: '1px solid #dbe3ee',
                borderRadius: 8,
                background: '#f8fafc',
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                gap: 12,
                flexWrap: 'wrap',
              }}
            >
              <span style={{ color: '#64748b' }}>
                当前列表已按来源任务筛选，生成中的结果会自动刷新。
              </span>
              <Button type="link" onClick={() => navigate('/reports')}>
                清除筛选
              </Button>
            </div>
          )}

          <ReportHistoryTable
            filters={reportFilters}
            autoRefresh={Boolean(reportJobId)}
            initialPreviewReportId={previewReportId}
            onDeletedReportId={handleDeletedReportId}
          />
        </Space>
      </Content>
    </Layout>
  );
};

export default ReportsPage;
