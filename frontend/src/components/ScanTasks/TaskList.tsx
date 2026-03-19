import React from 'react';
import { Table, Badge, Progress, Button, Popconfirm, Space, Typography, Tooltip } from 'antd';
import { DeleteOutlined, EyeOutlined, RedoOutlined, StopOutlined } from '@ant-design/icons';
import type { Job } from '../../types/scan';
import dayjs from 'dayjs';

const { Text } = Typography;

interface TaskListProps {
  jobs: Job[];
  loading: boolean;
  total: number;
  page: number;
  pageSize: number;
  onPageChange: (page: number, pageSize: number) => void;
  onViewDetails?: (job: Job) => void;
  onCancelJob?: (job: Job) => void;
  onRetryJob?: (job: Job) => void;
  onDeleteJob?: (job: Job) => void;
  loadingAction?: { jobId: string; action: 'cancel' | 'retry' | 'delete' } | null;
}

const CANCELABLE_STATUSES = new Set(['PENDING', 'QUEUED', 'RUNNING', 'PROCESSING']);
const RETRYABLE_STATUSES = new Set(['FAILED', 'CANCELED', 'TIMEOUT']);
const DELETABLE_STATUSES = new Set(['SUCCEEDED', 'FAILED', 'CANCELED', 'TIMEOUT']);

const getProjectDisplayName = (job: Job) => {
  const value = job.project_name?.trim();
  return value && value.length > 0 ? value : '未命名项目';
};

const getVersionDisplayName = (job: Job) => {
  const value = job.version_name?.trim();
  return value && value.length > 0 ? value : '未命名版本';
};

const TaskList: React.FC<TaskListProps> = ({
  jobs,
  loading,
  total,
  page,
  pageSize,
  onPageChange,
  onViewDetails,
  onCancelJob,
  onRetryJob,
  onDeleteJob,
  loadingAction,
}) => {
  const getStatusBadge = (status: string) => {
    const statusMap: Record<string, 'processing' | 'success' | 'error' | 'default' | 'warning'> = {
      PENDING: 'default',
      QUEUED: 'default',
      RUNNING: 'processing',
      PROCESSING: 'processing',
      SUCCEEDED: 'success',
      FAILED: 'error',
      CANCELED: 'warning',
      TIMEOUT: 'error',
    };
    return statusMap[status] || 'default';
  };

  const getStatusText = (status: string) => {
    const textMap: Record<string, string> = {
      PENDING: '等待中',
      QUEUED: '排队中',
      RUNNING: '扫描中',
      PROCESSING: '处理中',
      SUCCEEDED: '扫描完成',
      FAILED: '扫描失败',
      CANCELED: '已取消',
      TIMEOUT: '执行超时',
    };
    return textMap[status] || status;
  };

  const columns = [
    {
      title: '源码 / 版本',
      key: 'source_version',
      render: (_: unknown, record: Job) => {
        const projectName = getProjectDisplayName(record);
        const versionName = getVersionDisplayName(record);
        return (
          <Tooltip
            title={
              <div>
                <div>项目：{projectName}</div>
                <div>版本：{versionName}</div>
                <div>任务 ID：{record.id}</div>
              </div>
            }
          >
            <Space direction="vertical" size={2} style={{ width: '100%', lineHeight: 1.35 }}>
              <Text strong ellipsis={{ tooltip: projectName }} style={{ display: 'block' }}>
                {projectName}
              </Text>
              <Text type="secondary" ellipsis={{ tooltip: versionName }} style={{ display: 'block' }}>
                {versionName}
              </Text>
            </Space>
          </Tooltip>
        );
      },
    },
    {
      title: '扫描状态',
      dataIndex: 'status',
      key: 'status',
      width: 160,
      render: (status: string) => (
        <Badge status={getStatusBadge(status)} text={getStatusText(status)} />
      ),
    },
    {
      title: '扫描进度',
      key: 'progress',
      width: 240,
      render: (_: unknown, record: Job) => (
        <Progress
          percent={record.progress?.percent || 0}
          size="small"
          status={
            record.status === 'FAILED' || record.status === 'TIMEOUT' || record.status === 'CANCELED'
              ? 'exception'
              : record.status === 'SUCCEEDED'
                ? 'success'
                : 'active'
          }
          style={{ width: '90%' }}
        />
      ),
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 180,
      render: (date: string) => (
        <Space direction="vertical" size={0}>
          <Text>{dayjs(date).format('YYYY-MM-DD')}</Text>
          <Text type="secondary">{dayjs(date).format('HH:mm:ss')}</Text>
        </Space>
      ),
    },
    {
      title: '操作',
      key: 'actions',
      width: 240,
      render: (_: unknown, record: Job) => {
        const isCanceling = loadingAction?.jobId === record.id && loadingAction.action === 'cancel';
        const isRetrying = loadingAction?.jobId === record.id && loadingAction.action === 'retry';
        const isDeleting = loadingAction?.jobId === record.id && loadingAction.action === 'delete';
        const canCancel = CANCELABLE_STATUSES.has(record.status);
        const canRetry = RETRYABLE_STATUSES.has(record.status);
        const canDelete = DELETABLE_STATUSES.has(record.status);

        return (
          <Space size={0} wrap>
            <Button
              type="link"
              size="small"
              icon={<EyeOutlined />}
              onClick={() => onViewDetails && onViewDetails(record)}
            >
              详情
            </Button>

            {canCancel ? (
              <Popconfirm
                title="确认取消该扫描任务？"
                okText="确认取消"
                cancelText="取消"
                onConfirm={() => onCancelJob && onCancelJob(record)}
              >
                <Button
                  type="link"
                  size="small"
                  danger
                  icon={<StopOutlined />}
                  loading={isCanceling}
                >
                  取消
                </Button>
              </Popconfirm>
            ) : null}

            {canRetry ? (
              <Popconfirm
                title="确认重新执行该扫描任务？"
                okText="确认重启"
                cancelText="取消"
                onConfirm={() => onRetryJob && onRetryJob(record)}
              >
                <Button
                  type="link"
                  size="small"
                  icon={<RedoOutlined />}
                  loading={isRetrying}
                >
                  重启
                </Button>
              </Popconfirm>
            ) : null}

            {canDelete ? (
              <Button
                type="link"
                size="small"
                danger
                icon={<DeleteOutlined />}
                loading={isDeleting}
                onClick={() => onDeleteJob && onDeleteJob(record)}
              >
                删除
              </Button>
            ) : null}
          </Space>
        );
      },
    },
  ];

  return (
    <Table
      columns={columns}
      dataSource={jobs}
      rowKey="id"
      loading={loading}
      size="middle"
      pagination={{
        current: page,
        pageSize: pageSize,
        total: total,
        onChange: onPageChange,
        showSizeChanger: true,
      }}
      scroll={{ x: 980 }}
    />
  );
};

export default TaskList;
