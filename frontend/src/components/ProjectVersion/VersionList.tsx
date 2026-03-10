import React, { useEffect, useState } from 'react';
import { Table, Button, Space, Tag, Modal, message, Tooltip } from 'antd';
import {
  PlusOutlined,
  CodeOutlined,
  DeleteOutlined,
  SyncOutlined,
  ExclamationCircleOutlined,
  RadarChartOutlined,
} from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import { useNavigate } from 'react-router-dom';
import { getVersions, deleteVersion, triggerGitSync } from '../../services/projectVersion';
import type { Version } from '../../types/projectVersion';
import ImportWizard from './ImportWizard';
import CodeBrowser from './CodeBrowser';

interface VersionListProps {
  projectId: string;
}

const getErrorMessage = (error: unknown, fallback: string): string => {
  if (error instanceof Error && error.message) {
    return error.message;
  }
  return fallback;
};

const VersionList: React.FC<VersionListProps> = ({ projectId }) => {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState<Version[]>([]);
  const [total, setTotal] = useState(0);
  const [currentPage, setCurrentPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);

  const [importVisible, setImportVisible] = useState(false);
  const [syncing, setSyncing] = useState(false);

  const [codeBrowserVisible, setCodeBrowserVisible] = useState(false);
  const [selectedVersion, setSelectedVersion] = useState<Version | null>(null);

  const fetchVersions = async (page: number, size: number) => {
    try {
      setLoading(true);
      const res = await getVersions(projectId, { page, page_size: size });
      setData(res.data.items);
      setTotal(res.data.total);
    } catch (error) {
      message.error(`加载代码快照失败：${getErrorMessage(error, '未知错误')}`);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (projectId) {
      void fetchVersions(currentPage, pageSize);
    }
  }, [projectId, currentPage, pageSize]);

  const handleDelete = (version: Version) => {
    Modal.confirm({
      title: '确认删除',
      icon: <ExclamationCircleOutlined />,
      content: `确定要删除代码快照 "${version.name}" 吗？此操作不可恢复。`,
      onOk: async () => {
        try {
          await deleteVersion(version.id);
          message.success('删除成功');
          void fetchVersions(currentPage, pageSize);
        } catch (error) {
          message.error(`删除失败: ${getErrorMessage(error, '未知错误')}`);
        }
      },
    });
  };

  const handleGitSync = async () => {
    try {
      setSyncing(true);
      await triggerGitSync(projectId);
      message.success('Git 同步任务已触发');
      void fetchVersions(currentPage, pageSize);
    } catch (error) {
      message.error(`Git 同步失败: ${getErrorMessage(error, '未知错误')}`);
    } finally {
      setSyncing(false);
    }
  };

  const columns: ColumnsType<Version> = [
    {
      title: '代码快照名称',
      dataIndex: 'name',
      key: 'name',
      render: (text) => <span style={{ fontWeight: 500 }}>{text}</span>,
    },
    {
      title: '来源',
      dataIndex: 'source',
      key: 'source',
      render: (source) => (
        <Tag color={String(source).toUpperCase() === 'GIT' ? 'blue' : 'orange'}>
          {String(source).toUpperCase() === 'GIT' ? 'Git Import' : 'Upload'}
        </Tag>
      ),
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      render: (status) => {
        let color = 'default';
        const normalizedStatus = String(status).toUpperCase();
        if (normalizedStatus === 'READY') color = 'success';
        if (normalizedStatus === 'FAILED') color = 'error';
        if (normalizedStatus === 'IMPORTING') color = 'processing';
        return <Tag color={color}>{status}</Tag>;
      },
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      key: 'created_at',
      render: (date) => new Date(date).toLocaleString(),
    },
    {
      title: '操作',
      key: 'action',
      render: (_, record) => (
        <Space size="middle">
          <Tooltip title="浏览代码">
            <Button
              icon={<CodeOutlined />}
              type="text"
              onClick={() => {
                setSelectedVersion(record);
                setCodeBrowserVisible(true);
              }}
            />
          </Tooltip>
          <Tooltip title="前往扫描任务页面发起扫描">
            <Button
              icon={<RadarChartOutlined />}
              type="text"
              onClick={() => {
                navigate(
                  `/scans?project_id=${encodeURIComponent(projectId)}&version_id=${encodeURIComponent(record.id)}&create=1`
                );
              }}
            />
          </Tooltip>

          <Tooltip title="删除代码快照">
            <Button
              icon={<DeleteOutlined />}
              type="text"
              danger
              onClick={() => handleDelete(record)}
            />
          </Tooltip>
        </Space>
      ),
    },
  ];

  return (
    <div>
      <h3 style={{ margin: '0 0 16px' }}>代码快照列表</h3>
      <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between' }}>
        <Space>
            <Button
            type="primary"
            icon={<PlusOutlined />}
            onClick={() => setImportVisible(true)}
            >
            导入代码
            </Button>
            <Button 
                type="primary"
                icon={<SyncOutlined />} 
                onClick={() => void handleGitSync()} 
                loading={syncing}
            >
            Git 同步
            </Button>
        </Space>
        
        <Button
          icon={<SyncOutlined />}
          onClick={() => void fetchVersions(currentPage, pageSize)}
        >
          刷新
        </Button>
      </div>

      <Table
        columns={columns}
        dataSource={data}
        rowKey="id"
        pagination={{
          current: currentPage,
          pageSize: pageSize,
          total: total,
          onChange: (page, size) => {
            setCurrentPage(page);
            setPageSize(size);
          },
        }}
        loading={loading}
      />

      <ImportWizard
        open={importVisible}
        onCancel={() => setImportVisible(false)}
        onSuccess={() => {
          setImportVisible(false);
          fetchVersions(1, pageSize);
        }}
        projectId={projectId}
      />

      {selectedVersion && (
        <CodeBrowser
          open={codeBrowserVisible}
          onClose={() => {
            setCodeBrowserVisible(false);
            setSelectedVersion(null);
          }}
          versionId={selectedVersion.id}
          versionName={selectedVersion.name}
        />
      )}
    </div>
  );
};

export default VersionList;
