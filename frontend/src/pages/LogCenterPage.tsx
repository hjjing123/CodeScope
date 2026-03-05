import React, { useMemo, useState } from 'react';
import type { Dayjs } from 'dayjs';
import dayjs from 'dayjs';
import {
  Alert,
  Button,
  Card,
  Collapse,
  DatePicker,
  Descriptions,
  Drawer,
  Form,
  Input,
  InputNumber,
  Segmented,
  Space,
  Statistic,
  Switch,
  Table,
  Tabs,
  Tag,
  Typography,
  message,
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import {
  CopyOutlined,
  DownloadOutlined,
  LinkOutlined,
  ReloadOutlined,
  SearchOutlined,
} from '@ant-design/icons';
import {
  downloadTaskLogs,
  getAuditLogs,
  getLogCorrelation,
  getRuntimeLogs,
  getTaskLogs,
} from '../services/logCenter';
import type {
  AuditLogItem,
  AuditLogQuery,
  CorrelationQuery,
  LogCorrelationPayload,
  RuntimeLogItem,
  RuntimeLogQuery,
  TaskLogPayload,
  TaskType,
} from '../types/logCenter';
import './LogCenterPage.css';

const { RangePicker } = DatePicker;
const { Text } = Typography;

type SystemLogMode = 'audit' | 'runtime';
type LogCenterTabKey = 'system' | 'task' | 'correlation';

interface AuditFilterValues {
  request_id?: string;
  project_id?: string;
  action?: string;
  result?: string;
  range?: [Dayjs, Dayjs];
}

interface RuntimeFilterValues {
  request_id?: string;
  project_id?: string;
  level?: string;
  module?: string;
  event?: string;
  range?: [Dayjs, Dayjs];
}

interface TaskFilterValues {
  task_type: TaskType;
  task_id: string;
  stage?: string;
  tail: number;
}

interface CorrelationFilterValues {
  request_id?: string;
  task_type?: TaskType;
  task_id?: string;
  project_id?: string;
  limit?: number;
  range?: [Dayjs, Dayjs];
}

type LogDetailState =
  | { kind: 'audit'; record: AuditLogItem }
  | { kind: 'runtime'; record: RuntimeLogItem }
  | null;

const DEFAULT_PAGE_SIZE = 20;

const normalizeText = (value: string | undefined): string | undefined => {
  const next = (value ?? '').trim();
  return next.length > 0 ? next : undefined;
};

const toRangeParams = (range: [Dayjs, Dayjs] | undefined): { start_time?: string; end_time?: string } => {
  if (!range || range.length !== 2) {
    return {};
  }
  return {
    start_time: range[0].toISOString(),
    end_time: range[1].toISOString(),
  };
};

const formatTime = (value: string | null | undefined): string => {
  if (!value) {
    return '--';
  }
  const parsed = dayjs(value);
  if (!parsed.isValid()) {
    return value;
  }
  return parsed.format('YYYY-MM-DD HH:mm:ss');
};

const formatJson = (value: Record<string, unknown>): string => {
  return JSON.stringify(value, null, 2);
};

const copyText = async (label: string, value: string): Promise<void> => {
  if (!value) {
    return;
  }
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(value);
    message.success(`${label} 已复制`);
    return;
  }

  const input = document.createElement('textarea');
  input.value = value;
  input.style.position = 'fixed';
  input.style.opacity = '0';
  document.body.appendChild(input);
  input.select();
  document.execCommand('copy');
  document.body.removeChild(input);
  message.success(`${label} 已复制`);
};

const taskTypeOptions: { label: string; value: TaskType }[] = [
  { label: '扫描任务', value: 'SCAN' },
  { label: '导入任务', value: 'IMPORT' },
  { label: '规则自测', value: 'SELFTEST' },
];

