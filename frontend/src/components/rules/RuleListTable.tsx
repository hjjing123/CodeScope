import React from 'react';
import { Table, Tag, Button, Switch, Space, Tooltip } from 'antd';
import { EditOutlined, HistoryOutlined } from '@ant-design/icons';
import type { ColumnsType, TablePaginationConfig } from 'antd/es/table';
import type { FilterValue, SorterResult } from 'antd/es/table/interface';
import dayjs from 'dayjs';
import type { Rule } from '../../types/rule';

interface RuleListTableProps {
  loading: boolean;
  dataSource: Rule[];
  pagination: TablePaginationConfig;
  onChange: (
    pagination: TablePaginationConfig,
    filters: Record<string, FilterValue | null>,
    sorter: SorterResult<Rule> | SorterResult<Rule>[]
  ) => void;
  onEdit: (rule: Rule) => void;
  onToggle: (rule: Rule, checked: boolean) => void;
  onViewVersions: (rule: Rule) => void;
  size?: 'small' | 'middle' | 'large';
}

const severityColors: Record<string, string> = {
  CRITICAL: 'red',
  HIGH: 'orange',
  MEDIUM: 'gold',
  LOW: 'blue',
  INFO: 'cyan',
};

const RuleListTable: React.FC<RuleListTableProps> = ({
  loading,
  dataSource,
  pagination,
  onChange,
  onEdit,
  onToggle,
  onViewVersions,
  size = 'middle',
}) => {
  const columns: ColumnsType<Rule> = [
    {
      title: '规则名称',
      dataIndex: 'name',
      key: 'name',
      render: (text, record) => (
        <Space direction="vertical" size={0}>
          <a onClick={() => onEdit(record)} style={{ fontWeight: 500 }}>{text}</a>
          <span style={{ fontSize: '12px', color: '#8c8c8c', fontFamily: 'monospace' }}>{record.rule_key}</span>
        </Space>
      ),
    },
    {
      title: '漏洞类型',
      dataIndex: 'vuln_type',
      key: 'vuln_type',
      render: (text) => <Tag>{text}</Tag>,
    },
    {
      title: '严重程度',
      dataIndex: 'default_severity',
      key: 'default_severity',
      render: (text) => (
        <Tag color={severityColors[text] || 'default'}>{text}</Tag>
      ),
      filters: [
        { text: 'Critical', value: 'CRITICAL' },
        { text: 'High', value: 'HIGH' },
        { text: 'Medium', value: 'MEDIUM' },
        { text: 'Low', value: 'LOW' },
        { text: 'Info', value: 'INFO' },
      ],
    },
    {
      title: '状态',
      dataIndex: 'enabled',
      key: 'enabled',
      render: (enabled, record) => (
        <Switch
          checked={enabled}
          onChange={(checked) => onToggle(record, checked)}
          checkedChildren="启用"
          unCheckedChildren="禁用"
        />
      ),
      filters: [
        { text: '启用', value: true },
        { text: '禁用', value: false },
      ],
    },
    {
      title: '最后更新',
      dataIndex: 'updated_at',
      key: 'updated_at',
      render: (text) => dayjs(text).format('YYYY-MM-DD HH:mm:ss'),
      sorter: (a, b) => dayjs(a.updated_at).unix() - dayjs(b.updated_at).unix(),
    },
    {
      title: '操作',
      key: 'action',
      render: (_, record) => (
        <Space size="middle">
          <Tooltip title="编辑规则">
            <Button
              type="text"
              icon={<EditOutlined />}
              onClick={() => onEdit(record)}
            />
          </Tooltip>
          <Tooltip title="查看版本">
            <Button
              type="text"
              icon={<HistoryOutlined />}
              onClick={() => onViewVersions(record)}
            />
          </Tooltip>
        </Space>
      ),
    },
  ];

  return (
    <Table
      columns={columns}
      dataSource={dataSource}
      loading={loading}
      pagination={pagination}
      onChange={onChange}
      rowKey="rule_key"
      size={size}
    />
  );
};

export default RuleListTable;
