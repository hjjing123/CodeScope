import React, { useEffect, useState, useRef } from 'react';
import { Drawer, Steps, Typography, Spin, Tag, Descriptions, Empty, Button, Space } from 'antd';
import type { StepsProps } from 'antd';
import { LoadingOutlined, ReloadOutlined } from '@ant-design/icons';
import { getScanAIEnrichment } from '../../services/ai';
import { ScanService } from '../../services/scan';
import type { AIEnrichmentJobPayload } from '../../types/ai';
import type { Job, JobLog } from '../../types/scan';
import dayjs from 'dayjs';
import { openSseStream } from '../../utils/sse';
import { formatCompactLocation, formatLocation } from '../../utils/findingLocation';

const { Text, Title } = Typography;
type StepStatus = NonNullable<StepsProps['items']>[number]['status'];

interface LiveSummaryState {
  total_findings: number;
  severity_counts: Record<string, number>;
}

interface LiveFindingItem {
  id: string;
  rule_key: string;
  vuln_display_name?: string | null;
  severity: string;
  file_path?: string | null;
  line_start?: number | null;
  entry_display?: string | null;
  path_length?: number | null;
}

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
  const [liveSummary, setLiveSummary] = useState<LiveSummaryState | null>(null);
  const [liveFindings, setLiveFindings] = useState<LiveFindingItem[]>([]);
  const [aiEnrichment, setAiEnrichment] = useState<AIEnrichmentJobPayload | null>(null);
  const [loading, setLoading] = useState(false);
  const logContainerRef = useRef<HTMLDivElement>(null);
  const logSeqRef = useRef(0);
  const eventIdRef = useRef(0);
  const logAbortRef = useRef<AbortController | null>(null);
  const eventAbortRef = useRef<AbortController | null>(null);

  // Fetch job details and logs
  const fetchData = async (isPolling = false) => {
    if (!jobId) return;

    try {
      if (!isPolling) setLoading(true);

      const [jobData, logData, aiData] = await Promise.all([
        ScanService.getJob(jobId),
        ScanService.getJobLogs(jobId, undefined, FULL_LOG_TAIL),
        getScanAIEnrichment(jobId).catch(() => null),
      ]);

      setJob(jobData);
      setLogs(logData);
      setAiEnrichment(aiData);
      setLiveSummary({
        total_findings: Number(jobData.result_summary?.total_findings || 0),
        severity_counts: (jobData.result_summary?.severity_counts as Record<string, number>) || {},
      });
      logSeqRef.current = logData.items.reduce(
        (total, item) => total + Number(item.line_count || 0),
        0
      );
    } catch (error) {
      console.error('Failed to fetch job details:', error);
    } finally {
      if (!isPolling) setLoading(false);
    }
  };

  const appendLogEvent = (payload: Record<string, unknown>) => {
    const stage = String(payload.stage || 'UNKNOWN');
    const line = String(payload.raw_line || payload.line || '');
    const seq = Number(payload.seq || 0);
    if (seq > 0) {
      logSeqRef.current = Math.max(logSeqRef.current, seq);
    }
    if (!line) {
      return;
    }
    setLogs((prev) => {
      const current = prev ?? { job_id: jobId || '', items: [] };
      const items = [...current.items];
      const index = items.findIndex((item) => item.stage === stage);
      if (index >= 0) {
        const target = items[index];
        items[index] = {
          ...target,
          lines: [...target.lines, line],
          line_count: Number(target.line_count || 0) + 1,
          truncated: false,
        };
      } else {
        items.push({ stage, lines: [line], line_count: 1, truncated: false });
      }
      return { ...current, items };
    });
  };

  const applyJobEvent = (eventName: string, payload: Record<string, unknown>) => {
    const eventId = Number(payload.id || 0);
    if (eventId > 0) {
      eventIdRef.current = Math.max(eventIdRef.current, eventId);
    }
    const innerPayload =
      payload.payload && typeof payload.payload === 'object'
        ? (payload.payload as Record<string, unknown>)
        : payload;

    if (eventName === 'job_status') {
      const nextStatus = String(innerPayload.status || '');
      setJob((prev) =>
        prev
          ? {
              ...prev,
              status: nextStatus || prev.status,
              stage: String(innerPayload.stage || prev.stage),
              failure_code: (innerPayload.failure_code as string | null) ?? prev.failure_code,
              failure_stage: (innerPayload.failure_stage as string | null) ?? prev.failure_stage,
            }
          : prev
      );
      return;
    }

    if (eventName === 'step_status') {
      setJob((prev) => {
        if (!prev) return prev;
        const nextSteps = prev.steps.map((step) =>
          step.step_key === String(innerPayload.step_key || '')
            ? {
                ...step,
                status: String(innerPayload.status || step.status),
                started_at: (innerPayload.started_at as string | null) ?? step.started_at,
                finished_at: (innerPayload.finished_at as string | null) ?? step.finished_at,
                duration_ms: (innerPayload.duration_ms as number | null) ?? step.duration_ms,
              }
            : step
        );
        return { ...prev, steps: nextSteps };
      });
      return;
    }

    if (eventName === 'summary_update') {
      setLiveSummary({
        total_findings: Number(innerPayload.total_findings || 0),
        severity_counts: (innerPayload.severity_counts as Record<string, number>) || {},
      });
      return;
    }

    if (eventName === 'finding_upsert') {
      const finding = innerPayload.finding as Record<string, unknown> | undefined;
      if (!finding) return;
      setLiveFindings((prev) => {
        const next: LiveFindingItem = {
          id: String(finding.id || ''),
          rule_key: String(finding.rule_key || ''),
          vuln_display_name: (finding.vuln_display_name as string | null) ?? null,
          severity: String(finding.severity || ''),
          file_path: (finding.file_path as string | null) ?? null,
          line_start: (finding.line_start as number | null) ?? null,
          entry_display: (finding.entry_display as string | null) ?? null,
          path_length: (finding.path_length as number | null) ?? null,
        };
        return [next, ...prev.filter((item) => item.id !== next.id)].slice(0, 10);
      });
      return;
    }

    if (eventName === 'done') {
      logAbortRef.current?.abort();
      eventAbortRef.current?.abort();
      fetchData(true);
    }
  };

  useEffect(() => {
    if (!visible || !jobId) {
      return;
    }

    const logAbort = new AbortController();
    const eventAbort = new AbortController();
    logAbortRef.current = logAbort;
    eventAbortRef.current = eventAbort;

    const pumpLogs = async () => {
      while (!logAbort.signal.aborted) {
        try {
          await openSseStream({
            url: ScanService.buildJobLogsStreamUrl(jobId, logSeqRef.current),
            signal: logAbort.signal,
            onEvent: ({ event, data }) => {
              if (event !== 'log' || typeof data !== 'object' || data === null) {
                return;
              }
              appendLogEvent(data as Record<string, unknown>);
            },
          });
        } catch (error) {
          if (!logAbort.signal.aborted) {
            console.error('Log SSE disconnected:', error);
          }
        }
      }
    };

    const pumpEvents = async () => {
      while (!eventAbort.signal.aborted) {
        try {
          await openSseStream({
            url: ScanService.buildJobEventsStreamUrl(jobId, eventIdRef.current),
            signal: eventAbort.signal,
            onEvent: ({ event, data }) => {
              if (typeof data !== 'object' || data === null) {
                return;
              }
              applyJobEvent(event, data as Record<string, unknown>);
            },
          });
        } catch (error) {
          if (!eventAbort.signal.aborted) {
            console.error('Event SSE disconnected:', error);
          }
        }
      }
    };

    void pumpLogs();
    void pumpEvents();

    return () => {
      logAbort.abort();
      eventAbort.abort();
    };
  }, [visible, jobId]);

  useEffect(() => {
    if (visible && jobId) {
      fetchData();
    } else {
      setJob(null);
      setLogs(null);
      setLiveSummary(null);
      setLiveFindings([]);
      logSeqRef.current = 0;
      eventIdRef.current = 0;
      logAbortRef.current?.abort();
      eventAbortRef.current?.abort();
      logAbortRef.current = null;
      eventAbortRef.current = null;
    }
  }, [visible, jobId]);

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

  const renderLiveFindings = () => {
    if (!liveSummary && liveFindings.length === 0) {
      return <Empty description="暂无实时发现" image={Empty.PRESENTED_IMAGE_SIMPLE} />;
    }

    return (
      <div style={{ border: '1px solid #E5E7EB', borderRadius: 8, padding: 16 }}>
        <div style={{ display: 'flex', gap: 16, marginBottom: 12, flexWrap: 'wrap' }}>
          <Text>发现数: {liveSummary?.total_findings ?? liveFindings.length}</Text>
          <Text>HIGH: {liveSummary?.severity_counts?.HIGH ?? 0}</Text>
          <Text>MED: {liveSummary?.severity_counts?.MED ?? 0}</Text>
          <Text>LOW: {liveSummary?.severity_counts?.LOW ?? 0}</Text>
        </div>
        <div style={{ display: 'grid', gap: 8 }}>
          {liveFindings.map((item) => (
            <div
              key={item.id}
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                gap: 12,
                padding: '10px 12px',
                background: '#F8FAFC',
                borderRadius: 6,
              }}
            >
              <div style={{ minWidth: 0 }}>
                <div style={{ fontWeight: 600 }}>{item.vuln_display_name || item.rule_key || '-'}</div>
                <div style={{ color: '#64748B' }} title={item.entry_display || formatLocation(item.file_path, item.line_start)}>
                  {item.entry_display || formatCompactLocation(item.file_path, item.line_start)}
                </div>
              </div>
              <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexShrink: 0 }}>
                <Tag color={item.severity === 'HIGH' ? 'red' : item.severity === 'MED' ? 'orange' : 'blue'}>
                  {item.severity || 'UNKNOWN'}
                </Tag>
                <Text type="secondary">path={item.path_length ?? '-'}</Text>
              </div>
            </div>
          ))}
        </div>
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
            <Descriptions.Item label="Project">
              <Space direction="vertical" size={0}>
                <Text>{job.project_name || job.project_id}</Text>
                <Text type="secondary" code>{job.project_id}</Text>
              </Space>
            </Descriptions.Item>
            <Descriptions.Item label="Version">
              <Space direction="vertical" size={0}>
                <Text>{job.version_name || job.version_id}</Text>
                <Text type="secondary" code>{job.version_id}</Text>
              </Space>
            </Descriptions.Item>
            <Descriptions.Item label="Rule Sets" span={2}>
              {formatPayloadList(job.payload?.rule_set_keys)}
            </Descriptions.Item>
            <Descriptions.Item label="Resolved Rules" span={2}>
              {formatPayloadList(job.payload?.resolved_rule_keys ?? job.payload?.rule_keys)}
            </Descriptions.Item>
            <Descriptions.Item label="AI 研判" span={2}>
              {aiEnrichment?.enabled ? (
                <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
                  <Tag color={aiEnrichment.latest_status === 'SUCCEEDED' ? 'green' : aiEnrichment.latest_status === 'FAILED' ? 'red' : 'blue'}>
                    {aiEnrichment.latest_status || 'QUEUED'}
                  </Tag>
                  <Text type="secondary">
                    已创建 {aiEnrichment.jobs.length} 个 AI 补充任务
                  </Text>
                </div>
              ) : (
                <Text type="secondary">本次扫描未开启 AI 异步研判</Text>
              )}
            </Descriptions.Item>
          </Descriptions>

          <Title level={5}>Pipeline Progress</Title>
          {renderSteps()}

          <Title level={5} style={{ marginTop: 24 }}>Live Findings</Title>
          {renderLiveFindings()}

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
