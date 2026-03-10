import React, { useEffect, useState, useRef } from 'react';
import { Drawer, Steps, Typography, Spin, Tag, Descriptions, Empty, Button } from 'antd';
import type { StepsProps } from 'antd';
import { LoadingOutlined, ReloadOutlined } from '@ant-design/icons';
import { ScanService } from '../../services/scan';
import type { Job, JobLog } from '../../types/scan';
import dayjs from 'dayjs';

const { Text, Title } = Typography;
type StepStatus = NonNullable<StepsProps['items']>[number]['status'];

const TERMINAL_JOB_STATUSES = new Set(['SUCCEEDED', 'FAILED', 'CANCELED', 'TIMEOUT']);
const FULL_LOG_TAIL = 0;
const DEFAULT_STEPS = [
  { title: '源码准备', key: 'prepare' },
  { title: 'Joern 解析与导图', key: 'joern' },
  { title: '导入 Neo4j', key: 'neo4j_import' },
  { title: '图增强', key: 'post_labels' },
  { title: '规则扫描', key: 'rules' },
  { title: '结果聚合与落库', key: 'aggregate' },
  { title: '结果标准化与 AI 摘要', key: 'ai' },
  { title: '归档结果', key: 'archive' },
  { title: '清理资源', key: 'cleanup' },
];

const STAGE_TO_STEP_KEY: Record<string, string> = {
  Prepare: 'prepare',
  Analyze: 'joern',
  Query: 'rules',
  Aggregate: 'aggregate',
  AI: 'ai',
  Cleanup: 'cleanup',
};

const formatPayloadList = (value: unknown) => {
  if (!Array.isArray(value) || value.length === 0) {
    return '-';
  }

  const items = value
    .filter((item): item is string => typeof item === 'string' && item.trim().length > 0)
    .map((item) => item.trim());

  return items.length > 0 ? items.join(', ') : '-';
};

interface ScanDetailDrawerProps {
  visible: boolean;
  jobId: string | null;
  onClose: () => void;
}

