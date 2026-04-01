import React, { useEffect, useMemo, useState } from 'react';
import {
  Button,
  Card,
  Col,
  Empty,
  Row,
  Space,
  Spin,
  Statistic,
  Tag,
  Timeline,
  Typography,
} from 'antd';
import {
  ArrowRightOutlined,
  BugOutlined,
  HistoryOutlined,
  ProjectOutlined,
  ScanOutlined,
} from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import dayjs from 'dayjs';
import relativeTime from 'dayjs/plugin/relativeTime';
import { getProjects } from '../services/projectVersion';
import { ScanService } from '../services/scan';
import { FindingService } from '../services/findings';
import { getAuditLogs } from '../services/logCenter';
import { useAuthStore } from '../store/useAuthStore';
import type { Finding } from '../types/finding';
import type { AuditLogItem } from '../types/logCenter';
import type { Job } from '../types/scan';
import './DashboardPage.css';

dayjs.extend(relativeTime);

const { Text } = Typography;

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

const getAuditOperatorLabel = (log: AuditLogItem): string => {
  const operatorUserId = log.operator_user_id?.trim();
  return operatorUserId && operatorUserId.length > 0 ? operatorUserId : '系统';
};

const getAuditResourceLabel = (log: AuditLogItem): string | null => {
  const resourceType = log.resource_type?.trim();
  const resourceId = log.resource_id?.trim();

  if (resourceType && resourceId) {
    return `${resourceType} / ${resourceId}`;
  }
  if (resourceType) {
    return resourceType;
  }
  if (resourceId) {
    return resourceId;
  }
  return null;
};

