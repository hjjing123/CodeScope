import React, { useEffect, useState } from 'react';
import { Card, Col, Row, Statistic, Timeline, Tag, Spin, Button, Typography, Empty } from 'antd';
import {
  ProjectOutlined,
  ScanOutlined,
  BugOutlined,
  HistoryOutlined,
  ArrowRightOutlined,
} from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { getProjects } from '../services/projectVersion';
import { ScanService } from '../services/scan';
import { FindingService } from '../services/findings';
import { getAuditLogs } from '../services/logCenter';
import type { Job } from '../types/scan';
import type { Finding } from '../types/finding';
import type { AuditLogItem } from '../types/logCenter';
import dayjs from 'dayjs';
import relativeTime from 'dayjs/plugin/relativeTime';
import './DashboardPage.css';

dayjs.extend(relativeTime);

const { Title, Text } = Typography;

interface DashboardData {
  projectCount: number;
  scanCount: number;
  findingCount: number;
  auditCount: number;
  recentScans: Job[];
  recentFindings: Finding[];
  recentAudits: AuditLogItem[];
}

const severityColors: Record<string, string> = {
  critical: 'red',
  high: 'volcano',
  medium: 'orange',
  low: 'green',
  info: 'blue',
};

const DashboardPage: React.FC = () => {
  const navigate = useNavigate();
  const [loading, setLoading] = useState<boolean>(true);
  const [data, setData] = useState<DashboardData>({
    projectCount: 0,
    scanCount: 0,
    findingCount: 0,
    auditCount: 0,
    recentScans: [],
    recentFindings: [],
    recentAudits: [],
  });

  useEffect(() => {
    const fetchDashboardData = async () => {
      try {
        setLoading(true);
        const [projectsRes, scansRes, findingsRes, auditsRes] = await Promise.all([
          getProjects({ page: 1, page_size: 1 }),
          ScanService.listJobs({ page: 1, page_size: 5 }),
          FindingService.listFindings({ page: 1, page_size: 5 }),
          getAuditLogs({ page: 1, page_size: 10 }),
        ]);

        setData({
          projectCount: projectsRes.data?.total || 0,
          scanCount: scansRes.total || 0,
          findingCount: findingsRes.total || 0,
          auditCount: auditsRes.data?.total || 0,
          recentScans: scansRes.items || [],
          recentFindings: findingsRes.items || [],
          recentAudits: auditsRes.data?.items || [],
        });
      } catch (error) {
        console.error('Failed to fetch dashboard data:', error);
      } finally {
        setLoading(false);
      }
    };

    fetchDashboardData();
  }, []);

  const renderStatusBadge = (status: string) => {
    const s = status.toLowerCase();
    if (['running', 'queued', 'pending'].includes(s)) return <span className="status-badge status-info">{status}</span>;
    if (['success', 'completed'].includes(s)) return <span className="status-badge status-low">{status}</span>;
    if (['failed', 'error'].includes(s)) return <span className="status-badge status-high">{status}</span>;
    return <span className="status-badge status-medium">{status}</span>;
  };

  return (
    <div className="dashboard-container">
      <Spin spinning={loading}>
        {/* KPI Cards */}
        <Row gutter={[16, 16]}>
          <Col xs={24} sm={12} lg={6}>
            <Card hoverable onClick={() => navigate('/code-management')}>
              <Statistic
                title="纳管项目总数"
                value={data.projectCount}
                prefix={<ProjectOutlined />}
              />
            </Card>
          </Col>
          <Col xs={24} sm={12} lg={6}>
            <Card hoverable onClick={() => navigate('/scans')}>
              <Statistic
                title="累计扫描任务"
                value={data.scanCount}
                prefix={<ScanOutlined />}
              />
            </Card>
          </Col>
          <Col xs={24} sm={12} lg={6}>
            <Card hoverable onClick={() => navigate('/findings')}>
              <Statistic
                title="发现漏洞总数"
                value={data.findingCount}
                prefix={<BugOutlined />}
                valueStyle={{ color: data.findingCount > 0 ? '#b91c1c' : '#15803d' }}
              />
            </Card>
          </Col>
          <Col xs={24} sm={12} lg={6}>
            <Card hoverable onClick={() => navigate('/log-center')}>
              <Statistic
                title="审计日志总数"
                value={data.auditCount}
                prefix={<HistoryOutlined />}
              />
            </Card>
          </Col>
        </Row>

        {/* Tasks and Findings */}
        <Row gutter={[16, 16]} style={{ marginTop: '16px' }}>
          <Col xs={24} lg={12}>
            <Card 
              title={<div className="dashboard-section-title"><ScanOutlined /> 今日任务聚焦</div>}
              extra={<Button type="link" onClick={() => navigate('/scans')}>查看全部 <ArrowRightOutlined /></Button>}
              style={{ height: '100%' }}
            >
              {data.recentScans.length > 0 ? (
                <div className="dashboard-list">
                  {data.recentScans.map(job => (
                    <div key={job.id} className="dashboard-list-item" onClick={() => navigate('/scans')}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                        <div>
                          <div className="dashboard-item-title">任务 ID: {job.id.slice(0, 8)}...</div>
                          <div className="dashboard-item-meta">
                            <span>项目: {job.project_name || job.project_id.slice(0,8)}</span>
                            <span>{dayjs(job.created_at).fromNow()}</span>
                          </div>
                        </div>
                        <div>
                          {renderStatusBadge(job.status)}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无近期扫描任务" />
              )}
            </Card>
          </Col>
          
          <Col xs={24} lg={12}>
            <Card 
              title={<div className="dashboard-section-title"><BugOutlined /> 最新漏洞发现</div>}
              extra={<Button type="link" onClick={() => navigate('/findings')}>结果研判 <ArrowRightOutlined /></Button>}
              style={{ height: '100%' }}
            >
              {data.recentFindings.length > 0 ? (
                <div className="dashboard-list">
                  {data.recentFindings.map(finding => (
                    <div key={finding.id} className="dashboard-list-item" onClick={() => navigate('/findings')}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                        <div>
                          <div className="dashboard-item-title">{finding.rule_key}</div>
                          <div className="dashboard-item-meta">
                            <span>项目: {finding.project_id.slice(0,8)}</span>
                            <span>{dayjs(finding.created_at).fromNow()}</span>
                          </div>
                        </div>
                        <div>
                          <Tag color={severityColors[finding.severity.toLowerCase()] || 'default'}>
                            {finding.severity.toUpperCase()}
                          </Tag>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无未处理漏洞" />
              )}
            </Card>
          </Col>
        </Row>

        {/* Audit Logs */}
        <Row style={{ marginTop: '16px' }}>
          <Col span={24}>
            <Card title={<div className="dashboard-section-title"><HistoryOutlined /> 近期审计活动</div>}>
              {data.recentAudits.length > 0 ? (
                <div className="timeline-container">
                  <Timeline
                    items={data.recentAudits.map(log => ({
                      color: log.result === 'success' ? 'green' : 'red',
                      children: (
                        <div>
                          <Text strong>{log.operator_name || log.operator_id || '系统'}</Text>
                          <Text type="secondary" style={{ margin: '0 8px' }}>执行了</Text>
                          <Tag>{log.action}</Tag>
                          <Text type="secondary" style={{ fontSize: '12px', marginLeft: '8px' }}>
                            {dayjs(log.created_at).format('YYYY-MM-DD HH:mm:ss')}
                          </Text>
                          {log.resource_name && (
                            <div style={{ fontSize: '12px', color: '#64748b', marginTop: '4px' }}>
                              资源: {log.resource_name}
                            </div>
                          )}
                        </div>
                      )
                    }))}
                  />
                </div>
              ) : (
                <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无审计日志" />
              )}
            </Card>
          </Col>
        </Row>
      </Spin>
    </div>
  );
};

export default DashboardPage;
