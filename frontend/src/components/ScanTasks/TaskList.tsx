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
      PENDING: 'Pending',
      QUEUED: 'Queued',
      RUNNING: 'Running',
      PROCESSING: 'Processing',
      SUCCEEDED: 'Success',
      FAILED: 'Failed',
      CANCELED: 'Canceled',
      TIMEOUT: 'Timed Out',
    };
    return textMap[status] || status;
  };

  const columns = [
    {
      title: 'ID',
      dataIndex: 'id',
      key: 'id',
      width: 100,
      render: (id: string) => (
        <Tooltip title={id}>
          <Text code copyable>{id.substring(0, 8)}</Text>
        </Tooltip>
      ),
    },
    {
      title: 'Project',
      key: 'project',
      render: (_: unknown, record: Job) => {
        // Try to access project name if available, otherwise show ID
        const projectName = (record as any).project_name || record.project_id;
        return (
            <Tooltip title={record.project_id}>
                <Text>{projectName}</Text>
            </Tooltip>
        );
      },
    },
    {
      title: 'Version',
      key: 'version',
      render: (_: unknown, record: Job) => {
        // Try to access version name if available, otherwise show ID
        const versionName = (record as any).version_name || record.version_id;
        return (
            <Tooltip title={record.version_id}>
                <Text>{versionName}</Text>
            </Tooltip>
        );
      },
    },
    {
      title: 'Status',
      dataIndex: 'status',
      key: 'status',
      width: 120,
      render: (status: string) => (
        <Badge status={getStatusBadge(status)} text={getStatusText(status)} />
      ),
    },
    {
      title: 'Progress',
      key: 'progress',
      width: 200,
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
        />
      ),
    },
    {
      title: 'Created At',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 180,
      render: (date: string) => (
        <Text code>{dayjs(date).format('YYYY-MM-DD HH:mm:ss')}</Text>
      ),
    },
    {
      title: 'Actions',
      key: 'actions',
      width: 320,
      render: (_: unknown, record: Job) => {
        const isCanceling = loadingAction?.jobId === record.id && loadingAction.action === 'cancel';
        const isRetrying = loadingAction?.jobId === record.id && loadingAction.action === 'retry';
        const isDeleting = loadingAction?.jobId === record.id && loadingAction.action === 'delete';
        const canCancel = CANCELABLE_STATUSES.has(record.status);
        const canRetry = RETRYABLE_STATUSES.has(record.status);
        const canDelete = DELETABLE_STATUSES.has(record.status);

        return (
          <Space size={4} wrap>
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
      pagination={{
        current: page,
        pageSize: pageSize,
        total: total,
        onChange: onPageChange,
        showSizeChanger: true,
      }}
    />
  );
};

export default TaskList;