const ScanDetailDrawer: React.FC<ScanDetailDrawerProps> = ({ visible, jobId, onClose }) => {
  const [job, setJob] = useState<Job | null>(null);
  const [logs, setLogs] = useState<JobLog | null>(null);
  const [loading, setLoading] = useState(false);
  const logContainerRef = useRef<HTMLDivElement>(null);
  const pollingRef = useRef<number | null>(null);

  // Fetch job details and logs
  const fetchData = async (isPolling = false) => {
    if (!jobId) return;

    try {
      if (!isPolling) setLoading(true);
      
      const [jobData, logData] = await Promise.all([
        ScanService.getJob(jobId),
        ScanService.getJobLogs(jobId, undefined, FULL_LOG_TAIL)
      ]);

      setJob(jobData);
      setLogs(logData);
    } catch (error) {
      console.error('Failed to fetch job details:', error);
    } finally {
      if (!isPolling) setLoading(false);
    }
  };

  useEffect(() => {
    if (visible && jobId) {
      fetchData();
    } else {
      setJob(null);
      setLogs(null);
      if (pollingRef.current) {
        window.clearInterval(pollingRef.current);
        pollingRef.current = null;
      }
    }
  }, [visible, jobId]);

  // Polling logic
  useEffect(() => {
    if (!visible || !job) return;

    const isTerminal = TERMINAL_JOB_STATUSES.has(job.status);

    if (!isTerminal) {
      if (!pollingRef.current) {
        pollingRef.current = window.setInterval(() => {
          fetchData(true);
        }, 3000);
      }
    } else {
      if (pollingRef.current) {
        window.clearInterval(pollingRef.current);
        pollingRef.current = null;
      }
    }

    return () => {
      if (pollingRef.current) {
        window.clearInterval(pollingRef.current);
        pollingRef.current = null;
      }
    };
  }, [visible, job?.status]);

  // Auto-scroll logs
  useEffect(() => {
    if (logContainerRef.current) {
      logContainerRef.current.scrollTop = logContainerRef.current.scrollHeight;
    }
  }, [logs]);

  const getStepStatus = (stepStatus: string): StepStatus => {
    switch (stepStatus.toLowerCase()) {
      case 'pending':
        return 'wait';
      case 'running':
        return 'process';
      case 'succeeded':
        return 'finish';
      case 'failed':
      case 'canceled':
        return 'error';
      default:
        return 'wait';
    }
  };

  const renderSteps = () => {
    if (!job) return null;

    let items: StepsProps['items'] = [];

    if (job.steps && job.steps.length > 0) {
      items = job.steps.map((step) => ({
        title: step.display_name === '图增强 post_labels' ? '图增强' : step.display_name,
        status: getStepStatus(step.status),
        description: step.duration_ms ? `${(step.duration_ms / 1000).toFixed(2)}s` : null,
        icon: step.status.toLowerCase() === 'running' ? <LoadingOutlined /> : undefined,
      }));
    } else {
      const currentStepKey = STAGE_TO_STEP_KEY[job.stage];
      const currentStageIndex = Math.max(
        0,
        DEFAULT_STEPS.findIndex((step) => step.key === currentStepKey)
      );

      items = DEFAULT_STEPS.map((step, index) => {
        let status = 'wait';
        if (index < currentStageIndex) status = 'finish';
        if (index === currentStageIndex) {
          status = job.status === 'FAILED' || job.status === 'TIMEOUT' || job.status === 'CANCELED'
            ? 'error'
            : (job.status === 'RUNNING' ? 'process' : 'wait');
        }
        if (job.status === 'SUCCEEDED') status = 'finish';

        return {
          title: step.title,
          status: status as 'wait' | 'process' | 'finish' | 'error',
        };
      });
    }

    return (
      <Steps
        items={items}
        labelPlacement="vertical"
        style={{ marginBottom: 24 }}
      />
    );
  };

  const renderLogs = () => {
    if (!logs || !logs.items || logs.items.length === 0) {
      return (
        <div style={{ 
          background: '#0F172A', 
          color: '#E2E8F0', 
          padding: 16, 
          borderRadius: 8, 
          height: 400, 
          display: 'flex', 
          alignItems: 'center', 
          justifyContent: 'center',
          fontFamily: "'Fira Code', monospace"
        }}>
          <Text type="secondary" style={{ color: '#64748B' }}>No logs available</Text>
        </div>
      );
    }

    return (
      <div 
        ref={logContainerRef}
        style={{ 
          background: '#0F172A', 
          color: '#E2E8F0', 
          padding: 16, 
          borderRadius: 8, 
          height: 400, 
          overflowY: 'auto',
          fontFamily: "'Fira Code', monospace",
          fontSize: 13,
          lineHeight: 1.5,
          whiteSpace: 'pre-wrap'
        }}
      >
        {logs.items.map((item, idx) => (
          <div key={idx} style={{ marginBottom: 8 }}>
            <div style={{ color: '#94A3B8', marginBottom: 4, fontWeight: 'bold' }}>
              [{item.stage}] 共 {item.line_count} 行
              {item.truncated ? `，当前仅显示最后 ${item.lines.length} 行` : ''}
            </div>
            {item.lines.map((line, lineIdx) => (
              <div key={`${idx}-${lineIdx}`}>{line}</div>
            ))}
          </div>
        ))}
      </div>
    );
  };

  return (
    <Drawer
      title={
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span>Scan Details</span>
          {job && (
            <Tag
              color={
                job.status === 'SUCCEEDED'
                  ? 'green'
                  : job.status === 'FAILED' || job.status === 'TIMEOUT'
                    ? 'red'
                    : job.status === 'CANCELED'
                      ? 'orange'
                      : 'blue'
              }
            >
              {job.status}
            </Tag>
          )}
        </div>
      }
      placement="right"
      width={1200}
      onClose={onClose}
      open={visible}
      extra={
        <Button icon={<ReloadOutlined />} onClick={() => fetchData()}>
          Refresh
        </Button>
      }
    >
      {loading && !job ? (
        <div style={{ display: 'flex', justifyContent: 'center', padding: 40 }}>
          <Spin size="large" />
        </div>
      ) : job ? (
        <>
          <Descriptions column={2} size="small" style={{ marginBottom: 24 }}>
            <Descriptions.Item label="Job ID">
              <Text code>{job.id}</Text>
            </Descriptions.Item>
            <Descriptions.Item label="Created At">
              {dayjs(job.created_at).format('YYYY-MM-DD HH:mm:ss')}
            </Descriptions.Item>
            <Descriptions.Item label="Project ID">
              <Text code>{job.project_id}</Text>
            </Descriptions.Item>
            <Descriptions.Item label="Version ID">
              <Text code>{job.version_id}</Text>
            </Descriptions.Item>
            <Descriptions.Item label="Rule Sets" span={2}>
              {formatPayloadList(job.payload?.rule_set_keys)}
            </Descriptions.Item>
            <Descriptions.Item label="Resolved Rules" span={2}>
              {formatPayloadList(job.payload?.resolved_rule_keys ?? job.payload?.rule_keys)}
            </Descriptions.Item>
          </Descriptions>

          <Title level={5}>Pipeline Progress</Title>
          {renderSteps()}

          <Title level={5} style={{ marginTop: 24 }}>Execution Logs</Title>
          {renderLogs()}
        </>
      ) : (
        <Empty description="Job not found" />
      )}
    </Drawer>
  );
};

export default ScanDetailDrawer;
