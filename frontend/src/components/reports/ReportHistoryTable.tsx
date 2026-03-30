import React, { useCallback, useEffect, useState } from 'react';
import { Table, Tag, Button, message, Space, Tooltip } from 'antd';
import { DownloadOutlined } from '@ant-design/icons';
import { ReportService } from '../../services/report';
import type { ReportListParams, ReportPayload } from '../../types/report';
import { triggerBrowserDownload } from '../../utils/download';
import dayjs from 'dayjs';

interface ReportHistoryTableProps {
  filters?: ReportListParams;
  autoRefresh?: boolean;
}

const ReportHistoryTable: React.FC<ReportHistoryTableProps> = ({
  filters,
  autoRefresh = false,
}) => {
  const [data, setData] = useState<ReportPayload[]>([]);
  const [loading, setLoading] = useState<boolean>(false);
  const [total, setTotal] = useState<number>(0);
  const [currentPage, setCurrentPage] = useState<number>(1);
  const pageSize = 20;

  const fetchReports = useCallback(async (page: number) => {
    setLoading(true);
    try {
      const res = await ReportService.listReports({
        ...(filters || {}),
        page,
        page_size: pageSize,
      });
      setData(res.items);
      setTotal(res.total);
    } catch (error) {
      message.error('获取报告历史失败');
    } finally {
      setLoading(false);
    }
  }, [filters]);

  useEffect(() => {
    setCurrentPage(1);
  }, [filters]);

  useEffect(() => {
    void fetchReports(currentPage);
  }, [currentPage, fetchReports]);

  useEffect(() => {
    if (!autoRefresh) {
      return;
    }

    const timer = window.setInterval(() => {
      void fetchReports(currentPage);
    }, 4000);

    return () => {
      window.clearInterval(timer);
    };
  }, [autoRefresh, currentPage, fetchReports]);

  const handleDownload = async (record: ReportPayload) => {
    try {
      const blob = await ReportService.downloadReport(record.id);
      triggerBrowserDownload(blob, record.file_name || `report-${record.id}.md`);
      message.success('下载开始');
    } catch (error) {
      message.error('下载失败');
    }
  };

  const getStatusTag = (status: string) => {
    const statusMap: Record<string, { color: string; text: string }> = {
      DRAFT: { color: 'processing', text: '已生成' },
      PUBLISHED: { color: 'success', text: '已发布' },
      PENDING: { color: 'default', text: '排队中' },
      GENERATING: { color: 'processing', text: '生成中' },
      COMPLETED: { color: 'success', text: '已完成' },
      FAILED: { color: 'error', text: '失败' },
    };
    const config = statusMap[status] || { color: 'default', text: status };
    return <Tag color={config.color}>{config.text}</Tag>;
  };

  const columns = [
    {
      title: '报告文件',
      dataIndex: 'file_name',
      key: 'file_name',
      render: (text: string, record: ReportPayload) => (
        <span style={{ fontFamily: 'Fira Code, monospace', color: '#1E40AF', fontWeight: 500 }}>
          {text || `report_${record.id.substring(0, 8)}`}
        </span>
      ),
    },
    {
      title: '类型',
      dataIndex: 'report_type',
      key: 'report_type',
      width: 120,
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 120,
      render: (status: string) => getStatusTag(status),
    },
    {
      title: '格式',
      dataIndex: 'format',
      key: 'format',
      width: 100,
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 180,
      render: (text: string) => text ? dayjs(text).format('YYYY-MM-DD HH:mm:ss') : '-',
    },
    {
      title: '操作',
      key: 'action',
      width: 120,
      render: (_: unknown, record: ReportPayload) => {
        const downloadable = Boolean(record.object_key) || ['DRAFT', 'PUBLISHED', 'COMPLETED'].includes(record.status);

        return (
          <Space size="middle">
            <Tooltip title={downloadable ? '下载报告' : '文件生成中'}>
            <Button
              type="text"
              icon={<DownloadOutlined />}
              disabled={!downloadable}
              onClick={() => handleDownload(record)}
              style={{ color: downloadable ? '#F59E0B' : undefined }}
            />
            </Tooltip>
          </Space>
        );
      },
    },
  ];

  return (
    <div>
      <Table
        size="small"
        columns={columns}
        dataSource={data}
        rowKey="id"
        loading={loading}
        pagination={{
          current: currentPage,
          pageSize,
          total,
          onChange: (page) => setCurrentPage(page),
          showSizeChanger: false,
        }}
        rowClassName={() => 'hover-row-highlight'}
      />
    </div>
  );
};

export default ReportHistoryTable;
