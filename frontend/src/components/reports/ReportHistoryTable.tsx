import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Button, Popconfirm, Space, Table, Tag, Tooltip, message } from 'antd';
import { DeleteOutlined, DownloadOutlined, EyeOutlined } from '@ant-design/icons';
import dayjs from 'dayjs';
import { ReportService } from '../../services/report';
import type { ReportListParams, ReportPayload } from '../../types/report';
import { triggerBrowserDownload } from '../../utils/download';
import ReportPreviewDrawer from './ReportPreviewDrawer';

interface ReportHistoryTableProps {
  filters?: ReportListParams;
  autoRefresh?: boolean;
  initialPreviewReportId?: string;
  onDeletedReportId?: (reportId: string) => void;
}

const ReportHistoryTable: React.FC<ReportHistoryTableProps> = ({
  filters,
  autoRefresh = false,
  initialPreviewReportId,
  onDeletedReportId,
}) => {
  const [data, setData] = useState<ReportPayload[]>([]);
  const [loading, setLoading] = useState(false);
  const [total, setTotal] = useState(0);
  const [currentPage, setCurrentPage] = useState(1);
  const [previewOpen, setPreviewOpen] = useState(false);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewContent, setPreviewContent] = useState('');
  const [previewReport, setPreviewReport] = useState<ReportPayload | null>(null);
  const [downloadingReportId, setDownloadingReportId] = useState<string | null>(null);
  const [deletingReportId, setDeletingReportId] = useState<string | null>(null);
  const openedPreviewRef = useRef<string | null>(null);
  const pageSize = 20;

  const resetPreview = useCallback(() => {
    setPreviewOpen(false);
    setPreviewReport(null);
    setPreviewContent('');
  }, []);

  const fetchReports = useCallback(
    async (page: number) => {
      setLoading(true);
      try {
        const res = await ReportService.listReports({
          ...(filters || {}),
          page,
          page_size: pageSize,
        });
        setData(res.items);
        setTotal(res.total);
      } catch {
        message.error('获取报告列表失败');
      } finally {
        setLoading(false);
      }
    },
    [filters]
  );

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

  const openPreview = useCallback(async (reportId: string) => {
    setPreviewOpen(true);
    setPreviewLoading(true);
    try {
      const payload = await ReportService.getReportContent(reportId);
      setPreviewReport(payload.report);
      setPreviewContent(payload.content);
      openedPreviewRef.current = reportId;
    } catch {
      resetPreview();
      message.error('获取报告预览失败');
    } finally {
      setPreviewLoading(false);
    }
  }, [resetPreview]);

  useEffect(() => {
    if (!initialPreviewReportId) {
      return;
    }
    if (openedPreviewRef.current === initialPreviewReportId) {
      return;
    }
    void openPreview(initialPreviewReportId);
  }, [initialPreviewReportId, openPreview]);

  const handleDownload = useCallback(async (record: ReportPayload) => {
    try {
      setDownloadingReportId(record.id);
      const blob = await ReportService.downloadReport(record.id);
      triggerBrowserDownload(blob, record.file_name || `report-${record.id}.md`);
      message.success('下载开始');
    } catch {
      message.error('下载失败');
    } finally {
      setDownloadingReportId(null);
    }
  }, []);

  const handleDelete = useCallback(
    async (record: ReportPayload) => {
      try {
        setDeletingReportId(record.id);
        await ReportService.deleteReport(record.id);
        message.success('报告已删除');

        if (previewReport?.id === record.id) {
          resetPreview();
        }
        onDeletedReportId?.(record.id);

        const nextPage = data.length === 1 && currentPage > 1 ? currentPage - 1 : currentPage;
        if (nextPage !== currentPage) {
          setCurrentPage(nextPage);
        } else {
          await fetchReports(nextPage);
        }
      } catch {
        message.error('删除失败');
      } finally {
        setDeletingReportId(null);
      }
    },
    [
      currentPage,
      data.length,
      fetchReports,
      onDeletedReportId,
      previewReport?.id,
      resetPreview,
    ]
  );

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
      title: '报告标题',
      dataIndex: 'title',
      key: 'title',
      render: (_: string, record: ReportPayload) => (
        <Space orientation="vertical" size={2}>
          <span style={{ color: '#1d4ed8', fontWeight: 600 }}>
            {record.title || record.file_name || `report-${record.id.slice(0, 8)}`}
          </span>
          {record.template_key ? (
            <span style={{ color: '#64748b', fontSize: 12 }}>{record.template_key}</span>
          ) : null}
        </Space>
      ),
    },
    {
      title: '类型',
      dataIndex: 'report_type',
      key: 'report_type',
      width: 120,
      render: (value: string) => <Tag color={value === 'SCAN' ? 'blue' : 'purple'}>{value}</Tag>,
    },
    {
      title: '摘要',
      dataIndex: 'summary_text',
      key: 'summary_text',
      render: (text: string, record: ReportPayload) => (
        <span style={{ color: '#475569' }}>{text || record.file_name || '-'}</span>
      ),
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 120,
      render: (status: string) => getStatusTag(status),
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 180,
      render: (text: string) => (text ? dayjs(text).format('YYYY-MM-DD HH:mm:ss') : '-'),
    },
    {
      title: '操作',
      key: 'action',
      width: 180,
      render: (_: unknown, record: ReportPayload) => {
        const downloadable = Boolean(record.object_key) || ['DRAFT', 'PUBLISHED', 'COMPLETED'].includes(record.status);

        return (
          <Space size="small">
            <Tooltip title="预览报告">
              <Button
                type="text"
                icon={<EyeOutlined />}
                aria-label={`预览报告 ${record.title || record.id}`}
                onClick={() => {
                  void openPreview(record.id);
                }}
              />
            </Tooltip>
            <Tooltip title={downloadable ? '下载报告' : '文件生成中'}>
              <Button
                type="text"
                icon={<DownloadOutlined />}
                aria-label={`下载报告 ${record.title || record.id}`}
                disabled={!downloadable}
                loading={downloadingReportId === record.id}
                onClick={() => {
                  void handleDownload(record);
                }}
                style={{ color: downloadable ? '#f59e0b' : undefined }}
              />
            </Tooltip>
            <Popconfirm
              title="确定删除这份报告吗？"
              description="删除后将无法预览或下载；若这是该任务最后一份报告，还会清理对应报告产物与日志。"
              okText="删除"
              cancelText="取消"
              okButtonProps={{ danger: true }}
              onConfirm={() => handleDelete(record)}
            >
              <Tooltip title="删除报告">
                <Button
                  type="text"
                  danger
                  icon={<DeleteOutlined />}
                  aria-label={`删除报告 ${record.title || record.id}`}
                  loading={deletingReportId === record.id}
                />
              </Tooltip>
            </Popconfirm>
          </Space>
        );
      },
    },
  ];

  return (
    <>
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

      <ReportPreviewDrawer
        open={previewOpen}
        loading={previewLoading}
        report={previewReport}
        content={previewContent}
        onClose={() => setPreviewOpen(false)}
        onDownload={() => {
          if (previewReport) {
            void handleDownload(previewReport);
          }
        }}
        downloading={previewReport ? downloadingReportId === previewReport.id : false}
      />
    </>
  );
};

export default ReportHistoryTable;
