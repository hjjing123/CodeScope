import React, { useMemo, useState } from 'react';
import type { Dayjs } from 'dayjs';
import dayjs from 'dayjs';
import {
  Alert,
  Button,
  Card,
  Collapse,
  Col,
  DatePicker,
  Descriptions,
  Drawer,
  Form,
  Input,
  InputNumber,
  Modal,
  Row,
  Segmented,
  Select,
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
  DeleteOutlined,
  DownloadOutlined,
  LinkOutlined,
  ReloadOutlined,
  SearchOutlined,
} from '@ant-design/icons';
import {
  batchDeleteLogs,
  deleteSingleLog,
  downloadTaskLogs,
  getAuditLogs,
  getLogCorrelation,
  getTaskLogs,
} from '../services/logCenter';
import type {
  AuditLogItem,
  AuditLogQuery,
  CorrelationQuery,
  LogCorrelationPayload,
  TaskLogPayload,
  TaskType,
} from '../types/logCenter';

const { RangePicker } = DatePicker;
const { Text } = Typography;

type LogCenterTabKey = 'system' | 'task' | 'correlation';

interface AuditFilterValues {
  request_id?: string;
  project_id?: string;
  action?: string;
  action_group?: string;
  result?: string;
  keyword?: string;
  high_value_only?: boolean;
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

type LogDetailState = { kind: 'audit'; record: AuditLogItem } | null;

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

const actionGroupOptions = [
  { label: '认证与会话', value: 'AUTH' },
  { label: '权限与成员', value: 'PERMISSION' },
  { label: '项目与代码快照', value: 'PROJECT' },
  { label: '规则与规则集', value: 'RULE' },
  { label: '导入与扫描', value: 'SCAN' },
  { label: '结果与修复', value: 'FINDING' },
  { label: '报告与导出', value: 'REPORT' },
  { label: '任务与执行器', value: 'TASK' },
  { label: '平台运维', value: 'SYSTEM' },
  { label: '其他', value: 'OTHER' },
];

const resultOptions = [
  { label: '成功', value: 'SUCCEEDED' },
  { label: '失败', value: 'FAILED' },
];

const hasBatchDeleteCondition = (values: AuditFilterValues): boolean => {
  return Boolean(
    normalizeText(values.request_id) ||
      normalizeText(values.project_id) ||
      normalizeText(values.keyword) ||
      normalizeText(values.action_group) ||
      values.high_value_only ||
      (values.range && values.range.length === 2)
  );
};

const LogCenterPage: React.FC = () => {
  const [activeTab, setActiveTab] = useState<LogCenterTabKey>('system');
  const [autoRefreshEnabled, setAutoRefreshEnabled] = useState(false);
  const [refreshIntervalSec, setRefreshIntervalSec] = useState(15);
  const [lastRefreshTime, setLastRefreshTime] = useState<string>('');
  const [auditForm] = Form.useForm<AuditFilterValues>();
  const [taskForm] = Form.useForm<TaskFilterValues>();
  const [correlationForm] = Form.useForm<CorrelationFilterValues>();

  const [auditItems, setAuditItems] = useState<AuditLogItem[]>([]);
  const [auditTotal, setAuditTotal] = useState(0);
  const [auditPage, setAuditPage] = useState(1);
  const [auditPageSize, setAuditPageSize] = useState(DEFAULT_PAGE_SIZE);

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

  const activeTotal = auditTotal;
  const auditFailedCount = auditItems.filter((item) => item.result !== 'SUCCEEDED').length;
  const auditHighValueCount = auditItems.filter((item) => item.is_high_value).length;
  const taskStageCount = taskPayload?.items.length ?? 0;
  const correlationHitCount =
    (correlationPayload?.audit_logs.length ?? 0) +
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
      action_group: normalizeText(values.action_group),
      result: normalizeText(values.result),
      keyword: normalizeText(values.keyword),
      high_value_only: Boolean(values.high_value_only),
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

  const handleDeleteLog = (record: AuditLogItem): void => {
    Modal.confirm({
      title: '确认删除日志',
      content: '删除后不可恢复，是否继续？',
      okText: '确认删除',
      okButtonProps: { danger: true },
      cancelText: '取消',
      onOk: async () => {
        await deleteSingleLog(record.id);
        message.success('日志删除成功');
        if (logDetail && logDetail.record.id === record.id) {
          setLogDetail(null);
        }
        await loadAuditLogs(auditPage, auditPageSize);
      },
    });
  };

  const handleBatchDelete = (): void => {
    const values = auditForm.getFieldsValue();
    if (!hasBatchDeleteCondition(values)) {
      message.warning('请至少设置一个筛选条件后再批量删除');
      return;
    }
    Modal.confirm({
      title: '确认批量删除操作日志',
      content: '将删除当前筛选条件命中的操作日志，删除后不可恢复。',
      okText: '确认删除',
      okButtonProps: { danger: true },
      cancelText: '取消',
      onOk: async () => {
        const response = await batchDeleteLogs({
          log_kind: 'OPERATION',
          request_id: normalizeText(values.request_id),
          project_id: normalizeText(values.project_id),
          keyword: normalizeText(values.keyword),
          action_group: normalizeText(values.action_group),
          high_value_only: Boolean(values.high_value_only),
          ...toRangeParams(values.range),
        });
        message.success(`已删除 ${response.data.deleted_count} 条日志`);
        await loadAuditLogs(auditPage, auditPageSize);
      },
    });
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
        render: (value: string) => <span style={{ fontFamily: 'monospace', fontSize: 12 }}>{formatTime(value)}</span>,
      },
      {
        title: '动作',
        dataIndex: 'action_zh',
        width: 240,
        ellipsis: true,
        render: (_: string, record) => (
          <div style={{ display: 'grid', gap: 2 }}>
            <span>{record.action_zh || record.action || '--'}</span>
            <span style={{ fontFamily: 'monospace', fontSize: 12, color: '#999' }}>{record.action || '--'}</span>
          </div>
        ),
      },
      {
        title: '摘要',
        dataIndex: 'summary_zh',
        ellipsis: true,
        render: (value: string) => value || '--',
      },
      {
        title: '资源',
        key: 'resource',
        width: 200,
        ellipsis: true,
        render: (_, record) => (
          <span style={{ fontFamily: 'monospace', fontSize: 12 }}>{`${record.resource_type || '--'} / ${record.resource_id || '--'}`}</span>
        ),
      },
      {
        title: '结果',
        dataIndex: 'result',
        width: 110,
        render: (value: string) => (
          <Tag color={value === 'SUCCEEDED' ? 'blue' : 'red'}>{value || 'UNKNOWN'}</Tag>
        ),
      },
      {
        title: '高价值',
        dataIndex: 'is_high_value',
        width: 88,
        render: (value: boolean) => (value ? <Tag color="gold">是</Tag> : <Tag>否</Tag>),
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
            style={{ paddingInline: 0, height: 'auto' }}
            icon={<CopyOutlined />}
            onClick={(event) => {
              event.stopPropagation();
              void copyText('request_id', value);
            }}
          >
            <span style={{ fontFamily: 'monospace', fontSize: 12 }}>{value || '--'}</span>
          </Button>
        ),
      },
      {
        title: '错误码',
        dataIndex: 'error_code',
        width: 120,
        render: (value: string | null) => <span style={{ fontFamily: 'monospace', fontSize: 12 }}>{value || '--'}</span>,
      },
      {
        title: '操作',
        width: 92,
        fixed: 'right',
        render: (_, record) => (
          <Button
            type="link"
            danger
            icon={<DeleteOutlined />}
            onClick={(event) => {
              event.stopPropagation();
              handleDeleteLog(record);
            }}
          >
            删除
          </Button>
        ),
      },
    ],
    [handleDeleteLog]
  );

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
      await loadAuditLogs(auditPage, auditPageSize);
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
    taskQuery,
  ]);

  const taskLogItems = useMemo(() => {
    if (!taskPayload) {
      return [];
    }

    return taskPayload.items.map((entry) => ({
      key: entry.stage,
      label: (
        <div style={{ display: 'inline-flex', alignItems: 'center', gap: 8, fontSize: 13 }}>
          <span style={{ fontFamily: 'monospace', fontSize: 12 }}>{entry.stage}</span>
          <span>{entry.line_count} 行</span>
          {entry.truncated ? <Tag color="gold">已截断</Tag> : null}
        </div>
      ),
      children: (
        <div style={{ display: 'grid', gap: 8 }}>
          <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
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
            <Alert type="info" showIcon title="当前阶段暂无日志输出。" />
          ) : (
            <div 
              style={{
                border: '1px solid #d9d9d9',
                borderRadius: 6,
                background: '#f8fafc',
                maxHeight: 420,
                overflow: 'auto',
                padding: 12
              }} 
              role="log" 
              aria-live="polite"
            >
              {entry.lines.map((line, index) => (
                <p 
                  key={`${entry.stage}-${index}`} 
                  style={{
                    margin: 0,
                    padding: '4px 0',
                    borderBottom: '1px solid #f0f0f0',
                    display: 'grid',
                    gridTemplateColumns: '48px 1fr',
                    gap: 8,
                    fontSize: 13,
                    lineHeight: 1.5,
                  }}
                >
                  <span style={{ color: '#999', fontFamily: 'monospace', textAlign: 'right', userSelect: 'none' }}>{index + 1}</span>
                  <span style={{ color: '#333', fontFamily: 'monospace', whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>{line}</span>
                </p>
              ))}
            </div>
          )}
        </div>
      ),
    }));
  }, [taskPayload]);

  return (
    <div style={{ padding: '24px', background: '#fff', minHeight: '100%' }}>
      <div style={{ marginBottom: 24, display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 16 }}>
        <h2 style={{ margin: 0 }}>日志中心</h2>
        
        <Space size={16} wrap>
          <Space size={8}>
            <Text type="secondary" style={{ fontSize: 13 }}>自动刷新</Text>
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
          </Space>
          
          <Text type="secondary" style={{ fontSize: 12 }}>上次刷新: {lastRefreshTime || '--'}</Text>
          
          <Button
            type="default"
            icon={<ReloadOutlined />}
            onClick={() => {
              void runAutoRefresh();
            }}
          >
            立即刷新
          </Button>
        </Space>
      </div>

      <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
        <Col xs={24} sm={12} md={6}>
          <Card size="small" bordered>
            <Statistic title="当前视图日志数" value={activeTotal} valueStyle={{ fontSize: 20 }} />
          </Card>
        </Col>
        <Col xs={24} sm={12} md={6}>
          <Card size="small" bordered>
            <Statistic title="操作失败（当前页）" value={auditFailedCount} valueStyle={{ fontSize: 20 }} />
          </Card>
        </Col>
        <Col xs={24} sm={12} md={6}>
          <Card size="small" bordered>
            <Statistic title="高价值操作（当前页）" value={auditHighValueCount} valueStyle={{ fontSize: 20 }} />
          </Card>
        </Col>
        <Col xs={24} sm={12} md={6}>
          <Card size="small" bordered>
            <Statistic title="关联命中数" value={correlationHitCount} valueStyle={{ fontSize: 20 }} />
          </Card>
        </Col>
      </Row>

      <Tabs
        activeKey={activeTab}
        onChange={(key) => setActiveTab(key as LogCenterTabKey)}
        items={[
          {
            key: 'system',
            label: '系统日志（操作）',
            children: (
              <div style={{ display: 'grid', gap: 16 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <Text type="secondary" style={{ fontSize: 13 }}>
                    默认展示操作日志，可按动作、结果和时间范围筛选。
                  </Text>
                  <Space>
                    <Button
                      danger
                      icon={<DeleteOutlined />}
                      onClick={handleBatchDelete}
                    >
                      批量删除当前筛选
                    </Button>
                    <Button
                      icon={<ReloadOutlined />}
                      onClick={() => {
                        void runAutoRefresh();
                      }}
                    >
                      刷新
                    </Button>
                  </Space>
                </div>

                <Form
                  form={auditForm}
                  layout="inline"
                  onFinish={() => {
                    void loadAuditLogs(1, auditPageSize);
                  }}
                >
                  <Space wrap style={{ width: '100%' }}>
                    <Form.Item name="request_id" style={{ margin: 0 }}>
                      <Input allowClear placeholder="请求 ID" style={{ width: 180 }} />
                    </Form.Item>
                    <Form.Item name="project_id" style={{ margin: 0 }}>
                      <Input allowClear placeholder="项目 ID" style={{ width: 150 }} />
                    </Form.Item>
                    <Form.Item name="action" style={{ margin: 0 }}>
                      <Input allowClear placeholder="动作编码" style={{ width: 150 }} />
                    </Form.Item>
                    <Form.Item name="action_group" style={{ margin: 0 }}>
                      <Select
                        allowClear
                        placeholder="动作分组"
                        style={{ width: 160 }}
                        options={actionGroupOptions}
                      />
                    </Form.Item>
                    <Form.Item name="result" style={{ margin: 0 }}>
                      <Select allowClear placeholder="操作结果" style={{ width: 130 }} options={resultOptions} />
                    </Form.Item>
                    <Form.Item name="keyword" style={{ margin: 0 }}>
                      <Input allowClear placeholder="关键词" style={{ width: 160 }} />
                    </Form.Item>
                    <Form.Item name="high_value_only" style={{ margin: 0 }} valuePropName="checked">
                      <Switch checkedChildren="高价值" unCheckedChildren="全部" />
                    </Form.Item>
                    <Form.Item name="range" style={{ margin: 0 }}>
                      <RangePicker showTime style={{ width: 300 }} />
                    </Form.Item>
                    <Form.Item style={{ margin: 0 }}>
                      <Button type="primary" htmlType="submit" icon={<SearchOutlined />}>
                        查询
                      </Button>
                    </Form.Item>
                  </Space>
                </Form>

                <Table<AuditLogItem>
                  rowKey="id"
                  loading={systemLoading}
                  columns={auditColumns}
                  dataSource={auditItems}
                  scroll={{ x: 1360 }}
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
                    style: { cursor: 'pointer' },
                    onClick: () => {
                      setLogDetail({ kind: 'audit', record });
                    },
                  })}
                />
              </div>
            ),
          },
          {
            key: 'task',
            label: '任务日志',
            children: (
              <div style={{ display: 'grid', gap: 16 }}>
                <Form
                  form={taskForm}
                  layout="inline"
                  onFinish={(values) => {
                    void handleTaskSearch(values);
                  }}
                >
                  <Space wrap style={{ width: '100%' }}>
                    <Form.Item name="task_type" rules={[{ required: true, message: '请选择任务类型' }]} style={{ margin: 0 }}>
                      <Segmented options={taskTypeOptions} />
                    </Form.Item>
                    <Form.Item name="task_id" rules={[{ required: true, message: '请输入任务 ID' }]} style={{ margin: 0 }}>
                      <Input allowClear placeholder="task_id (UUID)" style={{ width: 300 }} />
                    </Form.Item>
                    <Form.Item name="stage" style={{ margin: 0 }}>
                      <Input allowClear placeholder="stage (可选)" style={{ width: 150 }} />
                    </Form.Item>
                    <Form.Item name="tail" rules={[{ required: true, message: '请输入 tail 行数' }]} style={{ margin: 0 }}>
                      <InputNumber min={1} max={5000} style={{ width: 100 }} />
                    </Form.Item>
                    <Form.Item style={{ margin: 0 }}>
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
                  </Space>
                </Form>

                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '12px', background: '#f5f5f5', borderRadius: 6 }}>
                  <Statistic title="阶段数量" value={taskStageCount} />
                  <Text type="secondary" style={{ fontSize: 13 }}>
                    当前按任务类型 + 任务 ID 聚合日志，可按 stage 精确定位问题阶段。
                  </Text>
                </div>

                {taskPayload ? (
                  <Collapse items={taskLogItems} style={{ background: '#fff' }} />
                ) : (
                  <Alert type="info" showIcon title="请先输入任务条件并点击查询。" />
                )}
              </div>
            ),
          },
          {
            key: 'correlation',
            label: '关联追踪',
            children: (
              <div style={{ display: 'grid', gap: 16 }}>
                <Form
                  form={correlationForm}
                  layout="inline"
                  onFinish={(values) => {
                    void handleCorrelationSearch(values);
                  }}
                >
                  <Space wrap style={{ width: '100%' }}>
                    <Form.Item name="request_id" style={{ margin: 0 }}>
                      <Input allowClear placeholder="request_id" style={{ width: 180 }} />
                    </Form.Item>
                    <Form.Item name="task_type" style={{ margin: 0 }}>
                      <Segmented options={taskTypeOptions} />
                    </Form.Item>
                    <Form.Item name="task_id" style={{ margin: 0 }}>
                      <Input allowClear placeholder="task_id" style={{ width: 300 }} />
                    </Form.Item>
                    <Form.Item name="project_id" style={{ margin: 0 }}>
                      <Input allowClear placeholder="project_id" style={{ width: 150 }} />
                    </Form.Item>
                    <Form.Item name="limit" style={{ margin: 0 }}>
                      <InputNumber min={1} max={500} style={{ width: 100 }} />
                    </Form.Item>
                    <Form.Item name="range" style={{ margin: 0 }}>
                      <RangePicker showTime style={{ width: 300 }} />
                    </Form.Item>
                    <Form.Item style={{ margin: 0 }}>
                      <Button type="primary" htmlType="submit" icon={<LinkOutlined />} loading={correlationLoading}>
                        追踪
                      </Button>
                    </Form.Item>
                  </Space>
                </Form>

                {correlationPayload ? (
                  <div style={{ display: 'grid', gap: 16 }}>
                    <Card title={`操作日志 (${correlationPayload.audit_logs.length})`} size="small">
                      <Table
                        rowKey="id"
                        size="middle"
                        pagination={false}
                        dataSource={correlationPayload.audit_logs}
                        columns={[
                          {
                            title: '时间',
                            dataIndex: 'created_at',
                            width: 170,
                            render: (value: string) => <span style={{ fontFamily: 'monospace', fontSize: 12 }}>{formatTime(value)}</span>,
                          },
                          {
                            title: '动作',
                            dataIndex: 'action_zh',
                            ellipsis: true,
                            render: (_: string, record: AuditLogItem) => (
                              <div style={{ display: 'grid', gap: 2 }}>
                                <span>{record.action_zh || record.action || '--'}</span>
                                <span style={{ fontFamily: 'monospace', fontSize: 12, color: '#999' }}>{record.action || '--'}</span>
                              </div>
                            ),
                          },
                          {
                            title: '摘要',
                            dataIndex: 'summary_zh',
                            ellipsis: true,
                            render: (value: string) => value || '--',
                          },
                          {
                            title: 'request_id',
                            dataIndex: 'request_id',
                            width: 220,
                            ellipsis: true,
                            render: (value: string) => <span style={{ fontFamily: 'monospace', fontSize: 12 }}>{value || '--'}</span>,
                          },
                        ]}
                      />
                    </Card>

                    <Card
                      title={`任务日志元数据 (${correlationPayload.task_log_previews.length})`}
                      size="small"
                    >
                      <Table
                        rowKey={(item) => `${item.task_type}-${item.task_id}-${item.stage}`}
                        size="middle"
                        pagination={false}
                        dataSource={correlationPayload.task_log_previews}
                        columns={[
                          {
                            title: 'task',
                            width: 260,
                            render: (_, item) => (
                              <span style={{ fontFamily: 'monospace', fontSize: 12 }}>{`${item.task_type} / ${item.task_id}`}</span>
                            ),
                          },
                          {
                            title: 'stage',
                            dataIndex: 'stage',
                            width: 120,
                            render: (value: string) => <span style={{ fontFamily: 'monospace', fontSize: 12 }}>{value}</span>,
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
                            render: (value: string) => <span style={{ fontFamily: 'monospace', fontSize: 12 }}>{formatTime(value)}</span>,
                          },
                        ]}
                      />
                    </Card>
                  </div>
                ) : (
                  <Alert type="info" showIcon title="请输入关联条件后点击追踪。" />
                )}
              </div>
            ),
          },
        ]}
      />

      <Drawer
        open={Boolean(logDetail)}
        width={540}
        onClose={() => setLogDetail(null)}
        title="操作日志详情"
        extra={
          logDetail ? (
            <Button
              danger
              size="small"
              icon={<DeleteOutlined />}
              onClick={() => {
                handleDeleteLog(logDetail.record);
              }}
            >
              删除日志
            </Button>
          ) : null
        }
      >
        {logDetail ? (
          <Space direction="vertical" size={16} style={{ width: '100%' }}>
            <Descriptions column={1} size="small" bordered>
              <>
                <Descriptions.Item label="时间">{formatTime(logDetail.record.created_at)}</Descriptions.Item>
                <Descriptions.Item label="动作中文">{logDetail.record.action_zh || '--'}</Descriptions.Item>
                <Descriptions.Item label="动作编码">
                  <span style={{ fontFamily: 'monospace', fontSize: 12 }}>{logDetail.record.action || '--'}</span>
                </Descriptions.Item>
                <Descriptions.Item label="摘要">{logDetail.record.summary_zh || '--'}</Descriptions.Item>
                <Descriptions.Item label="动作分组">{logDetail.record.action_group || '--'}</Descriptions.Item>
                <Descriptions.Item label="资源">
                  <span style={{ fontFamily: 'monospace', fontSize: 12 }}>{`${logDetail.record.resource_type} / ${logDetail.record.resource_id}`}</span>
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
                    <span style={{ fontFamily: 'monospace', fontSize: 12 }}>{logDetail.record.request_id}</span>
                  </Button>
                </Descriptions.Item>
                <Descriptions.Item label="结果">{logDetail.record.result || '--'}</Descriptions.Item>
                <Descriptions.Item label="高价值">{logDetail.record.is_high_value ? '是' : '否'}</Descriptions.Item>
              </>
            </Descriptions>

            <div>
              <p style={{ margin: '0 0 8px', color: '#999', fontSize: 13, fontWeight: 600 }}>detail_json</p>
              <pre style={{
                margin: 0,
                border: '1px solid #d9d9d9',
                borderRadius: 6,
                padding: 12,
                background: '#f5f5f5',
                color: '#333',
                fontSize: 13,
                lineHeight: 1.55,
                fontFamily: 'monospace',
                overflow: 'auto',
                maxHeight: 340
              }}>{formatJson(logDetail.record.detail_json)}</pre>
            </div>
          </Space>
        ) : null}
      </Drawer>
    </div>
  );
};

export default LogCenterPage;
