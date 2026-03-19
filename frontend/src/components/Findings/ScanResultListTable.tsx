import React from 'react';
import { Table, Tag, Button, Tooltip, Typography, Space, Badge } from 'antd';
import { EyeOutlined } from '@ant-design/icons';
import type { TablePaginationConfig } from 'antd/es/table';
import type { ScanResultRow } from '../../types/finding';
import dayjs from 'dayjs';

const { Text } = Typography;

interface ScanResultListTableProps {
  loading: boolean;
  data: ScanResultRow[];
  total: number;
  currentPage: number;
  pageSize: number;
  onChange: (
    pagination: TablePaginationConfig,
  ) => void;
  onViewDetails: (scanJobId: string) => void;
}

const ScanResultListTable: React.FC<ScanResultListTableProps> = ({
  loading,
  data,
  total,
  currentPage,
  pageSize,
  onChange,
  onViewDetails,
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
      title: 'Project / Version',
      key: 'project_version',
      render: (_: unknown, record: ScanResultRow) => (
        <Space direction="vertical" size={0}>
          <Text strong>{record.project_name}</Text>
          <Text type="secondary" style={{ fontSize: '12px' }}>{record.version_name}</Text>
        </Space>
      ),
    },
    {
      title: 'Status',
      dataIndex: 'job_status',
      key: 'job_status',
      width: 140,
      render: (status: string) => (
        <Badge status={getStatusBadge(status)} text={getStatusText(status)} />
      ),
    },
    {
      title: 'Total Findings',
      dataIndex: 'total_findings',
      key: 'total_findings',
      width: 120,
      render: (count: number) => <Text strong>{count}</Text>,
    },
    {
      title: 'Severity Distribution',
      key: 'severity',
      width: 280,
      render: (_: unknown, record: ScanResultRow) => {
        const { HIGH = 0, MED = 0, LOW = 0 } = record.severity_dist;
        return (
          <Space>
            <Tooltip title="High Severity">
              <Tag color="red" style={{ minWidth: 40, textAlign: 'center' }}>H: {HIGH}</Tag>
            </Tooltip>
            <Tooltip title="Medium Severity">
              <Tag color="orange" style={{ minWidth: 40, textAlign: 'center' }}>M: {MED}</Tag>
            </Tooltip>
            <Tooltip title="Low Severity">
              <Tag color="blue" style={{ minWidth: 40, textAlign: 'center' }}>L: {LOW}</Tag>
            </Tooltip>
          </Space>
        );
      },
    },
    {
      title: 'Scan Time',
      key: 'time',
      width: 200,
      render: (_: unknown, record: ScanResultRow) => {
          const time = record.finished_at || record.result_generated_at || record.created_at;
          return (
            <Space direction="vertical" size={0}>
                <Text>{dayjs(time).format('YYYY-MM-DD HH:mm:ss')}</Text>
                <Text type="secondary" style={{ fontSize: '12px' }}>
                    {record.finished_at ? 'Finished' : 'Created'}
                </Text>
            </Space>
          );
      },
    },
    {
      title: 'Action',
      key: 'action',
      width: 120,
      render: (_: unknown, record: ScanResultRow) => (
        <Button
          type="link"
          icon={<EyeOutlined />}
          onClick={(e) => {
            e.stopPropagation();
            onViewDetails(record.scan_job_id);
          }}
        >
          View
        </Button>
      ),
    },
  ];

  return (
    <Table
      rowKey="scan_job_id"
      columns={columns}
      dataSource={data}
      loading={loading}
      pagination={{
        current: currentPage,
        pageSize: pageSize,
        total: total,
        showSizeChanger: true,
        showQuickJumper: true,
      }}
      onChange={onChange}
      onRow={(record) => ({
        onClick: () => onViewDetails(record.scan_job_id),
        style: { cursor: 'pointer' },
      })}
      size="middle"
    />
  );
};

export default ScanResultListTable;
