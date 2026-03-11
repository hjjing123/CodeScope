import React from 'react';
import { Table, Tag, Badge, Button, Tooltip, Typography } from 'antd';
import { EyeOutlined } from '@ant-design/icons';
import type { TablePaginationConfig } from 'antd/es/table';
import type { FilterValue, SorterResult } from 'antd/es/table/interface';
import type { Finding } from '../../types/finding';

const { Text } = Typography;

interface FindingListTableProps {
  loading: boolean;
  data: Finding[];
  total: number;
  currentPage: number;
  pageSize: number;
  onChange: (
    pagination: TablePaginationConfig,
    filters: Record<string, FilterValue | null>,
    sorter: SorterResult<Finding> | SorterResult<Finding>[]
  ) => void;
  onViewDetail: (record: Finding) => void;
}

const severityColorMap: Record<string, string> = {
  HIGH: 'red',
  MED: 'orange',
  LOW: 'blue',
  INFO: 'default',
};

const statusStatusMap: Record<string, "success" | "processing" | "error" | "default" | "warning"> = {
  new: 'processing',
  confirmed: 'error',
  false_positive: 'success', // Green for handled
  wont_fix: 'warning',
  fixed: 'success',
};

const formatLocation = (filePath?: string | null, line?: number | null) => {
  if (!filePath) {
    return '-';
  }
  return typeof line === 'number' && line > 0 ? `${filePath}:${line}` : filePath;
};

const FindingListTable: React.FC<FindingListTableProps> = ({
  loading,
  data,
  total,
  currentPage,
  pageSize,
  onChange,
  onViewDetail,
}) => {
  const columns = [
    {
      title: 'Severity',
      dataIndex: 'severity',
      key: 'severity',
      width: 100,
      render: (severity: string) => (
        <Tag color={severityColorMap[severity] || 'default'}>{severity}</Tag>
      ),
    },
    {
      title: 'Rule Key',
      dataIndex: 'rule_key',
      key: 'rule_key',
      render: (text: string) => <Text copyable>{text}</Text>,
    },
    {
      title: 'File Path',
      dataIndex: 'file_path',
      key: 'file_path',
      render: (text: string, record: Finding) => (
        <Tooltip title={formatLocation(text, record.line_start)}>
          <Text style={{ maxWidth: 300 }} ellipsis>
            {formatLocation(text, record.line_start)}
          </Text>
        </Tooltip>
      ),
    },
    {
      title: 'Status',
      dataIndex: 'status',
      key: 'status',
      width: 120,
      render: (status: string) => (
        <Badge
          status={statusStatusMap[status] || 'default'}
          text={status.replace('_', ' ').toUpperCase()}
        />
      ),
    },
    {
      title: 'Action',
      key: 'action',
      width: 100,
      render: (_: any, record: Finding) => (
        <Button
          type="link"
          icon={<EyeOutlined />}
          onClick={(e) => {
            e.stopPropagation();
            onViewDetail(record);
          }}
        >
          Detail
        </Button>
      ),
    },
  ];

  return (
    <Table
      rowKey="id"
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
        onClick: () => onViewDetail(record),
        style: { cursor: 'pointer' },
      })}
      size="middle"
    />
  );
};

export default FindingListTable;
