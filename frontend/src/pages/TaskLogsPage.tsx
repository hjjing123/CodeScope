import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import dayjs from 'dayjs';
import {
  Alert,
  Button,
  Card,
  Collapse,
  Col,
  Form,
  Input,
  InputNumber,
  Row,
  Segmented,
  Space,
  Statistic,
  Tag,
  Typography,
  message,
} from 'antd';
import { DownloadOutlined, ReloadOutlined, SearchOutlined } from '@ant-design/icons';
import { useSearchParams } from 'react-router-dom';
import { downloadTaskLogs, getTaskLogs } from '../services/logCenter';
import { useAuthStore } from '../store/useAuthStore';
import type { TaskLogPayload, TaskType } from '../types/logCenter';

const { Text } = Typography;

interface TaskFilterValues {
  task_type: TaskType;
  task_id: string;
  stage?: string;
  tail: number;
}

type TaskQueryState = {
  taskType: TaskType;
  taskId: string;
  stage?: string;
  tail: number;
} | null;

const DEFAULT_TAIL = 200;
const MAX_TAIL = 5000;

const ALL_TASK_TYPE_OPTIONS: Array<{ label: string; value: TaskType }> = [
  { label: '扫描任务', value: 'SCAN' },
  { label: '导入任务', value: 'IMPORT' },
  { label: '规则自测', value: 'SELFTEST' },
];

const statisticContentStyle = { fontSize: 20 };

const normalizeText = (value: string | undefined): string | undefined => {
  const next = (value ?? '').trim();
  return next.length > 0 ? next : undefined;
};

const parseTail = (rawValue: string | null): number => {
  const parsed = Number(rawValue);
  if (!Number.isFinite(parsed) || parsed < 1) {
    return DEFAULT_TAIL;
  }
  return Math.min(parsed, MAX_TAIL);
};

const buildSearchParams = (query: TaskQueryState): URLSearchParams => {
  const params = new URLSearchParams();
  if (!query) {
    return params;
  }
  params.set('task_type', query.taskType);
  params.set('task_id', query.taskId);
  params.set('tail', String(query.tail));
  if (query.stage) {
    params.set('stage', query.stage);
  }
  return params;
};

