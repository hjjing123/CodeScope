import React, { useMemo } from 'react';
import { Layout, Breadcrumb, theme, Tabs, Button, Typography } from 'antd';
import type { TabsProps } from 'antd';
import { useNavigate, useSearchParams } from 'react-router-dom';
import ReportHistoryTable from '../components/reports/ReportHistoryTable';
import type { ReportListParams } from '../types/report';

const { Content } = Layout;
const { Text } = Typography;

const ReportsPage: React.FC = () => {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const {
    token: { colorBgContainer, borderRadiusLG },
  } = theme.useToken();

  const reportJobId = searchParams.get('report_job_id') || undefined;
  const jobId = searchParams.get('job_id') || undefined;

  const reportFilters = useMemo<ReportListParams>(() => ({
    report_job_id: reportJobId,
    job_id: jobId,
  }), [jobId, reportJobId]);

  const items: TabsProps['items'] = [
    {
      key: '1',
      label: '导出任务历史',
      children: (
        <ReportHistoryTable
          filters={reportFilters}
          autoRefresh={Boolean(reportJobId)}
        />
      ),
    },
  ];

  return (
    <Layout style={{ padding: '0 24px 24px', background: 'transparent' }}>
      <Breadcrumb
        style={{ margin: '16px 0' }}
        items={[
          { title: '首页' },
          { title: '报告中心' },
        ]}
      />
      <Content
        style={{
          padding: 24,
          margin: 0,
          minHeight: 280,
          background: colorBgContainer,
          borderRadius: borderRadiusLG,
        }}
      >
        {reportJobId && (
          <div
            style={{
              marginBottom: 16,
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
            <Text type="secondary">
              当前仅展示报告任务 {reportJobId.slice(0, 8)} 的生成结果，列表会自动刷新。
            </Text>
            <Button type="link" onClick={() => navigate('/reports')}>
              清除筛选
            </Button>
          </div>
        )}
        <Tabs defaultActiveKey="1" items={items} />
      </Content>
    </Layout>
  );
};

export default ReportsPage;