const LogCenterPage: React.FC = () => {
  const [activeTab, setActiveTab] = useState<LogCenterTabKey>('system');
  const [systemMode, setSystemMode] = useState<SystemLogMode>('audit');
  const [autoRefreshEnabled, setAutoRefreshEnabled] = useState(false);
  const [refreshIntervalSec, setRefreshIntervalSec] = useState(15);
  const [lastRefreshTime, setLastRefreshTime] = useState<string>('');
  const [auditForm] = Form.useForm<AuditFilterValues>();
  const [runtimeForm] = Form.useForm<RuntimeFilterValues>();
  const [taskForm] = Form.useForm<TaskFilterValues>();
  const [correlationForm] = Form.useForm<CorrelationFilterValues>();

  const [auditItems, setAuditItems] = useState<AuditLogItem[]>([]);
  const [auditTotal, setAuditTotal] = useState(0);
  const [auditPage, setAuditPage] = useState(1);
  const [auditPageSize, setAuditPageSize] = useState(DEFAULT_PAGE_SIZE);

  const [runtimeItems, setRuntimeItems] = useState<RuntimeLogItem[]>([]);
  const [runtimeTotal, setRuntimeTotal] = useState(0);
  const [runtimePage, setRuntimePage] = useState(1);
  const [runtimePageSize, setRuntimePageSize] = useState(DEFAULT_PAGE_SIZE);

  const [systemLoading, setSystemLoading] = useState(false);
  const [logDetail, setLogDetail] = useState<LogDetailState>(null);

  const [taskLoading, setTaskLoading] = useState(false);
  const [taskPayload, setTaskPayload] = useState<TaskLogPayload | null>(null);
  const [taskQuery, setTaskQuery] = useState<
    { taskType: TaskType; taskId: string; stage?: string; tail: number } | null
  >(null);

  const [correlationLoading, setCorrelationLoading] = useState(false);
  const [correlationPayload, setCorrelationPayload] = useState<LogCorrelationPayload | null>(null);
  const [correlationQuery, setCorrelationQuery] = useState<CorrelationQuery | null>(null);

  const activeTotal = systemMode === 'audit' ? auditTotal : runtimeTotal;
  const auditFailedCount = auditItems.filter((item) => item.result !== 'SUCCEEDED').length;
  const runtimeErrorCount = runtimeItems.filter(
    (item) => item.level === 'ERROR' || (item.status_code ?? 0) >= 500
  ).length;
  const taskStageCount = taskPayload?.items.length ?? 0;
  const correlationHitCount =
    (correlationPayload?.audit_logs.length ?? 0) +
    (correlationPayload?.runtime_logs.length ?? 0) +
    (correlationPayload?.task_log_previews.length ?? 0);

  const markRefreshed = () => {
    setLastRefreshTime(dayjs().format('HH:mm:ss'));
  };

  const loadAuditLogs = async (page = 1, pageSize = auditPageSize): Promise<void> => {
    const values = auditForm.getFieldsValue();
    const params: AuditLogQuery = {
      request_id: normalizeText(values.request_id),
      project_id: normalizeText(values.project_id),
      action: normalizeText(values.action),
      result: normalizeText(values.result),
      page,
      page_size: pageSize,
      ...toRangeParams(values.range),
    };

    setSystemLoading(true);
    try {
      const response = await getAuditLogs(params);
      setAuditItems(response.data.items);
      setAuditTotal(response.data.total);
      setAuditPage(page);
      setAuditPageSize(pageSize);
      markRefreshed();
    } finally {
      setSystemLoading(false);
    }
  };

  const loadRuntimeLogs = async (page = 1, pageSize = runtimePageSize): Promise<void> => {
    const values = runtimeForm.getFieldsValue();
    const params: RuntimeLogQuery = {
      request_id: normalizeText(values.request_id),
      project_id: normalizeText(values.project_id),
      level: normalizeText(values.level),
      module: normalizeText(values.module),
      event: normalizeText(values.event),
      page,
      page_size: pageSize,
      ...toRangeParams(values.range),
    };

    setSystemLoading(true);
    try {
      const response = await getRuntimeLogs(params);
      setRuntimeItems(response.data.items);
      setRuntimeTotal(response.data.total);
      setRuntimePage(page);
      setRuntimePageSize(pageSize);
      markRefreshed();
    } finally {
      setSystemLoading(false);
    }
  };

  React.useEffect(() => {
    taskForm.setFieldsValue({ task_type: 'SCAN', tail: 200 });
    correlationForm.setFieldsValue({ limit: 100 });
    void loadAuditLogs(1, DEFAULT_PAGE_SIZE);
  }, []);

  const auditColumns: ColumnsType<AuditLogItem> = useMemo(
    () => [
      {
        title: '时间',
        dataIndex: 'created_at',
        width: 170,
        render: (value: string) => <span className="log-center-code">{formatTime(value)}</span>,
      },
      {
        title: '动作',
        dataIndex: 'action',
        width: 180,
        ellipsis: true,
        render: (value: string) => <span className="log-center-code">{value || '--'}</span>,
      },
      {
        title: '资源',
        key: 'resource',
        width: 220,
        ellipsis: true,
        render: (_, record) => (
          <span className="log-center-code">{`${record.resource_type || '--'} / ${record.resource_id || '--'}`}</span>
        ),
      },
      {
        title: '结果',
        dataIndex: 'result',
        width: 96,
        render: (value: string) => (
          <Tag color={value === 'SUCCEEDED' ? 'blue' : 'red'}>{value || 'UNKNOWN'}</Tag>
        ),
      },
      {
        title: 'request_id',
        dataIndex: 'request_id',
        width: 220,
        ellipsis: true,
        render: (value: string) => (
          <Button
            type="link"
            size="small"
            className="log-center-inline-action"
            icon={<CopyOutlined />}
            onClick={(event) => {
              event.stopPropagation();
              void copyText('request_id', value);
            }}
          >
            <span className="log-center-code">{value || '--'}</span>
          </Button>
        ),
      },
      {
        title: '错误码',
        dataIndex: 'error_code',
        width: 160,
        render: (value: string | null) => <span className="log-center-code">{value || '--'}</span>,
      },
    ],
    []
  );

  const runtimeColumns: ColumnsType<RuntimeLogItem> = useMemo(
    () => [
      {
        title: '时间',
        dataIndex: 'occurred_at',
        width: 170,
        render: (value: string) => <span className="log-center-code">{formatTime(value)}</span>,
      },
      {
        title: '级别',
        dataIndex: 'level',
        width: 90,
        render: (value: string) => (
          <Tag color={value === 'ERROR' ? 'red' : value === 'WARN' ? 'gold' : 'blue'}>{value || '--'}</Tag>
        ),
      },
      {
        title: '模块/事件',
        key: 'module_event',
        width: 240,
        ellipsis: true,
        render: (_, record) => (
          <span className="log-center-code">{`${record.module || '--'} / ${record.event || '--'}`}</span>
        ),
      },
      {
        title: '消息',
        dataIndex: 'message',
        ellipsis: true,
      },
      {
        title: 'request_id',
        dataIndex: 'request_id',
        width: 220,
        ellipsis: true,
        render: (value: string) => (
          <Button
            type="link"
            size="small"
            className="log-center-inline-action"
            icon={<CopyOutlined />}
            onClick={(event) => {
              event.stopPropagation();
              void copyText('request_id', value);
            }}
          >
            <span className="log-center-code">{value || '--'}</span>
          </Button>
        ),
      },
      {
        title: '状态',
        width: 84,
        render: (_, record) => <span className="log-center-code">{record.status_code ?? '--'}</span>,
      },
      {
        title: '耗时(ms)',
        width: 90,
        render: (_, record) => <span className="log-center-code">{record.duration_ms ?? '--'}</span>,
      },
    ],
    []
  );

  const handleSystemModeChange = (value: string | number): void => {
    const nextMode = String(value) as SystemLogMode;
    setSystemMode(nextMode);
    if (nextMode === 'runtime' && runtimeItems.length === 0 && runtimeTotal === 0) {
      void loadRuntimeLogs(1, runtimePageSize);
    }
  };

  const handleTaskSearch = async (values: TaskFilterValues): Promise<void> => {
    const taskId = values.task_id.trim();
    if (!taskId) {
      message.warning('请填写任务 ID');
      return;
    }

    setTaskLoading(true);
    try {
      const response = await getTaskLogs(values.task_type, taskId, {
        stage: normalizeText(values.stage),
        tail: values.tail,
      });
      setTaskPayload(response.data);
      setTaskQuery({
        taskType: values.task_type,
        taskId,
        stage: normalizeText(values.stage),
        tail: values.tail,
      });
      markRefreshed();
    } finally {
      setTaskLoading(false);
    }
  };

  const handleTaskDownload = async (stage?: string): Promise<void> => {
    if (!taskQuery) {
      message.warning('请先查询任务日志');
      return;
    }

    const downloaded = await downloadTaskLogs(taskQuery.taskType, taskQuery.taskId, stage);
    message.success(`已下载 ${downloaded}`);
  };

  const handleCorrelationSearch = async (values: CorrelationFilterValues): Promise<void> => {
    const requestId = normalizeText(values.request_id);
    const taskId = normalizeText(values.task_id);
    const projectId = normalizeText(values.project_id);

    if (!requestId && !taskId && !projectId) {
      message.warning('请至少填写 request_id、task_id 或 project_id');
      return;
    }

    setCorrelationLoading(true);
    try {
      const response = await getLogCorrelation({
        request_id: requestId,
        task_type: values.task_type,
        task_id: taskId,
        project_id: projectId,
        limit: values.limit,
        ...toRangeParams(values.range),
      });
      setCorrelationQuery({
        request_id: requestId,
        task_type: values.task_type,
        task_id: taskId,
        project_id: projectId,
        limit: values.limit,
        ...toRangeParams(values.range),
      });
      setCorrelationPayload(response.data);
      markRefreshed();
    } finally {
      setCorrelationLoading(false);
    }
  };

  const runAutoRefresh = async (): Promise<void> => {
    if (activeTab === 'system') {
      if (systemMode === 'audit') {
        await loadAuditLogs(auditPage, auditPageSize);
      } else {
        await loadRuntimeLogs(runtimePage, runtimePageSize);
      }
      return;
    }

    if (activeTab === 'task') {
      if (!taskQuery) {
        return;
      }
      setTaskLoading(true);
      try {
        const response = await getTaskLogs(taskQuery.taskType, taskQuery.taskId, {
          stage: taskQuery.stage,
          tail: taskQuery.tail,
        });
        setTaskPayload(response.data);
        markRefreshed();
      } finally {
        setTaskLoading(false);
      }
      return;
    }

    if (!correlationQuery) {
      return;
    }
    setCorrelationLoading(true);
    try {
      const response = await getLogCorrelation(correlationQuery);
      setCorrelationPayload(response.data);
      markRefreshed();
    } finally {
      setCorrelationLoading(false);
    }
  };

  React.useEffect(() => {
    if (!autoRefreshEnabled) {
      return;
    }
    const timer = window.setInterval(() => {
      void runAutoRefresh();
    }, refreshIntervalSec * 1000);

    return () => {
      window.clearInterval(timer);
    };
  }, [
    activeTab,
    autoRefreshEnabled,
    auditPage,
    auditPageSize,
    correlationQuery,
    refreshIntervalSec,
    runtimePage,
    runtimePageSize,
    systemMode,
    taskQuery,
  ]);

  const taskLogItems = useMemo(() => {
    if (!taskPayload) {
      return [];
    }

    return taskPayload.items.map((entry) => ({
      key: entry.stage,
      label: (
        <div className="log-center-stage-label">
          <span className="log-center-code">{entry.stage}</span>
          <span>{entry.line_count} 行</span>
          {entry.truncated ? <Tag color="gold">已截断</Tag> : null}
        </div>
      ),
      children: (
        <div className="log-center-stage-body">
          <div className="log-center-stage-toolbar">
            <Button
              type="default"
              size="small"
              icon={<DownloadOutlined />}
              onClick={() => {
                void handleTaskDownload(entry.stage);
              }}
            >
              下载阶段日志
            </Button>
          </div>
          {entry.lines.length === 0 ? (
            <Alert type="info" showIcon message="当前阶段暂无日志输出。" />
          ) : (
            <div className="log-center-log-lines" role="log" aria-live="polite">
              {entry.lines.map((line, index) => (
                <p key={`${entry.stage}-${index}`} className="log-center-log-line">
                  <span className="log-center-line-number">{index + 1}</span>
                  <span className="log-center-line-content">{line}</span>
                </p>
              ))}
            </div>
          )}
        </div>
      ),
    }));
  }, [taskPayload]);

  return (
    <div className="log-center-page">
      <section className="log-center-hero" aria-label="日志中心概览">
        <div className="log-center-refresh-bar" aria-label="自动刷新控制">
          <Space size={10} wrap>
            <Text className="log-center-refresh-label">自动刷新</Text>
            <Switch
              checked={autoRefreshEnabled}
              onChange={(checked) => {
                setAutoRefreshEnabled(checked);
                if (checked) {
                  void runAutoRefresh();
                }
              }}
            />
            <Segmented
              options={[
                { label: '5s', value: 5 },
                { label: '10s', value: 10 },
                { label: '15s', value: 15 },
                { label: '30s', value: 30 },
                { label: '60s', value: 60 },
              ]}
              value={refreshIntervalSec}
              onChange={(value) => setRefreshIntervalSec(Number(value))}
              disabled={!autoRefreshEnabled}
            />
            <Text className="log-center-refresh-hint">仅轮询当前标签页</Text>
            <Text className="log-center-refresh-hint">上次刷新: {lastRefreshTime || '--'}</Text>
          </Space>

          <Button
            type="default"
            icon={<ReloadOutlined />}
            onClick={() => {
              void runAutoRefresh();
            }}
          >
            立即刷新
          </Button>
        </div>

        <div className="log-center-metrics" aria-label="日志指标速览">
          <Card className="log-center-metric-card" bordered={false}>
            <Statistic title="当前视图日志数" value={activeTotal} valueStyle={{ fontSize: 24 }} />
          </Card>
          <Card className="log-center-metric-card" bordered={false}>
            <Statistic title="操作失败（当前页）" value={auditFailedCount} valueStyle={{ fontSize: 24 }} />
          </Card>
          <Card className="log-center-metric-card" bordered={false}>
            <Statistic title="运行异常（当前页）" value={runtimeErrorCount} valueStyle={{ fontSize: 24 }} />
          </Card>
          <Card className="log-center-metric-card" bordered={false}>
            <Statistic title="关联命中数" value={correlationHitCount} valueStyle={{ fontSize: 24 }} />
          </Card>
        </div>
      </section>

      <Tabs
        className="log-center-tabs"
        activeKey={activeTab}
        onChange={(key) => setActiveTab(key as LogCenterTabKey)}
        items={[
          {
            key: 'system',
            label: '系统日志',
            children: (
              <section className="log-center-panel" aria-label="系统日志检索">
                <div className="log-center-panel-head">
                  <Segmented
                    value={systemMode}
                    onChange={handleSystemModeChange}
                    options={[
                      { label: '操作日志', value: 'audit' },
                      { label: '运行日志', value: 'runtime' },
                    ]}
                  />
                  <Button
                    type="default"
                    icon={<ReloadOutlined />}
                    onClick={() => {
                      void runAutoRefresh();
                    }}
                  >
                    刷新
                  </Button>
                </div>

                {systemMode === 'audit' ? (
                  <Form
                    form={auditForm}
                    layout="inline"
                    className="log-center-filter"
                    onFinish={() => {
                      void loadAuditLogs(1, auditPageSize);
                    }}
                  >
                    <Form.Item name="request_id">
                      <Input allowClear placeholder="request_id" className="log-center-input" />
                    </Form.Item>
                    <Form.Item name="project_id">
                      <Input allowClear placeholder="project_id" className="log-center-input" />
                    </Form.Item>
                    <Form.Item name="action">
                      <Input allowClear placeholder="action" className="log-center-input" />
                    </Form.Item>
                    <Form.Item name="result">
                      <Input allowClear placeholder="result: SUCCEEDED/FAILED" className="log-center-input" />
                    </Form.Item>
                    <Form.Item name="range">
                      <RangePicker showTime className="log-center-range" />
                    </Form.Item>
                    <Form.Item>
                      <Button type="primary" htmlType="submit" icon={<SearchOutlined />}>
                        查询
                      </Button>
                    </Form.Item>
                  </Form>
                ) : (
                  <Form
                    form={runtimeForm}
                    layout="inline"
                    className="log-center-filter"
                    onFinish={() => {
                      void loadRuntimeLogs(1, runtimePageSize);
                    }}
                  >
                    <Form.Item name="request_id">
                      <Input allowClear placeholder="request_id" className="log-center-input" />
                    </Form.Item>
                    <Form.Item name="project_id">
                      <Input allowClear placeholder="project_id" className="log-center-input" />
                    </Form.Item>
                    <Form.Item name="level">
                      <Input allowClear placeholder="level: INFO/WARN/ERROR" className="log-center-input" />
                    </Form.Item>
                    <Form.Item name="module">
                      <Input allowClear placeholder="module" className="log-center-input" />
                    </Form.Item>
                    <Form.Item name="event">
                      <Input allowClear placeholder="event" className="log-center-input" />
                    </Form.Item>
                    <Form.Item name="range">
                      <RangePicker showTime className="log-center-range" />
                    </Form.Item>
                    <Form.Item>
                      <Button type="primary" htmlType="submit" icon={<SearchOutlined />}>
                        查询
                      </Button>
                    </Form.Item>
                  </Form>
                )}

                {systemMode === 'audit' ? (
                  <Table<AuditLogItem>
                    className="log-center-table"
                    rowKey="id"
                    size="middle"
                    loading={systemLoading}
                    columns={auditColumns}
                    dataSource={auditItems}
                    pagination={{
                      current: auditPage,
                      pageSize: auditPageSize,
                      total: auditTotal,
                      showSizeChanger: true,
                      showTotal: (total) => `共 ${total} 条`,
                    }}
                    onChange={(pagination) => {
                      const page = pagination.current ?? 1;
                      const pageSize = pagination.pageSize ?? DEFAULT_PAGE_SIZE;
                      void loadAuditLogs(page, pageSize);
                    }}
                    onRow={(record) => ({
                      className: 'log-center-row',
                      onClick: () => {
                        setLogDetail({ kind: 'audit', record });
                      },
                    })}
                  />
                ) : (
                  <Table<RuntimeLogItem>
                    className="log-center-table"
                    rowKey="id"
                    size="middle"
                    loading={systemLoading}
                    columns={runtimeColumns}
                    dataSource={runtimeItems}
                    pagination={{
                      current: runtimePage,
                      pageSize: runtimePageSize,
                      total: runtimeTotal,
                      showSizeChanger: true,
                      showTotal: (total) => `共 ${total} 条`,
                    }}
                    onChange={(pagination) => {
                      const page = pagination.current ?? 1;
                      const pageSize = pagination.pageSize ?? DEFAULT_PAGE_SIZE;
                      void loadRuntimeLogs(page, pageSize);
                    }}
                    onRow={(record) => ({
                      className: 'log-center-row',
                      onClick: () => {
                        setLogDetail({ kind: 'runtime', record });
                      },
                    })}
                  />
                )}
              </section>
            ),
          },
          {
            key: 'task',
            label: '任务日志',
            children: (
              <section className="log-center-panel" aria-label="任务日志检索">
                <Form
                  form={taskForm}
                  layout="inline"
                  className="log-center-filter"
                  onFinish={(values) => {
                    void handleTaskSearch(values);
                  }}
                >
                  <Form.Item name="task_type" rules={[{ required: true, message: '请选择任务类型' }]}>
                    <Segmented options={taskTypeOptions} />
                  </Form.Item>
                  <Form.Item name="task_id" rules={[{ required: true, message: '请输入任务 ID' }]}>
                    <Input allowClear placeholder="task_id (UUID)" className="log-center-input log-center-input-wide" />
                  </Form.Item>
                  <Form.Item name="stage">
                    <Input allowClear placeholder="stage (可选)" className="log-center-input" />
                  </Form.Item>
                  <Form.Item name="tail" rules={[{ required: true, message: '请输入 tail 行数' }]}>
                    <InputNumber min={1} max={5000} className="log-center-input-number" />
                  </Form.Item>
                  <Form.Item>
                    <Space size={8}>
                      <Button type="primary" htmlType="submit" icon={<SearchOutlined />} loading={taskLoading}>
                        查询
                      </Button>
                      <Button
                        type="default"
                        icon={<DownloadOutlined />}
                        disabled={!taskQuery}
                        onClick={() => {
                          void handleTaskDownload(taskQuery?.stage);
                        }}
                      >
                        下载当前筛选
                      </Button>
                      <Button
                        type="default"
                        icon={<DownloadOutlined />}
                        disabled={!taskQuery}
                        onClick={() => {
                          void handleTaskDownload();
                        }}
                      >
                        下载全部
                      </Button>
                    </Space>
                  </Form.Item>
                </Form>

                <div className="log-center-task-summary">
                  <Statistic title="阶段数量" value={taskStageCount} />
                  <Text className="log-center-task-tip">
                    当前按任务类型 + 任务 ID 聚合日志，可按 stage 精确定位问题阶段。
                  </Text>
                </div>

                {taskPayload ? (
                  <Collapse className="log-center-collapse" items={taskLogItems} />
                ) : (
                  <Alert type="info" showIcon message="请先输入任务条件并点击查询。" />
                )}
              </section>
            ),
          },
          {
            key: 'correlation',
            label: '关联追踪',
            children: (
              <section className="log-center-panel" aria-label="关联追踪查询">
                <Form
                  form={correlationForm}
                  layout="inline"
                  className="log-center-filter"
                  onFinish={(values) => {
                    void handleCorrelationSearch(values);
                  }}
                >
                  <Form.Item name="request_id">
                    <Input allowClear placeholder="request_id" className="log-center-input" />
                  </Form.Item>
                  <Form.Item name="task_type">
                    <Segmented options={taskTypeOptions} />
                  </Form.Item>
                  <Form.Item name="task_id">
                    <Input allowClear placeholder="task_id" className="log-center-input log-center-input-wide" />
                  </Form.Item>
                  <Form.Item name="project_id">
                    <Input allowClear placeholder="project_id" className="log-center-input" />
                  </Form.Item>
                  <Form.Item name="limit">
                    <InputNumber min={1} max={500} className="log-center-input-number" />
                  </Form.Item>
                  <Form.Item name="range">
                    <RangePicker showTime className="log-center-range" />
                  </Form.Item>
                  <Form.Item>
                    <Button type="primary" htmlType="submit" icon={<LinkOutlined />} loading={correlationLoading}>
                      追踪
                    </Button>
                  </Form.Item>
                </Form>

                {correlationPayload ? (
                  <div className="log-center-correlation-grid">
                    <Card title={`操作日志 (${correlationPayload.audit_logs.length})`} size="small" bordered={false}>
                      <Table
                        rowKey="id"
                        size="middle"
                        className="log-center-table"
                        pagination={false}
                        dataSource={correlationPayload.audit_logs}
                        columns={[
                          {
                            title: '时间',
                            dataIndex: 'created_at',
                            width: 170,
                            render: (value: string) => <span className="log-center-code">{formatTime(value)}</span>,
                          },
                          {
                            title: 'action',
                            dataIndex: 'action',
                            ellipsis: true,
                            render: (value: string) => <span className="log-center-code">{value || '--'}</span>,
                          },
                          {
                            title: 'request_id',
                            dataIndex: 'request_id',
                            width: 220,
                            ellipsis: true,
                            render: (value: string) => <span className="log-center-code">{value || '--'}</span>,
                          },
                        ]}
                      />
                    </Card>

                    <Card title={`运行日志 (${correlationPayload.runtime_logs.length})`} size="small" bordered={false}>
                      <Table
                        rowKey="id"
                        size="middle"
                        className="log-center-table"
                        pagination={false}
                        dataSource={correlationPayload.runtime_logs}
                        columns={[
                          {
                            title: '时间',
                            dataIndex: 'occurred_at',
                            width: 170,
                            render: (value: string) => <span className="log-center-code">{formatTime(value)}</span>,
                          },
                          {
                            title: '事件',
                            dataIndex: 'event',
                            ellipsis: true,
                            render: (value: string) => <span className="log-center-code">{value || '--'}</span>,
                          },
                          {
                            title: '消息',
                            dataIndex: 'message',
                            ellipsis: true,
                          },
                        ]}
                      />
                    </Card>

                    <Card
                      title={`任务日志元数据 (${correlationPayload.task_log_previews.length})`}
                      size="small"
                      bordered={false}
                    >
                      <Table
                        rowKey={(item) => `${item.task_type}-${item.task_id}-${item.stage}`}
                        size="middle"
                        className="log-center-table"
                        pagination={false}
                        dataSource={correlationPayload.task_log_previews}
                        columns={[
                          {
                            title: 'task',
                            width: 260,
                            render: (_, item) => (
                              <span className="log-center-code">{`${item.task_type} / ${item.task_id}`}</span>
                            ),
                          },
                          {
                            title: 'stage',
                            dataIndex: 'stage',
                            width: 120,
                            render: (value: string) => <span className="log-center-code">{value}</span>,
                          },
                          {
                            title: '行数',
                            dataIndex: 'line_count',
                            width: 90,
                          },
                          {
                            title: '更新时间',
                            dataIndex: 'updated_at',
                            width: 170,
                            render: (value: string) => <span className="log-center-code">{formatTime(value)}</span>,
                          },
                        ]}
                      />
                    </Card>
                  </div>
                ) : (
                  <Alert type="info" showIcon message="请输入关联条件后点击追踪。" />
                )}
              </section>
            ),
          },
        ]}
      />

      <Drawer
        open={Boolean(logDetail)}
        width={540}
        onClose={() => setLogDetail(null)}
        title={logDetail?.kind === 'audit' ? '操作日志详情' : '运行日志详情'}
        className="log-center-detail-drawer"
      >
        {logDetail ? (
          <Space direction="vertical" size={12} className="log-center-detail-content">
            <Descriptions column={1} size="small" bordered>
              {logDetail.kind === 'audit' ? (
                <>
                  <Descriptions.Item label="时间">{formatTime(logDetail.record.created_at)}</Descriptions.Item>
                  <Descriptions.Item label="动作">
                    <span className="log-center-code">{logDetail.record.action || '--'}</span>
                  </Descriptions.Item>
                  <Descriptions.Item label="资源">
                    <span className="log-center-code">{`${logDetail.record.resource_type} / ${logDetail.record.resource_id}`}</span>
                  </Descriptions.Item>
                  <Descriptions.Item label="request_id">
                    <Button
                      type="link"
                      size="small"
                      icon={<CopyOutlined />}
                      onClick={() => {
                        void copyText('request_id', logDetail.record.request_id);
                      }}
                    >
                      <span className="log-center-code">{logDetail.record.request_id}</span>
                    </Button>
                  </Descriptions.Item>
                  <Descriptions.Item label="结果">{logDetail.record.result || '--'}</Descriptions.Item>
                </>
              ) : (
                <>
                  <Descriptions.Item label="时间">{formatTime(logDetail.record.occurred_at)}</Descriptions.Item>
                  <Descriptions.Item label="级别">{logDetail.record.level || '--'}</Descriptions.Item>
                  <Descriptions.Item label="服务/模块">
                    <span className="log-center-code">{`${logDetail.record.service || '--'} / ${logDetail.record.module || '--'}`}</span>
                  </Descriptions.Item>
                  <Descriptions.Item label="事件">
                    <span className="log-center-code">{logDetail.record.event || '--'}</span>
                  </Descriptions.Item>
                  <Descriptions.Item label="request_id">
                    <Button
                      type="link"
                      size="small"
                      icon={<CopyOutlined />}
                      onClick={() => {
                        void copyText('request_id', logDetail.record.request_id);
                      }}
                    >
                      <span className="log-center-code">{logDetail.record.request_id}</span>
                    </Button>
                  </Descriptions.Item>
                  <Descriptions.Item label="消息">{logDetail.record.message || '--'}</Descriptions.Item>
                </>
              )}
            </Descriptions>

            <div>
              <p className="log-center-json-title">detail_json</p>
              <pre className="log-center-json-block">{formatJson(logDetail.record.detail_json)}</pre>
            </div>
          </Space>
        ) : null}
      </Drawer>
    </div>
  );
};

export default LogCenterPage;