const TaskLogsPage: React.FC = () => {
  const { user } = useAuthStore();
  const [searchParams, setSearchParams] = useSearchParams();
  const [taskForm] = Form.useForm<TaskFilterValues>();
  const [taskLoading, setTaskLoading] = useState(false);
  const [taskPayload, setTaskPayload] = useState<TaskLogPayload | null>(null);
  const [taskQuery, setTaskQuery] = useState<TaskQueryState>(null);
  const [lastRefreshTime, setLastRefreshTime] = useState('');
  const didHydrateQueryRef = useRef(false);

  const isAdmin = user?.role === 'Admin';
  const allowedTaskTypes = useMemo<TaskType[]>(
    () => (isAdmin ? ['SCAN', 'IMPORT', 'SELFTEST'] : ['SCAN', 'IMPORT']),
    [isAdmin]
  );

  const taskTypeOptions = useMemo(
    () => ALL_TASK_TYPE_OPTIONS.filter((option) => allowedTaskTypes.includes(option.value)),
    [allowedTaskTypes]
  );

  const defaultTaskType = taskTypeOptions[0]?.value ?? 'SCAN';
  const taskStageCount = taskPayload?.items.length ?? 0;
  const taskLineCount =
    taskPayload?.items.reduce((total, item) => total + item.line_count, 0) ?? 0;
  const taskTruncatedCount =
    taskPayload?.items.filter((item) => item.truncated).length ?? 0;

  const resolveTaskType = useCallback(
    (rawValue: string | null): TaskType => {
      const normalized = (rawValue ?? '').trim().toUpperCase() as TaskType;
      return allowedTaskTypes.includes(normalized) ? normalized : defaultTaskType;
    },
    [allowedTaskTypes, defaultTaskType]
  );

  const markRefreshed = useCallback(() => {
    setLastRefreshTime(dayjs().format('HH:mm:ss'));
  }, []);

  const executeTaskSearch = useCallback(
    async (query: TaskQueryState): Promise<void> => {
      if (!query) {
        return;
      }

      setTaskLoading(true);
      try {
        const response = await getTaskLogs(query.taskType, query.taskId, {
          stage: query.stage,
          tail: query.tail,
        });
        setTaskPayload(response.data);
        setTaskQuery(query);
        markRefreshed();
      } finally {
        setTaskLoading(false);
      }
    },
    [markRefreshed]
  );

  const handleTaskSearch = async (values: TaskFilterValues): Promise<void> => {
    const taskId = values.task_id.trim();
    if (!taskId) {
      message.warning('请填写任务 ID');
      return;
    }

    const nextQuery = {
      taskType: allowedTaskTypes.includes(values.task_type) ? values.task_type : defaultTaskType,
      taskId,
      stage: normalizeText(values.stage),
      tail: values.tail,
    } satisfies NonNullable<TaskQueryState>;

    setSearchParams(buildSearchParams(nextQuery));
    await executeTaskSearch(nextQuery);
  };

  const handleRefresh = async (): Promise<void> => {
    if (!taskQuery) {
      return;
    }
    await executeTaskSearch(taskQuery);
  };

  const handleTaskDownload = useCallback(
    async (stage?: string): Promise<void> => {
      if (!taskQuery) {
        message.warning('请先查询任务日志');
        return;
      }

      const downloaded = await downloadTaskLogs(taskQuery.taskType, taskQuery.taskId, stage);
      message.success(`已下载 ${downloaded}`);
    },
    [taskQuery]
  );

  useEffect(() => {
    if (didHydrateQueryRef.current) {
      return;
    }
    didHydrateQueryRef.current = true;

    const taskType = resolveTaskType(searchParams.get('task_type'));
    const taskId = (searchParams.get('task_id') ?? '').trim();
    const stage = normalizeText(searchParams.get('stage') ?? undefined);
    const tail = parseTail(searchParams.get('tail'));

    taskForm.setFieldsValue({
      task_type: taskType,
      task_id: taskId,
      stage,
      tail,
    });

    if (!taskId) {
      return;
    }

    void executeTaskSearch({
      taskType,
      taskId,
      stage,
      tail,
    });
  }, [executeTaskSearch, resolveTaskType, searchParams, taskForm]);

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
                padding: 12,
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
                  <span
                    style={{
                      color: '#999',
                      fontFamily: 'monospace',
                      textAlign: 'right',
                      userSelect: 'none',
                    }}
                  >
                    {index + 1}
                  </span>
                  <span
                    style={{
                      color: '#333',
                      fontFamily: 'monospace',
                      whiteSpace: 'pre-wrap',
                      wordBreak: 'break-word',
                    }}
                  >
                    {line}
                  </span>
                </p>
              ))}
            </div>
          )}
        </div>
      ),
    }));
  }, [handleTaskDownload, taskPayload]);

  return (
    <div style={{ padding: '24px', background: '#fff', minHeight: '100%' }}>
      <div
        style={{
          marginBottom: 24,
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          flexWrap: 'wrap',
          gap: 16,
        }}
      >
        <div>
          <h2 style={{ margin: 0 }}>任务日志</h2>
          <Text type="secondary" style={{ fontSize: 13 }}>
            按任务类型、任务 ID 与阶段查看任务执行日志。
          </Text>
        </div>

        <Space size={16} wrap>
          <Text type="secondary" style={{ fontSize: 12 }}>
            上次刷新: {lastRefreshTime || '--'}
          </Text>
          <Button
            type="default"
            icon={<ReloadOutlined />}
            onClick={() => {
              void handleRefresh();
            }}
            disabled={!taskQuery}
          >
            刷新
          </Button>
        </Space>
      </div>

      <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
        <Col xs={24} sm={12} md={8}>
          <Card size="small" variant="outlined">
            <Statistic title="阶段数量" value={taskStageCount} styles={{ content: statisticContentStyle }} />
          </Card>
        </Col>
        <Col xs={24} sm={12} md={8}>
          <Card size="small" variant="outlined">
            <Statistic title="日志总行数" value={taskLineCount} styles={{ content: statisticContentStyle }} />
          </Card>
        </Col>
        <Col xs={24} sm={12} md={8}>
          <Card size="small" variant="outlined">
            <Statistic title="已截断阶段" value={taskTruncatedCount} styles={{ content: statisticContentStyle }} />
          </Card>
        </Col>
      </Row>

      <div style={{ display: 'grid', gap: 16 }}>
        <Form
          form={taskForm}
          layout="inline"
          initialValues={{ task_type: defaultTaskType, tail: DEFAULT_TAIL }}
          onFinish={(values) => {
            void handleTaskSearch(values);
          }}
        >
          <Space wrap style={{ width: '100%' }}>
            <Form.Item
              name="task_type"
              rules={[{ required: true, message: '请选择任务类型' }]}
              style={{ margin: 0 }}
            >
              <Segmented options={taskTypeOptions} />
            </Form.Item>
            <Form.Item
              name="task_id"
              rules={[{ required: true, message: '请输入任务 ID' }]}
              style={{ margin: 0 }}
            >
              <Input allowClear placeholder="task_id (UUID)" style={{ width: 300 }} />
            </Form.Item>
            <Form.Item name="stage" style={{ margin: 0 }}>
              <Input allowClear placeholder="stage (可选)" style={{ width: 150 }} />
            </Form.Item>
            <Form.Item
              name="tail"
              rules={[{ required: true, message: '请输入 tail 行数' }]}
              style={{ margin: 0 }}
            >
              <InputNumber min={1} max={MAX_TAIL} style={{ width: 100 }} />
            </Form.Item>
            <Form.Item style={{ margin: 0 }}>
              <Space size={8}>
                <Button
                  type="primary"
                  htmlType="submit"
                  icon={<SearchOutlined />}
                  loading={taskLoading}
                >
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

        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            padding: '12px',
            background: '#f5f5f5',
            borderRadius: 6,
          }}
        >
          <Statistic title="阶段数量" value={taskStageCount} />
          <Text type="secondary" style={{ fontSize: 13 }}>
            当前按任务类型与任务 ID 聚合日志，可按 stage 精确定位问题阶段。
          </Text>
        </div>

        {taskPayload ? (
          <Collapse items={taskLogItems} style={{ background: '#fff' }} />
        ) : (
          <Alert type="info" showIcon title="请输入任务条件并点击查询。" />
        )}
      </div>
    </div>
  );
};

export default TaskLogsPage;
