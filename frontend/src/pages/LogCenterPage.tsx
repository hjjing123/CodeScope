import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
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
  Empty,
  Form,
  Input,
  InputNumber,
  Modal,
  Row,
  Segmented,
  Select,
  Space,
  Statistic,
  Table,
  Tabs,
  Tag,
  Typography,
  message,
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useSearchParams } from 'react-router-dom';
import {
  DeleteOutlined,
  DownloadOutlined,
  ReloadOutlined,
  SearchOutlined,
} from '@ant-design/icons';
import {
  batchDeleteLogs,
  deleteSingleLog,
  downloadTaskLogs,
  getAuditLogs,
  getTaskLogs,
} from '../services/logCenter';
import { ScanService } from '../services/scan';
import { useAuthStore } from '../store/useAuthStore';
import { logCenterActionGroupOptions } from './logCenterOptions';
import type {
  AuditLogItem,
  AuditLogQuery,
  TaskLogPayload,
  TaskType,
} from '../types/logCenter';
import type { Job } from '../types/scan';

const { RangePicker } = DatePicker;
const { Text } = Typography;

type LogCenterTabKey = 'system' | 'task';

interface AuditFilterValues {
  action_group?: string;
  result?: string;
  keyword?: string;
  range?: [Dayjs, Dayjs];
}

interface TaskFilterValues {
  task_type: TaskType;
  task_id: string;
  stage?: string;
  tail: number;
}

type LogDetailState = { kind: 'audit'; record: AuditLogItem } | null;

const DEFAULT_PAGE_SIZE = 20;
const DEFAULT_TASK_TYPE: TaskType = 'SCAN';
const DEFAULT_TASK_TAIL = 200;
const MAX_TASK_TAIL = 5000;
const DEFAULT_TASK_FORM_VALUES: TaskFilterValues = {
  task_type: DEFAULT_TASK_TYPE,
  task_id: '',
  stage: undefined,
  tail: DEFAULT_TASK_TAIL,
};

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

const parseTaskTail = (rawValue: string | null): number => {
  const parsed = Number(rawValue);
  if (!Number.isFinite(parsed) || parsed < 1) {
    return DEFAULT_TASK_TAIL;
  }
  return Math.min(parsed, MAX_TASK_TAIL);
};

const resolveTabKey = (rawValue: string | null): LogCenterTabKey =>
  rawValue === 'task' ? 'task' : 'system';

const resolveTaskType = (rawValue: string | null): TaskType => {
  const normalized = (rawValue ?? '').trim().toUpperCase() as TaskType;
  return ['SCAN', 'IMPORT', 'SELFTEST'].includes(normalized) ? normalized : DEFAULT_TASK_TYPE;
};

const taskTypeOptions: { label: string; value: TaskType }[] = [
  { label: '扫描任务', value: 'SCAN' },
  { label: '导入任务', value: 'IMPORT' },
  { label: '规则自测', value: 'SELFTEST' },
];

const buildLogCenterSearchParams = (
  tab: LogCenterTabKey,
  taskQuery: { taskType: TaskType; taskId: string; stage?: string; tail: number } | null
): URLSearchParams => {
  const params = new URLSearchParams();
  params.set('tab', tab);
  if (!taskQuery) {
    return params;
  }

  params.set('task_type', taskQuery.taskType);
  params.set('task_id', taskQuery.taskId);
  params.set('tail', String(taskQuery.tail));
  if (taskQuery.stage) {
    params.set('stage', taskQuery.stage);
  }
  return params;
};

const resultOptions = [
  { label: '成功', value: 'SUCCEEDED' },
  { label: '失败', value: 'FAILED' },
];

const hasBatchDeleteCondition = (values: AuditFilterValues): boolean => {
  return Boolean(
    normalizeText(values.keyword) ||
      normalizeText(values.action_group) ||
      (values.range && values.range.length === 2)
  );
};

