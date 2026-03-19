import React from 'react';
import { Table, Tag, Badge, Button, Tooltip, Typography } from 'antd';
import { EyeOutlined } from '@ant-design/icons';
import type { TablePaginationConfig } from 'antd/es/table';
import type { FilterValue, SorterResult } from 'antd/es/table/interface';
import type { Finding } from '../../types/finding';
import { formatLocation } from '../../utils/findingLocation';

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
  onOpenAIReview?: (record: Finding) => void;
  openingFindingId?: string | null;
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

const getVulnDisplayName = (record: Finding) => {
  return record.vuln_display_name || record.vuln_type || record.rule_key || '-';
};

const getEntryDisplay = (record: Finding) => {
  // If it's a route, show route info (method + path usually)
  const entryDisplay = record.entry_display;
  if (record.entry_kind === 'route' && entryDisplay) {
    return entryDisplay.replace(/^[A-Z]+\s+/, '');
  }

  // For any file path (Config or Code), only show filename:line
  if (record.file_path) {
    const filename = record.file_path.split(/[/\\]/).pop() || '';
    return typeof record.line_start === 'number' && record.line_start > 0
      ? `${filename}:${record.line_start}`
      : filename;
  }

  // Fallback
  if (record.entry_display) {
    return record.entry_display;
  }
  return '-';
};

const getEntryTooltip = (record: Finding) => {
  const entryDisplay = record.entry_display;
  if (record.entry_kind === 'route' && entryDisplay) {
    return entryDisplay.replace(/^[A-Z]+\s+/, '');
  }
  if (record.entry_display) {
    return record.entry_display;
  }
  return formatLocation(record.file_path, record.line_start);
};

const FindingListTable: React.FC<FindingListTableProps> = ({
  loading,
  data,
  total,
  currentPage,
  pageSize,
  onChange,
  onViewDetail,
  onOpenAIReview,
  openingFindingId,
}) => {
  const renderAIReviewCell = (record: Finding) => {
    const review = record.ai_review;
    if (!review?.has_assessment) {
      return <Text type="secondary">未研判</Text>;
    }

    if (review.status && review.status !== 'SUCCEEDED') {
      return <Tag color={review.status === 'FAILED' ? 'red' : 'blue'}>{review.status}</Tag>;
    }

    const confidence = String(review.confidence || '').toLowerCase();
    const verdict = String(review.verdict || '').toUpperCase();
    const color = confidence === 'high' ? 'green' : confidence === 'medium' ? 'gold' : 'default';

    if (!onOpenAIReview) {
      return <Tag color={color}>{confidence || 'unknown'}{verdict ? ` · ${verdict}` : ''}</Tag>;
    }

    return (
      <Button
        type="link"
        size="small"
        style={{ padding: 0 }}
        loading={openingFindingId === record.id}
        onClick={(e) => {
          e.stopPropagation();
          onOpenAIReview(record);
        }}
      >
        <Tag color={color} style={{ marginInlineEnd: 0, cursor: 'pointer' }}>
          {confidence || 'unknown'}{verdict ? ` · ${verdict}` : ''}
        </Tag>
      </Button>
    );
  };

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
      title: 'Vuln',
      dataIndex: 'vuln_display_name',
      key: 'vuln_display_name',
      render: (_: string, record: Finding) => <Text>{getVulnDisplayName(record)}</Text>,
    },
    {
      title: 'Entry',
      dataIndex: 'entry_display',
      key: 'entry_display',
      render: (_: string, record: Finding) => (
        <Tooltip title={getEntryTooltip(record)}>
          <Text style={{ maxWidth: 300 }} ellipsis>
            {getEntryDisplay(record)}
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
      title: 'AI 研判',
      key: 'ai_review',
      width: 160,
      render: (_: unknown, record: Finding) => renderAIReviewCell(record),
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