const DashboardPage: React.FC = () => {
  const navigate = useNavigate();
  const { user } = useAuthStore();
  const [loading, setLoading] = useState(true);
  const [data, setData] = useState<DashboardData>({
    projectCount: 0,
    scanCount: 0,
    findingCount: 0,
    auditCount: 0,
    recentScans: [],
    recentFindings: [],
    recentAudits: [],
  });

  const isAdmin = user?.role === 'Admin';

  useEffect(() => {
    const fetchDashboardData = async () => {
      try {
        setLoading(true);

        const auditLogsPromise = isAdmin
          ? getAuditLogs({ page: 1, page_size: 10 })
          : Promise.resolve(null);

        const [projectsRes, scansRes, findingsRes, auditsRes] = await Promise.all([
          getProjects({ page: 1, page_size: 1 }),
          ScanService.listJobs({ page: 1, page_size: 5 }),
          FindingService.listFindings({ page: 1, page_size: 5 }),
          auditLogsPromise,
        ]);

        setData({
          projectCount: projectsRes.data?.total || 0,
          scanCount: scansRes.total || 0,
          findingCount: findingsRes.total || 0,
          auditCount: auditsRes?.data?.total || 0,
          recentScans: scansRes.items || [],
          recentFindings: findingsRes.items || [],
          recentAudits: auditsRes?.data?.items || [],
        });
      } catch (error) {
        console.error('Failed to fetch dashboard data:', error);
      } finally {
        setLoading(false);
      }
    };

    void fetchDashboardData();
  }, [isAdmin]);

  const taskLogSummaryItems = useMemo(() => data.recentScans.slice(0, 5), [data.recentScans]);
  const kpiColumnSpan = isAdmin ? 6 : 8;

  const renderStatusBadge = (status: string) => {
    const normalizedStatus = status.toLowerCase();
    if (['running', 'queued', 'pending'].includes(normalizedStatus)) {
      return <span className="status-badge status-info">{status}</span>;
    }
    if (['success', 'completed', 'succeeded'].includes(normalizedStatus)) {
      return <span className="status-badge status-low">{status}</span>;
    }
    if (['failed', 'error'].includes(normalizedStatus)) {
      return <span className="status-badge status-high">{status}</span>;
    }
    return <span className="status-badge status-medium">{status}</span>;
  };

  const auditCardProps = {
    hoverable: true,
    onClick: () => navigate('/log-center'),
    className: 'dashboard-card--clickable',
  } as const;

  return (
    <div className="dashboard-container">
      <Spin spinning={loading}>
        <Row gutter={[16, 16]}>
          <Col xs={24} sm={12} lg={kpiColumnSpan}>
            <Card
              hoverable
              className="dashboard-card--clickable"
              onClick={() => navigate('/code-management')}
            >
              <Statistic title="纳管项目总数" value={data.projectCount} prefix={<ProjectOutlined />} />
            </Card>
          </Col>
          <Col xs={24} sm={12} lg={kpiColumnSpan}>
            <Card
              hoverable
              className="dashboard-card--clickable"
              onClick={() => navigate('/scans')}
            >
              <Statistic title="累计扫描任务" value={data.scanCount} prefix={<ScanOutlined />} />
            </Card>
          </Col>
          <Col xs={24} sm={12} lg={kpiColumnSpan}>
            <Card
              hoverable
              className="dashboard-card--clickable"
              onClick={() => navigate('/findings')}
            >
              <Statistic
                title="发现漏洞总数"
                value={data.findingCount}
                prefix={<BugOutlined />}
                styles={{
                  content: {
                    color: data.findingCount > 0 ? '#b91c1c' : '#15803d',
                  },
                }}
              />
            </Card>
          </Col>
          {isAdmin ? (
            <Col xs={24} sm={12} lg={6}>
              <Card data-testid="audit-count-card" {...auditCardProps}>
                <Statistic title="审计日志总数" value={data.auditCount} prefix={<HistoryOutlined />} />
              </Card>
            </Col>
          ) : null}
        </Row>

        <Row gutter={[16, 16]} style={{ marginTop: '16px' }}>
          <Col xs={24} lg={12}>
            <Card
              title={
                <div className="dashboard-section-title">
                  <ScanOutlined /> 今日任务聚焦
                </div>
              }
              extra={
                <Button type="link" onClick={() => navigate('/scans')}>
                  查看全部 <ArrowRightOutlined />
                </Button>
              }
              style={{ height: '100%' }}
            >
              {data.recentScans.length > 0 ? (
                <div className="dashboard-list">
                  {data.recentScans.map((job) => (
                    <div
                      key={job.id}
                      className="dashboard-list-item"
                      onClick={() => navigate('/scans')}
                    >
                      <div
                        style={{
                          display: 'flex',
                          justifyContent: 'space-between',
                          alignItems: 'flex-start',
                        }}
                      >
                        <div>
                          <div className="dashboard-item-title">任务 ID: {job.id.slice(0, 8)}...</div>
                          <div className="dashboard-item-meta">
                            <span>项目: {job.project_name || job.project_id.slice(0, 8)}</span>
                            <span>{dayjs(job.created_at).fromNow()}</span>
                          </div>
                        </div>
                        <div>{renderStatusBadge(job.status)}</div>
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
              title={
                <div className="dashboard-section-title">
                  <BugOutlined /> 最新漏洞发现
                </div>
              }
              extra={
                <Button type="link" onClick={() => navigate('/findings')}>
                  结果研判 <ArrowRightOutlined />
                </Button>
              }
              style={{ height: '100%' }}
            >
              {data.recentFindings.length > 0 ? (
                <div className="dashboard-list">
                  {data.recentFindings.map((finding) => (
                    <div
                      key={finding.id}
                      className="dashboard-list-item"
                      onClick={() => navigate('/findings')}
                    >
                      <div
                        style={{
                          display: 'flex',
                          justifyContent: 'space-between',
                          alignItems: 'flex-start',
                        }}
                      >
                        <div>
                          <div className="dashboard-item-title">{finding.rule_key}</div>
                          <div className="dashboard-item-meta">
                            <span>项目: {finding.project_id.slice(0, 8)}</span>
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

        <Row style={{ marginTop: '16px' }}>
          <Col span={24}>
            {isAdmin ? (
              <Card
                data-testid="recent-audit-card"
                title={
                  <div className="dashboard-section-title">
                    <HistoryOutlined /> 近期审计活动
                  </div>
                }
              >
                {data.recentAudits.length > 0 ? (
                  <div className="timeline-container">
                    <Timeline
                      items={data.recentAudits.map((log) => ({
                        color: log.result === 'SUCCEEDED' ? 'green' : 'red',
                        content: (
                          <div>
                            <Text strong>{getAuditOperatorLabel(log)}</Text>
                            <Text type="secondary" style={{ margin: '0 8px' }}>
                              执行了
                            </Text>
                            <Tag>{log.action_zh || log.action}</Tag>
                            <Text type="secondary" style={{ fontSize: '12px', marginLeft: '8px' }}>
                              {dayjs(log.created_at).format('YYYY-MM-DD HH:mm:ss')}
                            </Text>
                            {getAuditResourceLabel(log) ? (
                              <div
                                style={{
                                  fontSize: '12px',
                                  color: '#64748b',
                                  marginTop: '4px',
                                }}
                              >
                                资源: {getAuditResourceLabel(log)}
                              </div>
                            ) : null}
                          </div>
                        ),
                      }))}
                    />
                  </div>
                ) : (
                  <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无审计日志" />
                )}
              </Card>
            ) : (
              <Card
                data-testid="task-log-summary-card"
                title={
                  <div className="dashboard-section-title">
                    <HistoryOutlined /> 任务日志摘要
                  </div>
                }
              >
                {taskLogSummaryItems.length > 0 ? (
                  <div className="dashboard-list">
                    {taskLogSummaryItems.map((job) => (
                      <div key={job.id} className="dashboard-list-item">
                        <div
                          style={{
                            display: 'flex',
                            justifyContent: 'space-between',
                            alignItems: 'center',
                            gap: 16,
                          }}
                        >
                          <div>
                            <div className="dashboard-item-title">
                              扫描任务: {job.id.slice(0, 8)}...
                            </div>
                            <div className="dashboard-item-meta">
                              <span>项目: {job.project_name || job.project_id.slice(0, 8)}</span>
                              <span>{dayjs(job.created_at).fromNow()}</span>
                            </div>
                          </div>
                          <Space size={12}>
                            {renderStatusBadge(job.status)}
                            <Button
                              type="link"
                              onClick={() =>
                                navigate(`/task-logs?task_type=SCAN&task_id=${job.id}`)
                              }
                            >
                              查看日志
                            </Button>
                          </Space>
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div style={{ display: 'grid', gap: 12, justifyItems: 'center' }}>
                    <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无近期扫描任务" />
                    <Button type="primary" onClick={() => navigate('/task-logs')}>
                      进入任务日志
                    </Button>
                  </div>
                )}
              </Card>
            )}
          </Col>
        </Row>
      </Spin>
    </div>
  );
};

export default DashboardPage;