const LogCenterPage: React.FC = () => {
  const { user } = useAuthStore();
  const [searchParams, setSearchParams] = useSearchParams();
  const [activeTab, setActiveTab] = useState<LogCenterTabKey>(() =>
    searchParams.get('task_id') ? 'task' : resolveTabKey(searchParams.get('tab'))
  );
  const [auditForm] = Form.useForm<AuditFilterValues>();
  const [taskForm] = Form.useForm<TaskFilterValues>();
  const didHydrateTaskQueryRef = useRef(false);
  const didLoadRecentScansRef = useRef(false);

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
  const [recentScans, setRecentScans] = useState<Job[]>([]);
  const [recentScansLoading, setRecentScansLoading] = useState(false);
  const [recentScansError, setRecentScansError] = useState<string | null>(null);
  const canManageAuditLogs = user?.role === 'Admin';

  const activeTotal = activeTab === 'system' ? auditTotal : taskPayload?.items.length ?? 0;
  const auditFailedCount = auditItems.filter((item) => item.result !== 'SUCCEEDED').length;
  const taskStageCount = taskPayload?.items.length ?? 0;
  const taskLineCount = taskPayload?.items.reduce((total, item) => total + item.line_count, 0) ?? 0;
  const taskTruncatedCount = taskPayload?.items.filter((item) => item.truncated).length ?? 0;

  const loadAuditLogs = async (page = 1, pageSize = auditPageSize): Promise<void> => {
    const values = auditForm.getFieldsValue();
    const params: AuditLogQuery = {
      action_group: normalizeText(values.action_group),
      result: normalizeText(values.result),
      keyword: normalizeText(values.keyword),
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
    } finally {
      setSystemLoading(false);
    }
  };

  const loadRecentScans = useCallback(async (): Promise<void> => {
    setRecentScansLoading(true);
    setRecentScansError(null);
    try {
      const response = await ScanService.listJobs({ page: 1, page_size: 5 });
      setRecentScans(response.items ?? []);
    } catch {
      setRecentScansError('Failed to load recent scan tasks. You can still search by task ID.');
    } finally {
      setRecentScansLoading(false);
    }
  }, []);

  const executeTaskSearch = useCallback(
    async (
      query: { taskType: TaskType; taskId: string; stage?: string; tail: number },
      options: { syncUrl?: boolean } = {}
    ): Promise<void> => {
      const { syncUrl = true } = options;

      setTaskLoading(true);
      try {
        const response = await getTaskLogs(query.taskType, query.taskId, {
          stage: query.stage,
          tail: query.tail,
        });
        setTaskPayload(response.data);
        setTaskQuery(query);
        if (syncUrl) {
          setSearchParams(buildLogCenterSearchParams('task', query));
        }
      } finally {
        setTaskLoading(false);
      }
    },
    [setSearchParams]
  );

  const resetTaskLogView = useCallback((): void => {
    setTaskPayload(null);
    setTaskQuery(null);
    taskForm.resetFields();
    setSearchParams(buildLogCenterSearchParams('task', null));
  }, [setSearchParams, taskForm]);

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
          keyword: normalizeText(values.keyword),
          action_group: normalizeText(values.action_group),
          ...toRangeParams(values.range),
        });
        message.success(`已删除 ${response.data.deleted_count} 条日志`);
        await loadAuditLogs(auditPage, auditPageSize);
      },
    });
  };

  useEffect(() => {
    void loadAuditLogs(1, DEFAULT_PAGE_SIZE);
  }, []);

  useEffect(() => {
    if (didHydrateTaskQueryRef.current) {
      return;
    }
    didHydrateTaskQueryRef.current = true;

    const taskType = resolveTaskType(searchParams.get('task_type'));
    const taskId = (searchParams.get('task_id') ?? '').trim();
    const stage = normalizeText(searchParams.get('stage') ?? undefined);
    const tail = parseTaskTail(searchParams.get('tail'));
    const nextTab = taskId ? 'task' : resolveTabKey(searchParams.get('tab'));

    setActiveTab(nextTab);
    taskForm.setFieldsValue({
      task_type: taskType,
      task_id: taskId,
      stage,
      tail,
    });

    if (!taskId) {
      return;
    }

    void executeTaskSearch(
      {
        taskType,
        taskId,
        stage,
        tail,
      },
      { syncUrl: false }
    );
  }, [executeTaskSearch, searchParams, taskForm]);

  useEffect(() => {
    if (activeTab !== 'task' || didLoadRecentScansRef.current) {
      return;
    }
    didLoadRecentScansRef.current = true;
    void loadRecentScans();
  }, [activeTab, loadRecentScans]);

  useEffect(() => {
    if (!didHydrateTaskQueryRef.current || activeTab !== 'task') {
      return;
    }
    setSearchParams(buildLogCenterSearchParams('task', taskQuery));
  }, [activeTab, setSearchParams, taskQuery]);

  const auditColumns: ColumnsType<AuditLogItem> = useMemo(
    () => [
      {
        title: '时间',
        dataIndex: 'created_at',
        width: 190,
        render: (value: string) => <span style={{ fontFamily: 'monospace', fontSize: 12 }}>{formatTime(value)}</span>,
      },
      {
        title: '动作',
        dataIndex: 'action_zh',
        width: 260,
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
        width: 260,
        ellipsis: true,
        render: (value: string) => value || '--',
      },
      {
        title: '结果',
        dataIndex: 'result',
        width: 140,
        align: 'center',
        render: (value: string) => (
          <Tag color={value === 'SUCCEEDED' ? 'blue' : 'red'}>{value || 'UNKNOWN'}</Tag>
        ),
      },
      {
        title: '操作',
        width: 130,
        align: 'center',
        fixed: 'right' as const,
        render: (_: unknown, record: AuditLogItem) => (
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
  const visibleAuditColumns = useMemo(
    () =>
      canManageAuditLogs
        ? auditColumns
        : auditColumns.filter((column) => column.fixed !== 'right'),
    [auditColumns, canManageAuditLogs]
  );

  const handleTaskSearch = async (values: TaskFilterValues): Promise<void> => {
    const taskId = values.task_id.trim();
    if (!taskId) {
      message.warning('请填写任务 ID');
      return;
    }

    await executeTaskSearch({
      taskType: values.task_type,
      taskId,
      stage: normalizeText(values.stage),
      tail: values.tail,
    });
  };

  const handleTaskDownload = async (stage?: string): Promise<void> => {
    if (!taskQuery) {
      message.warning('请先查询任务日志');
      return;
    }

    const downloaded = await downloadTaskLogs(taskQuery.taskType, taskQuery.taskId, stage);
    message.success(`已下载 ${downloaded}`);
  };

  const runAutoRefresh = async (): Promise<void> => {
    if (activeTab === 'system') {
      await loadAuditLogs(auditPage, auditPageSize);
      return;
    }

    if (!taskQuery) {
      return;
    }
    await executeTaskSearch(taskQuery, { syncUrl: false });
  };

  const handleSelectRecentScan = (job: Job): void => {
    const nextQuery = {
      taskType: 'SCAN' as TaskType,
      taskId: job.id,
      stage: undefined,
      tail: DEFAULT_TASK_TAIL,
    };
    taskForm.setFieldsValue({
      task_type: nextQuery.taskType,
      task_id: nextQuery.taskId,
      stage: undefined,
      tail: nextQuery.tail,
    });
    void executeTaskSearch(nextQuery);
  };

  const handleTaskFormValuesChange = (changedValues: Partial<TaskFilterValues>): void => {
    if (!Object.prototype.hasOwnProperty.call(changedValues, 'task_id')) {
      return;
    }

    const nextTaskId = typeof changedValues.task_id === 'string' ? changedValues.task_id.trim() : '';
    if (nextTaskId.length > 0 || (!taskPayload && !taskQuery)) {
      return;
    }

    resetTaskLogView();
  };

  const handleTabChange = (key: string): void => {
    const nextTab = key as LogCenterTabKey;
    setActiveTab(nextTab);

    const fallbackTaskId = (searchParams.get('task_id') ?? '').trim();
    const fallbackTaskQuery =
      fallbackTaskId.length > 0
        ? {
            taskType: resolveTaskType(searchParams.get('task_type')),
            taskId: fallbackTaskId,
            stage: normalizeText(searchParams.get('stage') ?? undefined),
            tail: parseTaskTail(searchParams.get('tail')),
          }
        : null;

    setSearchParams(buildLogCenterSearchParams(nextTab, taskQuery ?? fallbackTaskQuery));
  };

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
      <div style={{ marginBottom: 24 }}>
        <h2 style={{ margin: 0 }}>日志中心</h2>
        
      </div>

      <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
        <Col xs={24} sm={12} md={8}>
          <Card size="small" bordered>
            <Statistic
              title={activeTab === 'system' ? '当前视图日志数' : '阶段数量'}
              value={activeTotal}
              valueStyle={{ fontSize: 20 }}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} md={8}>
          <Card size="small" bordered>
            <Statistic
              title={activeTab === 'system' ? '操作失败（当前页）' : '日志总行数'}
              value={activeTab === 'system' ? auditFailedCount : taskLineCount}
              valueStyle={{ fontSize: 20 }}
            />
          </Card>
        </Col>
        {activeTab === 'task' ? (
          <Col xs={24} sm={12} md={8}>
            <Card size="small" bordered>
              <Statistic title="已截断阶段" value={taskTruncatedCount} valueStyle={{ fontSize: 20 }} />
            </Card>
          </Col>
        ) : null}
      </Row>

      <Tabs
        activeKey={activeTab}
        onChange={handleTabChange}
        items={[
          {
            key: 'system',
            label: '系统操作日志',
            children: (
              <div style={{ display: 'grid', gap: 16 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <Text type="secondary" style={{ fontSize: 13 }}>
                    默认展示操作日志，可按动作、结果和时间范围筛选。
                  </Text>
                  <Space>
                    {canManageAuditLogs ? (
                      <Button
                        danger
                        icon={<DeleteOutlined />}
                        onClick={handleBatchDelete}
                      >
                      批量删除当前筛选
                    </Button>
                    ) : null}
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
                    <Form.Item name="action_group" style={{ margin: 0 }}>
                      <Select
                        allowClear
                        placeholder="动作分组"
                        style={{ width: 160 }}
                        options={logCenterActionGroupOptions}
                      />
                    </Form.Item>
                    <Form.Item name="result" style={{ margin: 0 }}>
                      <Select allowClear placeholder="操作结果" style={{ width: 130 }} options={resultOptions} />
                    </Form.Item>
                    <Form.Item name="keyword" style={{ margin: 0 }}>
                      <Input allowClear placeholder="关键词" style={{ width: 160 }} />
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
                  columns={visibleAuditColumns}
                  dataSource={auditItems}
                  tableLayout="fixed"
                  scroll={{ x: 1200 }}
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
                  initialValues={DEFAULT_TASK_FORM_VALUES}
                  onValuesChange={handleTaskFormValuesChange}
                  onFinish={(values) => {
                    void handleTaskSearch(values);
                  }}
                >
                  <Space wrap style={{ width: '100%' }}>
                    <Form.Item name="task_type" rules={[{ required: true, message: '请选择任务类型' }]} style={{ margin: 0 }}>
                      <Segmented options={taskTypeOptions} />
                    </Form.Item>
                    <Form.Item name="task_id" rules={[{ required: true, message: '请输入任务 ID' }]} style={{ margin: 0 }}>
                      <Input
                        allowClear
                        placeholder="task_id (UUID)"
                        style={{ width: 300 }}
                      />
                    </Form.Item>
                    <Form.Item name="stage" style={{ margin: 0 }}>
                      <Input allowClear placeholder="stage (可选)" style={{ width: 150 }} />
                    </Form.Item>
                    <Form.Item name="tail" rules={[{ required: true, message: '请输入 tail 行数' }]} style={{ margin: 0 }}>
                      <InputNumber min={1} max={MAX_TASK_TAIL} style={{ width: 100 }} />
                    </Form.Item>
                    <Form.Item style={{ margin: 0 }}>
                      <Space size={8}>
                        <Button type="primary" htmlType="submit" icon={<SearchOutlined />} loading={taskLoading}>
                          查询
                        </Button>
                        {taskQuery || taskPayload ? (
                          <Button
                            type="default"
                            data-testid="task-log-reset-button"
                            onClick={() => {
                              resetTaskLogView();
                            }}
                          >
                            返回最近任务
                          </Button>
                        ) : null}
                        <Button
                          type="default"
                          icon={<DownloadOutlined />}
                          data-testid="task-log-download-current"
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
                          data-testid="task-log-download-all"
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
                  taskPayload.items.length > 0 ? (
                    <Collapse items={taskLogItems} style={{ background: '#fff' }} />
                  ) : (
                    <Alert type="info" showIcon message="No stage logs found for this task." />
                  )
                                ) : (
                  <Card
                    size="small"
                    title="Recent Scan Tasks"
                    extra={
                      recentScans.length > 0 ? (
                        <Text type="secondary" style={{ fontSize: 12 }}>
                          Pick a recent task to view logs
                        </Text>
                      ) : null
                    }
                  >
                    {recentScansError ? (
                      <Alert type="warning" showIcon message={recentScansError} />
                    ) : recentScansLoading ? (
                      <Card loading size="small" />
                    ) : recentScans.length > 0 ? (
                      <div style={{ display: 'grid', gap: 12 }}>
                        {recentScans.map((job) => (
                          <div
                            key={job.id}
                            style={{
                              display: 'flex',
                              justifyContent: 'space-between',
                              alignItems: 'center',
                              gap: 16,
                              padding: '12px 0',
                              borderBottom: '1px solid #f0f0f0',
                            }}
                          >
                            <div style={{ display: 'grid', gap: 4 }}>
                              <Text strong>{job.project_name || job.project_id}</Text>
                              <Text type="secondary" style={{ fontSize: 12 }}>
                                Task ID: {job.id}
                              </Text>
                              <Text type="secondary" style={{ fontSize: 12 }}>
                                Created At: {formatTime(job.created_at)}
                              </Text>
                            </div>
                            <Button
                              type="link"
                              onClick={() => {
                                handleSelectRecentScan(job);
                              }}
                            >
                              View Logs
                            </Button>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <Empty
                        image={Empty.PRESENTED_IMAGE_SIMPLE}
                        description="No recent scan tasks. Enter a task ID to search."
                      />
                    )}
                  </Card>
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
          logDetail && canManageAuditLogs ? (
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
            <Descriptions column={1} size="small" bordered style={{ display: 'none' }}>
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
                <Descriptions.Item label="结果">{logDetail.record.result || '--'}</Descriptions.Item>
              </>
            </Descriptions>

            <Descriptions column={1} size="small" bordered>
              <>
                <Descriptions.Item label="时间">{formatTime(logDetail.record.created_at)}</Descriptions.Item>
                <Descriptions.Item label="动作中文">{logDetail.record.action_zh || '--'}</Descriptions.Item>
                <Descriptions.Item label="动作编码">
                  <span style={{ fontFamily: 'monospace', fontSize: 12 }}>
                    {logDetail.record.action || '--'}
                  </span>
                </Descriptions.Item>
                <Descriptions.Item label="摘要">{logDetail.record.summary_zh || '--'}</Descriptions.Item>
                <Descriptions.Item label="动作分组">{logDetail.record.action_group || '--'}</Descriptions.Item>
                <Descriptions.Item label="结果">{logDetail.record.result || '--'}</Descriptions.Item>
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
